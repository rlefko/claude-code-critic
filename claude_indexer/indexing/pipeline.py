"""High-performance bulk indexing orchestrator.

This module provides the IndexingPipeline class that coordinates
file discovery, parallel parsing, embedding batching, and vector storage
with progress tracking and resume capability.
"""

import gc
import time
from logging import Logger
from pathlib import Path
from typing import Any

from ..analysis.entities import Entity, EntityChunk, Relation
from ..analysis.parser import ParserRegistry
from ..categorization import FileCategorizationSystem, ProcessingTier
from ..config import IndexerConfig
from ..embeddings.base import Embedder
from ..indexer_logging import get_logger
from ..parallel_processor import ParallelFileProcessor
from ..processing.unified_processor import UnifiedContentProcessor
from ..storage.base import VectorStore
from ..storage.file_cache import FileHashCache
from .batch_optimizer import BatchOptimizer
from .checkpoint import IndexingCheckpoint
from .progress import PipelineProgress
from .types import (
    BatchMetrics,
    BatchResult,
    IndexingPhase,
    PipelineConfig,
    PipelineResult,
    ProgressCallback,
)

# Minimum files for parallel processing
MIN_PARALLEL_BATCH = 100


class IndexingPipeline:
    """High-performance bulk indexing orchestrator.

    Coordinates file discovery, parallel parsing, embedding batching,
    and vector storage with progress tracking and resume capability.

    Features:
        - Parallel file processing (ProcessPoolExecutor)
        - Intelligent batch sizing with memory awareness
        - Progress tracking with ETA
        - Resume capability for interrupted indexing
        - File hash caching to skip unchanged files

    Example:
        >>> pipeline = IndexingPipeline(
        ...     config=PipelineConfig(),
        ...     indexer_config=indexer_config,
        ...     embedder=embedder,
        ...     vector_store=vector_store,
        ...     project_path=Path("/path/to/project"),
        ... )
        >>> result = pipeline.run("my-collection", incremental=True)
        >>> print(f"Indexed {result.files_processed} files")
    """

    def __init__(
        self,
        config: PipelineConfig,
        indexer_config: IndexerConfig,
        embedder: Embedder,
        vector_store: VectorStore,
        project_path: Path,
        logger: Logger | None = None,
    ):
        """Initialize indexing pipeline.

        Args:
            config: Pipeline-specific configuration
            indexer_config: Global indexer configuration
            embedder: Embedding engine with caching
            vector_store: Vector storage backend (Qdrant)
            project_path: Root path of the project to index
            logger: Optional logger instance
        """
        self.config = config
        self.indexer_config = indexer_config
        self.embedder = embedder
        self.vector_store = vector_store
        self.project_path = project_path.resolve()
        self.logger = logger or get_logger()

        # Initialize sub-components
        self.progress = PipelineProgress(logger=self.logger)
        self.checkpoint = IndexingCheckpoint(
            cache_dir=self.project_path / ".index_cache",
            enabled=config.enable_resume,
            logger=self.logger,
        )
        self.batch_optimizer = BatchOptimizer(
            initial_size=config.initial_batch_size,
            max_size=config.max_batch_size,
            memory_threshold_mb=config.memory_threshold_mb,
            logger=self.logger,
        )

        # Lazy-initialized components
        self._parallel_processor: ParallelFileProcessor | None = None
        self._content_processor: UnifiedContentProcessor | None = None
        self._file_cache: FileHashCache | None = None
        self._parser_registry: ParserRegistry | None = None
        self._categorizer: FileCategorizationSystem | None = None
        self._ignore_manager: Any = None

    def _get_parallel_processor(self) -> ParallelFileProcessor | None:
        """Get or create parallel processor."""
        if (
            self._parallel_processor is None
            and self.indexer_config.use_parallel_processing
        ):
            max_workers = (
                self.indexer_config.max_parallel_workers
                if self.indexer_config.max_parallel_workers > 0
                else None
            )
            self._parallel_processor = ParallelFileProcessor(
                max_workers=max_workers,
                memory_limit_mb=self.config.memory_threshold_mb,
                logger=self.logger,
            )
        return self._parallel_processor

    def _get_content_processor(self) -> UnifiedContentProcessor:
        """Get or create content processor."""
        if self._content_processor is None:
            self._content_processor = UnifiedContentProcessor(
                self.vector_store, self.embedder, self.logger
            )
        return self._content_processor

    def _get_file_cache(self, collection_name: str) -> FileHashCache:
        """Get or create file hash cache."""
        if self._file_cache is None:
            self._file_cache = FileHashCache(self.project_path, collection_name)
        return self._file_cache

    def _get_parser_registry(self) -> ParserRegistry:
        """Get or create parser registry."""
        if self._parser_registry is None:
            # Try to use parse cache if available
            parse_cache = None
            try:
                from ..analysis.parse_cache import ParseResultCache

                cache_dir = self.project_path / ".index_cache"
                parse_cache = ParseResultCache(cache_dir)
            except Exception:
                pass
            self._parser_registry = ParserRegistry(
                self.project_path, parse_cache=parse_cache
            )
        return self._parser_registry

    def _get_categorizer(self) -> FileCategorizationSystem:
        """Get or create file categorizer."""
        if self._categorizer is None:
            self._categorizer = FileCategorizationSystem()
        return self._categorizer

    def _get_ignore_manager(self) -> Any:
        """Get or create ignore manager."""
        if self._ignore_manager is None:
            try:
                from ..utils.hierarchical_ignore import HierarchicalIgnoreManager

                self._ignore_manager = HierarchicalIgnoreManager(
                    self.project_path
                ).load()
            except Exception:
                self._ignore_manager = False  # Mark as unavailable
        return self._ignore_manager if self._ignore_manager is not False else None

    def run(
        self,
        collection_name: str,
        files: list[Path] | None = None,
        incremental: bool = True,
        progress_callback: ProgressCallback | None = None,
    ) -> PipelineResult:
        """Execute the indexing pipeline.

        Args:
            collection_name: Target Qdrant collection
            files: Specific files to index (None = discover all)
            incremental: Use file hash cache to skip unchanged
            progress_callback: Optional callback for progress updates

        Returns:
            PipelineResult with metrics and status
        """
        start_time = time.time()
        errors: list[str] = []
        warnings: list[str] = []

        try:
            # Phase 1: File Discovery
            self.progress.set_phase(IndexingPhase.DISCOVERY.value)
            if files is not None:
                all_files = [f for f in files if f.exists()]
            else:
                all_files = self._discover_files()

            if not all_files:
                return PipelineResult(
                    success=True,
                    files_processed=0,
                    files_skipped=0,
                    total_time_seconds=time.time() - start_time,
                    warnings=["No files found to index"],
                )

            # Phase 2: Filter unchanged files
            self.progress.set_phase(IndexingPhase.FILTERING.value)
            if incremental:
                file_cache = self._get_file_cache(collection_name)
                changed_files = file_cache.get_changed_files(all_files)
                files_skipped = len(all_files) - len(changed_files)
                self.progress.update_discovery(
                    files_found=len(all_files),
                    files_filtered=files_skipped,
                )
            else:
                changed_files = all_files
                files_skipped = 0

            if not changed_files:
                return PipelineResult(
                    success=True,
                    files_processed=0,
                    files_skipped=files_skipped,
                    total_time_seconds=time.time() - start_time,
                    warnings=["All files unchanged, nothing to index"],
                )

            # Phase 3: Create batches
            batches = self._create_batches(changed_files)
            total_batches = len(batches)

            # Initialize progress and checkpoint
            self.progress.start(
                total_files=len(changed_files),
                total_batches=total_batches,
                callback=progress_callback,
            )

            self.checkpoint.create(
                collection_name=collection_name,
                project_path=self.project_path,
                all_files=changed_files,
                config=self.config,
            )

            # Phase 4: Process batches
            all_entities: list[Entity] = []
            total_files_processed = 0
            total_files_failed = 0

            for batch_index, batch in enumerate(batches):
                batch_result = self._process_batch(
                    batch=batch,
                    collection_name=collection_name,
                    batch_index=batch_index,
                )

                # Update totals
                total_files_processed += batch_result.files_processed
                total_files_failed += batch_result.files_failed
                all_entities.extend([])  # Entities stored in batch
                errors.extend(batch_result.errors)

                # Update checkpoint
                processed_paths = [Path(p) for p in batch_result.processed_files]
                failed_paths = [Path(p) for p in batch_result.failed_files]
                self.checkpoint.update_batch(
                    processed_files=processed_paths,
                    failed_files=failed_paths,
                    batch_index=batch_index,
                    entities=batch_result.entities_created,
                    relations=batch_result.relations_created,
                    chunks=batch_result.implementation_chunks,
                )

                # Save checkpoint periodically
                if (batch_index + 1) % max(
                    1,
                    self.config.checkpoint_interval
                    // self.batch_optimizer.current_size,
                ) == 0:
                    self.checkpoint.save()

                # Record batch metrics for optimizer
                metrics = BatchMetrics(
                    batch_size=len(batch),
                    processing_time_ms=batch_result.total_time_ms,
                    memory_delta_mb=0.0,  # Calculated in batch_optimizer
                    error_count=batch_result.files_failed,
                )
                self.batch_optimizer.record_batch(metrics)

                # Garbage collection between batches
                gc.collect()

            # Update file cache with processed files
            if incremental:
                file_cache = self._get_file_cache(collection_name)
                file_cache.update_batch(
                    [
                        Path(f)
                        for f in self.checkpoint.get_state().processed_files
                        if self.checkpoint.get_state()
                    ]
                    if self.checkpoint.get_state()
                    else []
                )

            # Clear checkpoint on success
            self.checkpoint.clear(collection_name)

            # Finish progress
            final_state = self.progress.finish(success=True)

            return PipelineResult(
                success=True,
                files_processed=total_files_processed,
                files_skipped=files_skipped,
                files_failed=total_files_failed,
                entities_created=final_state.entities_created,
                relations_created=final_state.relations_created,
                implementation_chunks=final_state.chunks_created,
                total_time_seconds=time.time() - start_time,
                errors=errors,
                warnings=warnings,
                batch_count=total_batches,
                cache_stats=(
                    self._get_file_cache(collection_name).get_stats()
                    if incremental
                    else {}
                ),
            )

        except Exception as e:
            self.logger.error(f"Pipeline failed: {e}")
            self.checkpoint.save()  # Save checkpoint on failure
            self.progress.finish(success=False)

            return PipelineResult(
                success=False,
                files_processed=0,
                total_time_seconds=time.time() - start_time,
                errors=[str(e)],
            )

    def resume(
        self,
        collection_name: str,
        progress_callback: ProgressCallback | None = None,
    ) -> PipelineResult:
        """Resume from the latest checkpoint.

        Args:
            collection_name: Target collection
            progress_callback: Optional progress callback

        Returns:
            PipelineResult from resumed execution
        """
        # Check for existing checkpoint
        checkpoint_state = self.checkpoint.load(collection_name)
        if checkpoint_state is None:
            return PipelineResult(
                success=False,
                errors=["No valid checkpoint found to resume from"],
            )

        # Get pending files
        pending_files = self.checkpoint.get_pending_files(self.project_path)
        if not pending_files:
            # All files were processed
            self.checkpoint.clear(collection_name)
            return PipelineResult(
                success=True,
                files_processed=len(checkpoint_state.processed_files),
                warnings=["Resume: All files already processed"],
            )

        self.logger.info(
            f"Resuming from checkpoint: {len(checkpoint_state.processed_files)} "
            f"processed, {len(pending_files)} pending"
        )

        # Run pipeline with pending files (skip filter since checkpoint tracks state)
        return self.run(
            collection_name=collection_name,
            files=pending_files,
            incremental=False,  # Don't re-check, checkpoint is source of truth
            progress_callback=progress_callback,
        )

    def _discover_files(self) -> list[Path]:
        """Discover all indexable files in the project.

        Returns:
            List of file paths to consider for indexing
        """
        files: list[Path] = []
        ignore_manager = self._get_ignore_manager()

        # Get include patterns from config
        include_patterns = self.indexer_config.include_patterns or ["*.py"]

        for pattern in include_patterns:
            for file_path in self.project_path.rglob(pattern.lstrip("*")):
                if not file_path.is_file():
                    continue

                # Check size limit
                try:
                    if file_path.stat().st_size > self.indexer_config.max_file_size:
                        continue
                except OSError:
                    continue

                # Check ignore patterns
                if ignore_manager:
                    try:
                        rel_path = file_path.relative_to(self.project_path)
                        if ignore_manager.should_ignore(str(rel_path)):
                            continue
                    except ValueError:
                        continue
                else:
                    # Fallback to config exclude patterns
                    rel_path = str(file_path.relative_to(self.project_path))
                    if self._matches_exclude(rel_path):
                        continue

                files.append(file_path)

        return sorted(files)

    def _matches_exclude(self, rel_path: str) -> bool:
        """Check if path matches any exclude pattern.

        Args:
            rel_path: Relative path to check

        Returns:
            True if path should be excluded
        """
        import fnmatch

        for pattern in self.indexer_config.exclude_patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            # Also check against directory components
            if "/" in pattern or "\\" in pattern:
                if fnmatch.fnmatch(rel_path, pattern):
                    return True
            else:
                # Check against any path component
                for component in rel_path.split("/"):
                    if fnmatch.fnmatch(component, pattern):
                        return True
        return False

    def _create_batches(self, files: list[Path]) -> list[list[Path]]:
        """Create optimized batches based on file tiers.

        Args:
            files: Files to batch

        Returns:
            List of file batches
        """
        categorizer = self._get_categorizer()
        batch_size = self.batch_optimizer.get_batch_size()

        # Categorize files by tier
        light_files: list[Path] = []
        standard_files: list[Path] = []
        deep_files: list[Path] = []

        for file_path in files:
            tier = categorizer.categorize_file(file_path)
            if tier == ProcessingTier.LIGHT:
                light_files.append(file_path)
            elif tier == ProcessingTier.DEEP:
                deep_files.append(file_path)
            else:
                standard_files.append(file_path)

        # Create batches, prioritizing light files
        batches: list[list[Path]] = []
        all_sorted = light_files + standard_files + deep_files

        for i in range(0, len(all_sorted), batch_size):
            batches.append(all_sorted[i : i + batch_size])

        return batches

    def _process_batch(
        self,
        batch: list[Path],
        collection_name: str,
        batch_index: int,
    ) -> BatchResult:
        """Process a single batch of files.

        Args:
            batch: Files in this batch
            collection_name: Target collection
            batch_index: Index of this batch

        Returns:
            BatchResult with metrics
        """
        start_time = time.time()
        result = BatchResult(batch_index=batch_index)

        # Get tier stats for progress
        categorizer = self._get_categorizer()
        tier_stats: dict[str, int] = {"light": 0, "standard": 0, "deep": 0}
        for f in batch:
            tier = categorizer.categorize_file(f)
            if tier == ProcessingTier.LIGHT:
                tier_stats["light"] += 1
            elif tier == ProcessingTier.DEEP:
                tier_stats["deep"] += 1
            else:
                tier_stats["standard"] += 1

        self.progress.update_batch(
            batch_index=batch_index,
            files_in_batch=len(batch),
            tier_stats=tier_stats,
        )

        # Parse files
        parse_start = time.time()
        entities: list[Entity] = []
        relations: list[Relation] = []
        implementation_chunks: list[EntityChunk] = []
        processed_files: list[str] = []
        failed_files: list[str] = []

        # Use parallel processing for large batches
        parallel_processor = self._get_parallel_processor()
        if parallel_processor and len(batch) >= MIN_PARALLEL_BATCH:
            try:
                parse_result = parallel_processor.process_files_parallel(
                    batch, collection_name, self.indexer_config
                )
                for file_result in parse_result:
                    if file_result.get("success", False):
                        entities.extend(
                            self._dict_to_entities(file_result.get("entities", []))
                        )
                        relations.extend(
                            self._dict_to_relations(file_result.get("relations", []))
                        )
                        implementation_chunks.extend(
                            self._dict_to_chunks(
                                file_result.get("implementation_chunks", [])
                            )
                        )
                        processed_files.append(file_result.get("file_path", ""))
                    else:
                        failed_files.append(file_result.get("file_path", ""))
                        result.errors.append(
                            f"Failed to parse {file_result.get('file_path')}: "
                            f"{file_result.get('error', 'Unknown error')}"
                        )
            except Exception as e:
                self.logger.warning(f"Parallel processing failed, falling back: {e}")
                # Fall through to sequential processing
                parallel_processor = None

        # Sequential processing (fallback or small batches)
        if not parallel_processor or len(batch) < MIN_PARALLEL_BATCH:
            parser_registry = self._get_parser_registry()
            for file_path in batch:
                try:
                    file_entities, file_relations, file_chunks = (
                        parser_registry.parse_file(file_path)
                    )
                    entities.extend(file_entities)
                    relations.extend(file_relations)
                    implementation_chunks.extend(file_chunks)
                    processed_files.append(str(file_path))
                    self.progress.update_file(file_path, status="complete")
                except Exception as e:
                    failed_files.append(str(file_path))
                    result.errors.append(f"Failed to parse {file_path}: {e}")
                    self.logger.warning(f"Parse error for {file_path}: {e}")

        result.parse_time_ms = (time.time() - parse_start) * 1000

        # Store vectors
        store_start = time.time()
        if entities or relations or implementation_chunks:
            content_processor = self._get_content_processor()

            # Build changed entity IDs set
            changed_entity_ids = {
                f"{e.file_path}::{e.name}" for e in entities if e.file_path
            }

            processing_result = content_processor.process_all_content(
                collection_name=collection_name,
                entities=entities,
                relations=relations,
                implementation_chunks=implementation_chunks,
                changed_entity_ids=changed_entity_ids,
            )

            if not processing_result.success:
                result.errors.append(
                    f"Storage failed: {processing_result.error_message}"
                )

        result.store_time_ms = (time.time() - store_start) * 1000

        # Update result metrics
        result.files_processed = len(processed_files)
        result.files_failed = len(failed_files)
        result.entities_created = len(entities)
        result.relations_created = len(relations)
        result.implementation_chunks = len(implementation_chunks)
        result.processed_files = processed_files
        result.failed_files = failed_files

        # Update progress
        self.progress.complete_batch(
            batch_index=batch_index,
            entities=len(entities),
            relations=len(relations),
            chunks=len(implementation_chunks),
            parse_time_ms=result.parse_time_ms,
            embed_time_ms=result.embed_time_ms,
            store_time_ms=result.store_time_ms,
            files_processed=len(processed_files),
        )

        total_time = (time.time() - start_time) * 1000
        self.logger.debug(
            f"Batch {batch_index + 1}: {len(processed_files)} files, "
            f"{len(entities)} entities, {len(relations)} relations, "
            f"{total_time:.0f}ms"
        )

        return result

    def _dict_to_entities(self, dicts: list[dict]) -> list[Entity]:
        """Convert dictionary representations to Entity objects.

        Args:
            dicts: List of entity dictionaries from parallel processing

        Returns:
            List of Entity objects
        """
        from ..analysis.entities import Entity, EntityType

        entities = []
        for d in dicts:
            try:
                entity_type = EntityType(d.get("entity_type", "function"))
                entity = Entity(
                    name=d.get("name", ""),
                    entity_type=entity_type,
                    file_path=d.get("file_path"),
                    start_line=d.get("start_line", 0),
                    end_line=d.get("end_line", 0),
                    docstring=d.get("docstring"),
                    signature=d.get("signature"),
                    code=d.get("code"),
                    parent_name=d.get("parent_name"),
                    metadata=d.get("metadata", {}),
                )
                entities.append(entity)
            except Exception:
                continue
        return entities

    def _dict_to_relations(self, dicts: list[dict]) -> list[Relation]:
        """Convert dictionary representations to Relation objects.

        Args:
            dicts: List of relation dictionaries from parallel processing

        Returns:
            List of Relation objects
        """
        from ..analysis.entities import Relation, RelationType

        relations = []
        for d in dicts:
            try:
                relation_type = RelationType(d.get("relation_type", "calls"))
                relation = Relation(
                    source=d.get("source", ""),
                    target=d.get("target", ""),
                    relation_type=relation_type,
                    file_path=d.get("file_path"),
                    line_number=d.get("line_number"),
                    metadata=d.get("metadata", {}),
                )
                relations.append(relation)
            except Exception:
                continue
        return relations

    def _dict_to_chunks(self, dicts: list[dict]) -> list[EntityChunk]:
        """Convert dictionary representations to EntityChunk objects.

        Args:
            dicts: List of chunk dictionaries from parallel processing

        Returns:
            List of EntityChunk objects
        """
        from ..analysis.entities import EntityChunk

        chunks = []
        for d in dicts:
            try:
                chunk = EntityChunk(
                    entity_name=d.get("entity_name", ""),
                    chunk_type=d.get("chunk_type", "implementation"),
                    content=d.get("content", ""),
                    file_path=d.get("file_path"),
                    start_line=d.get("start_line", 0),
                    end_line=d.get("end_line", 0),
                    metadata=d.get("metadata", {}),
                )
                chunks.append(chunk)
            except Exception:
                continue
        return chunks
