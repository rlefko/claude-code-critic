"""Registry for managing embedder instances and configurations."""

from pathlib import Path
from typing import Any

from .base import CachingEmbedder, Embedder, RetryableEmbedder
from .bm25 import BM25_AVAILABLE, BM25Embedder
from .openai import OPENAI_AVAILABLE, OpenAIEmbedder
from .voyage import VOYAGE_AVAILABLE, VoyageEmbedder


class EmbedderRegistry:
    """Registry for creating and managing embedders."""

    def __init__(self) -> None:
        self._embedders: dict[str, type[Embedder]] = {}
        self._register_default_embedders()

    def _register_default_embedders(self) -> None:
        """Register default embedder implementations."""
        if OPENAI_AVAILABLE:
            self.register("openai", OpenAIEmbedder)
        if VOYAGE_AVAILABLE:
            self.register("voyage", VoyageEmbedder)
        if BM25_AVAILABLE:
            self.register("bm25", BM25Embedder)

    def register(self, name: str, embedder_class: type[Embedder]) -> None:
        """Register an embedder class."""
        self._embedders[name] = embedder_class

    def create_embedder(
        self,
        provider: str,
        config: dict[str, Any],
        enable_caching: bool = True,
        cache_dir: Path | str | None = None,
    ) -> Embedder:
        """Create an embedder instance from configuration.

        Args:
            provider: Embedder provider name (openai, voyage, bm25)
            config: Provider-specific configuration
            enable_caching: Whether to enable caching
            cache_dir: Optional directory for persistent disk cache.
                      If provided, enables two-tier caching (memory + disk).
        """
        if provider not in self._embedders:
            available = list(self._embedders.keys())
            raise ValueError(
                f"Unknown embedder provider: {provider}. Available: {available}"
            )

        embedder_class = self._embedders[provider]

        try:
            # Create base embedder
            embedder = embedder_class(**config)

            # Wrap with caching if enabled
            if enable_caching:
                cache_size = config.get("cache_size", 10000)

                if cache_dir is not None:
                    # Use two-tier caching (memory + persistent disk)
                    model_name = config.get("model", provider)
                    embedder = CachingEmbedder.with_persistent_cache(
                        embedder=embedder,
                        cache_dir=cache_dir,
                        model_name=model_name,
                        max_memory_cache=cache_size,
                        max_disk_cache_mb=500,
                    )
                else:
                    # Use memory-only caching
                    embedder = CachingEmbedder(embedder, max_cache_size=cache_size)

            return embedder

        except Exception as e:
            raise RuntimeError(f"Failed to create {provider} embedder: {e}") from None

    def get_available_providers(self) -> list[str]:
        """Get list of available embedder providers."""
        return list(self._embedders.keys())

    def get_provider_info(self, provider: str) -> dict[str, Any]:
        """Get information about a specific provider."""
        if provider not in self._embedders:
            raise ValueError(f"Unknown provider: {provider}")

        embedder_class = self._embedders[provider]

        # Try to get model info without instantiating
        if hasattr(embedder_class, "MODELS"):
            return {
                "provider": provider,
                "class": embedder_class.__name__,
                "available_models": list(embedder_class.MODELS.keys()),
                "supports_batch": True,
                "supports_retry": issubclass(embedder_class, RetryableEmbedder),
            }

        return {
            "provider": provider,
            "class": embedder_class.__name__,
            "available_models": ["unknown"],
            "supports_batch": hasattr(embedder_class, "embed_batch"),
            "supports_retry": False,
        }


def create_embedder_from_config(
    config: Any,
    cache_dir: Path | str | None = None,
) -> Embedder:
    """Create embedder from configuration (IndexerConfig or dict).

    Args:
        config: IndexerConfig object or dict with embedder settings
        cache_dir: Optional directory for persistent disk cache.
                  If provided, enables two-tier caching (memory + disk).
    """
    registry = EmbedderRegistry()

    # Handle both IndexerConfig objects and dicts
    if hasattr(config, "embedding_provider"):
        # IndexerConfig object
        provider = config.embedding_provider
        enable_caching = True  # Default for IndexerConfig

        # Try to get cache_dir from config if not provided
        if cache_dir is None and hasattr(config, "project_path"):
            cache_dir = Path(config.project_path) / ".index_cache"

        if provider == "voyage":
            provider_config = {
                "api_key": config.voyage_api_key,
                "model": config.voyage_model,
            }
        elif provider == "bm25":
            provider_config = {
                "model_name": getattr(config, "bm25_model", "bm25"),
                "method": getattr(config, "bm25_method", "robertson"),
                "k1": getattr(config, "bm25_k1", 1.2),
                "b": getattr(config, "bm25_b", 0.75),
            }
        else:  # openai
            provider_config = {
                "api_key": config.openai_api_key,
                "model": "text-embedding-3-small",
            }
    else:
        # Dict config (backward compatibility)
        provider = config.get("provider", "openai")
        enable_caching = config.get("enable_caching", True)
        cache_dir = config.get("cache_dir", cache_dir)
        provider_config = {
            k: v
            for k, v in config.items()
            if k not in ["provider", "enable_caching", "cache_size", "cache_dir"]
        }

    return registry.create_embedder(
        provider, provider_config, enable_caching, cache_dir=cache_dir
    )


# For backward compatibility
def create_openai_embedder(
    api_key: str,
    model: str = "text-embedding-3-small",
    enable_caching: bool = True,
    **kwargs: Any,
) -> Embedder:
    """Create OpenAI embedder with default configuration."""
    config = {
        "provider": "openai",
        "api_key": api_key,
        "model": model,
        "enable_caching": enable_caching,
        **kwargs,
    }
    return create_embedder_from_config(config)


def create_voyage_embedder(
    api_key: str,
    model: str = "voyage-3-lite",
    enable_caching: bool = True,
    **kwargs: Any,
) -> Embedder:
    """Create Voyage AI embedder with default configuration."""
    config = {
        "provider": "voyage",
        "api_key": api_key,
        "model": model,
        "enable_caching": enable_caching,
        **kwargs,
    }
    return create_embedder_from_config(config)


def create_bm25_embedder(
    model_name: str = "bm25",
    method: str = "robertson",
    k1: float = 1.2,
    b: float = 0.75,
    enable_caching: bool = False,  # BM25 has its own caching
    **kwargs: Any,
) -> Embedder:
    """Create BM25 embedder with default configuration."""
    config = {
        "provider": "bm25",
        "model_name": model_name,
        "method": method,
        "k1": k1,
        "b": b,
        "enable_caching": enable_caching,
        **kwargs,
    }
    return create_embedder_from_config(config)
