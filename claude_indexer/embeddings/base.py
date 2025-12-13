"""Base classes and interfaces for text embedding generation."""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from ..indexer_logging import get_logger

if TYPE_CHECKING:
    from .cache import PersistentEmbeddingCache

try:
    from tiktoken import Encoding
except ImportError:
    # Create a placeholder type for when tiktoken is not available
    class _EncodingFallback:
        pass

    Encoding = _EncodingFallback  # type: ignore


@dataclass
class EmbeddingResult:
    """Result of an embedding operation."""

    text: str
    embedding: list[float]

    # Metadata
    model: str = ""
    token_count: int = 0
    processing_time: float = 0.0
    cost_estimate: float = 0.0
    error: str | None = None

    @property
    def success(self) -> bool:
        """Check if embedding generation was successful."""
        return self.error is None and len(self.embedding) > 0

    @property
    def dimension(self) -> int:
        """Get the dimensionality of the embedding vector."""
        return len(self.embedding)


class TiktokenMixin:
    """Mixin for accurate token counting with tiktoken."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._tiktoken_encoder: Encoding | None = None
        self.logger = get_logger()
        self._init_tiktoken()

    def _init_tiktoken(self) -> None:
        """Initialize tiktoken encoder for the model."""
        try:
            import tiktoken

            if hasattr(self, "model"):
                # Try model-specific encoder first
                try:
                    self._tiktoken_encoder = tiktoken.encoding_for_model(self.model)
                    self.logger.debug(f"Using model-specific encoder for {self.model}")
                except KeyError:
                    # Fallback to cl100k_base for most embedding models
                    self._tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
                    self.logger.debug(f"Using cl100k_base encoder for {self.model}")
            else:
                # Default to cl100k_base for most models
                self._tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
                self.logger.debug("Using default cl100k_base encoder")
        except ImportError:
            self.logger.warning("tiktoken not available, using character approximation")
            self._tiktoken_encoder = None
        except Exception as e:
            self.logger.warning(f"tiktoken initialization failed: {e}")
            self._tiktoken_encoder = None

    def _estimate_tokens_with_tiktoken(self, text: str) -> int:
        """Accurate token count using tiktoken with fallback."""
        if self._tiktoken_encoder:
            try:
                return max(1, len(self._tiktoken_encoder.encode(text)))
            except Exception as e:
                self.logger.debug(
                    f"Tiktoken encoding failed: {e}, falling back to approximation"
                )

        # Fallback to character-based approximation
        return max(1, len(text) // 4)

    def _character_approximation(self, text: str) -> int:
        """Character-based token approximation fallback."""
        return max(1, len(text) // 4)


class Embedder(ABC):
    """Abstract base class for text embedding generators."""

    @abstractmethod
    def embed_text(self, text: str) -> EmbeddingResult:
        """Generate embedding for a single text."""
        pass

    @abstractmethod
    def embed_batch(
        self, texts: list[str], item_type: str = "general"
    ) -> list[EmbeddingResult]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of text strings to embed
            item_type: Type of items being embedded ('relation', 'entity', 'implementation', 'general')
                      Used for batch size optimization.
        """
        pass

    @abstractmethod
    def get_model_info(self) -> dict[str, Any]:
        """Get information about the embedding model."""
        pass

    @abstractmethod
    def get_max_tokens(self) -> int:
        """Get maximum token limit for input text."""
        pass

    def truncate_text(self, text: str, max_tokens: int | None = None) -> str:
        """Truncate text to fit within token limits."""
        if max_tokens is None:
            max_tokens = self.get_max_tokens()

        # Use tiktoken if available (for classes that inherit TiktokenMixin)
        if hasattr(self, "_estimate_tokens_with_tiktoken"):
            current_tokens = self._estimate_tokens_with_tiktoken(text)
            if current_tokens <= max_tokens:
                return text

            # Binary search approach for accurate truncation
            left, right = 0, len(text)
            best_length = 0

            while left <= right:
                mid = (left + right) // 2
                truncated = text[:mid]
                tokens = self._estimate_tokens_with_tiktoken(truncated)

                if tokens <= max_tokens:
                    best_length = mid
                    left = mid + 1
                else:
                    right = mid - 1

            # Truncate at word boundary when possible
            truncated = text[:best_length]
            last_space = truncated.rfind(" ")

            if last_space > best_length * 0.8:  # Don't lose too much content
                truncated = truncated[:last_space]

            return truncated + "..."

        # Fallback to character approximation
        max_chars = max_tokens * 4

        if len(text) <= max_chars:
            return text

        # Truncate at word boundary when possible
        truncated = text[:max_chars]
        last_space = truncated.rfind(" ")

        if last_space > max_chars * 0.8:  # Don't lose too much content
            truncated = truncated[:last_space]

        return truncated + "..."


class RetryableEmbedder(Embedder):
    """Base class for embedders that support retry logic."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for exponential backoff with jitter."""
        import random

        delay = self.base_delay * (self.backoff_factor**attempt)
        delay = min(delay, self.max_delay)

        # Add jitter to prevent thundering herd
        jitter = random.uniform(0.1, 0.3) * delay
        return delay + jitter

    def _should_retry(self, error: Exception, attempt: int) -> bool:
        """Determine if an error should trigger a retry."""
        if attempt >= self.max_retries:
            return False

        # Retry on common transient errors
        error_str = str(error).lower()
        transient_errors = [
            "rate limit",
            "timeout",
            "connection",
            "temporary",
            "503",
            "502",
            "429",
        ]

        return any(err in error_str for err in transient_errors)

    def _embed_with_retry(self, operation_func: Any, *args: Any, **kwargs: Any) -> Any:
        """Execute embedding operation with retry logic."""
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return operation_func(*args, **kwargs)
            except Exception as e:
                last_error = e

                if not self._should_retry(e, attempt):
                    break

                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt)
                    print(
                        f"Embedding attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)

        # If we get here, all retries failed
        assert (
            last_error is not None
        )  # We must have caught an exception to reach this point
        raise last_error


class CachingEmbedder(Embedder):
    """Wrapper that adds two-tier caching (memory + persistent disk) to any embedder.

    Caching hierarchy:
    1. In-memory cache (fastest, volatile)
    2. Persistent disk cache (fast, survives restarts)
    3. API call (slow, rate-limited)
    """

    def __init__(
        self,
        embedder: Embedder,
        max_cache_size: int = 10000,
        persistent_cache: "PersistentEmbeddingCache | None" = None,
    ):
        self.embedder = embedder
        self.max_cache_size = max_cache_size
        self._cache: dict[str, EmbeddingResult] = {}
        self._persistent_cache = persistent_cache
        self.logger = get_logger()

        # Statistics
        self._memory_hits = 0
        self._disk_hits = 0
        self._api_calls = 0

    @classmethod
    def with_persistent_cache(
        cls,
        embedder: Embedder,
        cache_dir: Path | str,
        model_name: str = "default",
        max_memory_cache: int = 10000,
        max_disk_cache_mb: int = 500,
    ) -> "CachingEmbedder":
        """Create CachingEmbedder with persistent disk cache enabled.

        Args:
            embedder: The underlying embedder to wrap
            cache_dir: Directory to store persistent cache
            model_name: Model identifier for cache isolation
            max_memory_cache: Max entries in memory cache
            max_disk_cache_mb: Max size of disk cache in MB
        """
        from .cache import PersistentEmbeddingCache

        persistent = PersistentEmbeddingCache(
            cache_dir=cache_dir,
            max_size_mb=max_disk_cache_mb,
            model_name=model_name,
        )
        return cls(
            embedder=embedder,
            max_cache_size=max_memory_cache,
            persistent_cache=persistent,
        )

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        import hashlib

        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def _add_to_cache(self, text: str, result: EmbeddingResult) -> None:
        """Add result to both memory and persistent cache."""
        if len(self._cache) >= self.max_cache_size:
            # Remove oldest entries (simple FIFO)
            keys_to_remove = list(self._cache.keys())[: len(self._cache) // 2]
            for key in keys_to_remove:
                del self._cache[key]

        cache_key = self._get_cache_key(text)
        self._cache[cache_key] = result

        # Also save to persistent cache
        if self._persistent_cache is not None and result.embedding:
            self._persistent_cache.set(cache_key, result.embedding, result.dimension)

    def _get_from_persistent(self, cache_key: str, text: str) -> EmbeddingResult | None:
        """Try to get embedding from persistent cache and wrap as EmbeddingResult."""
        if self._persistent_cache is None:
            return None

        embedding = self._persistent_cache.get(cache_key)
        if embedding is None:
            return None

        # Reconstruct EmbeddingResult from cached embedding
        result = EmbeddingResult(
            text=text,
            embedding=embedding,
            model=self.embedder.get_model_info().get("model", "cached"),
        )
        return result

    def embed_text(self, text: str) -> EmbeddingResult:
        """Embed text with two-tier caching."""
        cache_key = self._get_cache_key(text)

        # Tier 1: Memory cache
        if cache_key in self._cache:
            self._memory_hits += 1
            return self._cache[cache_key]

        # Tier 2: Persistent cache
        persistent_result = self._get_from_persistent(cache_key, text)
        if persistent_result is not None:
            self._disk_hits += 1
            # Promote to memory cache
            self._cache[cache_key] = persistent_result
            return persistent_result

        # Tier 3: API call
        self._api_calls += 1
        result = self.embedder.embed_text(text)

        if result.success:
            self._add_to_cache(text, result)

        return result

    def embed_batch(
        self, texts: list[str], item_type: str = "general"
    ) -> list[EmbeddingResult]:
        """Embed batch with two-tier caching.

        Args:
            texts: List of text strings to embed
            item_type: Type of items being embedded (passed through to wrapped embedder)
        """
        results: list[EmbeddingResult | None] = [None] * len(texts)
        uncached_texts = []
        uncached_indices = []

        # Check both cache tiers for each text
        for i, text in enumerate(texts):
            cache_key = self._get_cache_key(text)

            # Tier 1: Memory cache
            if cache_key in self._cache:
                self._memory_hits += 1
                results[i] = self._cache[cache_key]
                continue

            # Tier 2: Persistent cache
            persistent_result = self._get_from_persistent(cache_key, text)
            if persistent_result is not None:
                self._disk_hits += 1
                # Promote to memory cache
                self._cache[cache_key] = persistent_result
                results[i] = persistent_result
                continue

            # Need API call
            uncached_texts.append(text)
            uncached_indices.append(i)

        # Log cache efficiency
        total = len(texts)
        cached = total - len(uncached_texts)
        if total > 0 and cached > 0:
            self.logger.debug(
                f"Embedding batch: {cached}/{total} from cache "
                f"({cached * 100 / total:.0f}% hit rate)"
            )

        # Tier 3: Embed uncached texts via API
        if uncached_texts:
            self._api_calls += len(uncached_texts)
            uncached_results = self.embedder.embed_batch(
                uncached_texts, item_type=item_type
            )

            # Fill in results and update cache
            for i, result in enumerate(uncached_results):
                original_index = uncached_indices[i]
                results[original_index] = result

                if result.success:
                    self._add_to_cache(uncached_texts[i], result)

            # Flush persistent cache after batch
            if self._persistent_cache is not None:
                self._persistent_cache.flush()

        # All placeholders should now be filled
        return cast(list[EmbeddingResult], results)

    def get_model_info(self) -> dict[str, Any]:
        """Get model info from wrapped embedder."""
        info = self.embedder.get_model_info()
        info["caching_enabled"] = True
        info["memory_cache_size"] = len(self._cache)
        info["max_memory_cache_size"] = self.max_cache_size
        info["persistent_cache_enabled"] = self._persistent_cache is not None
        if self._persistent_cache:
            info["persistent_cache_stats"] = self._persistent_cache.get_stats()
        return info

    def get_max_tokens(self) -> int:
        """Get max tokens from wrapped embedder."""
        return self.embedder.get_max_tokens()

    def get_cache_stats(self) -> dict[str, Any]:
        """Get comprehensive cache statistics."""
        total_requests = self._memory_hits + self._disk_hits + self._api_calls
        stats = {
            "memory_cache_size": len(self._cache),
            "max_memory_cache_size": self.max_cache_size,
            "memory_hits": self._memory_hits,
            "disk_hits": self._disk_hits,
            "api_calls": self._api_calls,
            "total_requests": total_requests,
            "overall_hit_ratio": (self._memory_hits + self._disk_hits)
            / max(total_requests, 1),
            "memory_hit_ratio": self._memory_hits / max(total_requests, 1),
            "disk_hit_ratio": self._disk_hits / max(total_requests, 1),
        }

        if self._persistent_cache:
            stats["persistent_cache"] = self._persistent_cache.get_stats()

        return stats

    def flush_persistent_cache(self) -> None:
        """Force flush persistent cache to disk."""
        if self._persistent_cache:
            self._persistent_cache.flush()


class BatchingEmbedder(Embedder):
    """Embedder wrapper with intelligent batching using BatchOptimizer.

    Provides adaptive batch sizing based on memory pressure, error rates,
    and processing history. This wrapper ensures efficient embedding
    generation by automatically adjusting batch sizes.

    Features:
        - Memory-aware batch sizing (reduces when approaching threshold)
        - Error-rate tracking (reduces batch size on high errors)
        - Success streaks (increases batch size after consecutive successes)
        - Statistics tracking for performance analysis

    Example:
        >>> embedder = OpenAIEmbedder()
        >>> batching = BatchingEmbedder(embedder, initial_batch_size=25)
        >>> results = batching.embed_batch(texts)
        >>> print(batching.get_optimizer_stats())
    """

    def __init__(
        self,
        embedder: Embedder,
        initial_batch_size: int = 25,
        max_batch_size: int = 100,
        memory_threshold_mb: int = 2000,
    ):
        """Initialize the batching embedder.

        Args:
            embedder: The underlying embedder to wrap.
            initial_batch_size: Starting batch size.
            max_batch_size: Maximum batch size limit.
            memory_threshold_mb: Memory threshold for batch reduction.
        """
        from ..indexing.batch_optimizer import BatchOptimizer

        self.embedder = embedder
        self.optimizer = BatchOptimizer(
            initial_size=initial_batch_size,
            max_size=max_batch_size,
            memory_threshold_mb=memory_threshold_mb,
        )
        self.logger = get_logger()

        # Track total embeddings processed
        self._total_processed = 0
        self._total_errors = 0

    def embed_text(self, text: str) -> EmbeddingResult:
        """Embed a single text (delegates to wrapped embedder).

        Args:
            text: Text to embed.

        Returns:
            EmbeddingResult with embedding or error.
        """
        result = self.embedder.embed_text(text)
        self._total_processed += 1
        if not result.success:
            self._total_errors += 1
        return result

    def embed_batch(
        self, texts: list[str], item_type: str = "general"
    ) -> list[EmbeddingResult]:
        """Embed batch with adaptive sizing based on BatchOptimizer.

        Splits the input into optimally-sized sub-batches based on
        memory pressure and processing history.

        Args:
            texts: List of texts to embed.
            item_type: Type of items being embedded (for wrapped embedder).

        Returns:
            List of EmbeddingResult objects.
        """
        from ..indexing.types import BatchMetrics

        if not texts:
            return []

        results: list[EmbeddingResult] = []
        remaining = list(texts)  # Copy to avoid mutating input

        while remaining:
            # Get current optimal batch size
            batch_size = self.optimizer.get_batch_size()
            batch = remaining[:batch_size]
            remaining = remaining[batch_size:]

            # Process batch
            start_time = time.perf_counter()
            try:
                batch_results = self.embedder.embed_batch(batch, item_type=item_type)
            except Exception as e:
                # On exception, create error results for all in batch
                self.logger.error(f"Batch embedding failed: {e}")
                batch_results = [
                    EmbeddingResult(text=t, embedding=[], error=str(e)) for t in batch
                ]

            processing_time_ms = (time.perf_counter() - start_time) * 1000

            # Count errors
            error_count = sum(1 for r in batch_results if not r.success)
            self._total_processed += len(batch_results)
            self._total_errors += error_count

            # Record metrics for optimizer
            metrics = BatchMetrics(
                batch_size=len(batch),
                processing_time_ms=processing_time_ms,
                error_count=error_count,
            )
            self.optimizer.record_batch(metrics)

            results.extend(batch_results)

        return results

    def get_model_info(self) -> dict[str, Any]:
        """Get model info with batching stats.

        Returns:
            Dictionary with model info and batching configuration.
        """
        info = self.embedder.get_model_info()
        info["batching_enabled"] = True
        info["current_batch_size"] = self.optimizer.current_size
        info["optimizer_stats"] = self.optimizer.get_statistics()
        return info

    def get_max_tokens(self) -> int:
        """Get max tokens from wrapped embedder."""
        return self.embedder.get_max_tokens()

    def get_optimizer_stats(self) -> dict[str, Any]:
        """Get comprehensive optimizer statistics.

        Returns:
            Dictionary with optimizer stats and embedding totals.
        """
        stats = self.optimizer.get_statistics()
        stats["total_embeddings_processed"] = self._total_processed
        stats["total_embedding_errors"] = self._total_errors
        stats["overall_error_rate"] = (
            self._total_errors / self._total_processed
            if self._total_processed > 0
            else 0.0
        )
        return stats

    def reset_optimizer(self) -> None:
        """Reset the batch optimizer to initial state."""
        self.optimizer.reset()

    @property
    def current_batch_size(self) -> int:
        """Get current batch size."""
        return self.optimizer.current_size
