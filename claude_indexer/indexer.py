"""Core indexing orchestrator - stateless domain service."""

import contextlib
import fnmatch
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .analysis.entities import Entity, EntityChunk, Relation
from .analysis.parser import ParserRegistry
from .categorization import FileCategorizationSystem
from .config import IndexerConfig
from .embeddings.base import Embedder
from .git import ChangeSet, GitChangeDetector
from .indexer_logging import get_logger
from .parallel_processor import ParallelFileProcessor
from .storage.base import VectorStore

logger = get_logger()

# Import HierarchicalIgnoreManager for .claudeignore support
try:
    from .utils.hierarchical_ignore import HierarchicalIgnoreManager

    HIERARCHICAL_IGNORE_AVAILABLE = True
except ImportError:
    HIERARCHICAL_IGNORE_AVAILABLE = False
    logger.debug("HierarchicalIgnoreManager not available, using config patterns only")

# Legacy import for backward compatibility
try:
    # Add utils directory to path if not already there
    utils_path = Path(__file__).parent.parent / "utils"
    if str(utils_path) not in sys.path:
        sys.path.insert(0, str(utils_path))
    from exclusion_manager import ExclusionManager

    EXCLUSION_MANAGER_AVAILABLE = True
except ImportError:
    EXCLUSION_MANAGER_AVAILABLE = False
    logger.debug("ExclusionManager not available, using config patterns only")


def format_change(current: int, previous: int) -> str:
    """Format a change value with +/- indicator."""
    change = current - previous
    if change > 0:
        return f"{current} (+{change})"
    elif change < 0:
        return f"{current} ({change})"
    else:
        return f"{current} (+0)" if previous > 0 else str(current)


@dataclass
class IndexingResult:
    """Result of an indexing operation."""

    success: bool
    operation: str  # "full", "incremental", "single_file"

    # Metrics
    files_processed: int = 0
    files_failed: int = 0
    entities_created: int = 0
    relations_created: int = 0
    implementation_chunks_created: int = 0  # Progressive disclosure metric
    processing_time: float = 0.0

    # Cost tracking
    total_tokens: int = 0
    total_cost_estimate: float = 0.0
    embedding_requests: int = 0

    # File tracking
    processed_files: list[str] | None = None
    failed_files: list[str] | None = None

    # Errors and warnings
    errors: list[str] | None = None
    warnings: list[str] | None = None

    def __post_init__(self) -> None:
        if self.processed_files is None:
            self.processed_files = []
        if self.failed_files is None:
            self.failed_files = []
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []

    @property
    def total_items(self) -> int:
        """Total entities and relations created."""
        return self.entities_created + self.relations_created

    @property
    def success_rate(self) -> float:
        """File processing success rate."""
        total = self.files_processed + self.files_failed
        if total == 0:
            return 1.0
        return self.files_processed / total

    @property
    def duration(self) -> float:
        """Alias for processing_time for backward compatibility."""
        return self.processing_time


@dataclass
class GitMetaContext:
    """Context information from Git+Meta content analysis."""

    changed_entity_ids: set[str]
    unchanged_count: int
    should_process: bool
    global_entities: set[str] | None = None

    @classmethod
    def empty(cls) -> "GitMetaContext":
        """Create empty context for cases where Git+Meta is not applicable."""
        return cls(
            changed_entity_ids=set(),
            unchanged_count=0,
            should_process=True,
            global_entities=None,
        )


class CoreIndexer:
    """Stateless core indexing service orchestrating all components."""

    def __init__(
        self,
        config: IndexerConfig,
        embedder: Embedder,
        vector_store: VectorStore,
        project_path: Path,
    ):
        self.config = config
        self.embedder = embedder
        self.vector_store = vector_store
        self.project_path = project_path
        self.logger = get_logger()

        # Initialize file categorization system
        self.categorizer = FileCategorizationSystem()

        # Initialize parallel processor if enabled
        self.parallel_processor = None
        if config.use_parallel_processing:
            max_workers = (
                config.max_parallel_workers if config.max_parallel_workers > 0 else None
            )
            self.parallel_processor = ParallelFileProcessor(
                max_workers=max_workers,
                memory_limit_mb=2000,  # Same as main process limit
                logger=self.logger,
            )
            self.logger.info(
                f"🚀 Parallel processing enabled with {self.parallel_processor.current_workers} workers"
            )

        # Initialize hierarchical ignore manager for .claudeignore support
        self.ignore_manager = None
        if HIERARCHICAL_IGNORE_AVAILABLE:
            try:
                self.ignore_manager = HierarchicalIgnoreManager(project_path).load()
                stats = self.ignore_manager.get_stats()
                self.logger.debug(
                    f"Hierarchical ignore loaded: {stats['total_patterns']} patterns "
                    f"(universal: {stats['universal_patterns']}, "
                    f"global: {stats['global_patterns']}, "
                    f"project: {stats['project_patterns']})"
                )
            except Exception as e:
                self.logger.warning(f"Could not load hierarchical ignore: {e}")
                self.ignore_manager = None

        # Fallback: Enhance exclusion patterns with legacy ExclusionManager
        if self.ignore_manager is None and EXCLUSION_MANAGER_AVAILABLE:
            try:
                exclusion_mgr = ExclusionManager(project_path)
                enhanced_patterns = exclusion_mgr.get_all_patterns()

                # Merge with config patterns (config takes precedence for manual overrides)
                all_patterns = list(
                    dict.fromkeys(enhanced_patterns + self.config.exclude_patterns)
                )

                # Update config with enhanced patterns
                self.config.exclude_patterns = all_patterns

                self.logger.debug(
                    f"Legacy exclusions: {len(enhanced_patterns)} patterns "
                    f"(.gitignore + .claudeignore + universal defaults + binaries)"
                )
            except Exception as e:
                self.logger.warning(f"Could not load enhanced exclusions: {e}")

        # Initialize parse cache for skipping re-parsing of unchanged files
        self._parse_cache = None
        try:
            from .analysis.parse_cache import ParseResultCache

            cache_dir = project_path / ".index_cache"
            self._parse_cache = ParseResultCache(cache_dir)
            self.logger.debug(
                f"Parse cache initialized with {len(self._parse_cache)} entries"
            )
        except Exception as e:
            self.logger.debug(f"Parse cache initialization failed: {e}")

        # Initialize parser registry with optional parse cache
        self.parser_registry = ParserRegistry(
            project_path, parse_cache=self._parse_cache
        )

        # Initialize session cost tracking
        self._session_cost_data: dict[str, int | float] = {
            "tokens": 0,
            "cost": 0.0,
            "requests": 0,
        }

        # Initialize embedding metrics tracking
        self._embedding_metrics: dict[str, int | float] = {
            "metadata_embeddings": 0,
            "implementation_embeddings": 0,
            "relation_embeddings": 0,
            "total_embeddings": 0,
            "embeddings_reused": 0,
            "relation_batch_size": 500,  # Track optimized batch size
            "avg_embeddings_per_entity": 0.0,
        }

        # Pipeline support (lazy-initialized)
        self._pipeline: Any = None

    def _get_pipeline(self) -> Any:
        """Get or create the IndexingPipeline for bulk operations.

        Returns:
            IndexingPipeline instance with resume capability
        """
        if self._pipeline is None:
            from .indexing import IndexingPipeline, PipelineConfig

            self._pipeline = IndexingPipeline(
                config=PipelineConfig(
                    initial_batch_size=self.config.initial_batch_size,
                    max_batch_size=self.config.batch_size,
                    ramp_up_enabled=self.config.batch_size_ramp_up,
                    parallel_threshold=100,  # MIN_PARALLEL_BATCH
                    memory_threshold_mb=2000,
                    checkpoint_interval=50,
                    enable_resume=True,
                    max_parallel_workers=self.config.max_parallel_workers,
                ),
                indexer_config=self.config,
                embedder=self.embedder,
                vector_store=self.vector_store,
                project_path=self.project_path,
                logger=self.logger,
            )
        return self._pipeline

    def index_project_with_pipeline(
        self,
        collection_name: str,
        include_tests: bool = False,
        verbose: bool = False,
        resume: bool = False,
    ) -> IndexingResult:
        """Index project using the new IndexingPipeline with resume capability.

        This method provides an alternative to index_project() with:
        - Resume capability for interrupted indexing
        - Unified progress tracking
        - Checkpoint-based recovery

        Args:
            collection_name: Target Qdrant collection
            include_tests: Whether to include test files
            verbose: Enable verbose logging
            resume: Attempt to resume from checkpoint

        Returns:
            IndexingResult with metrics
        """
        pipeline = self._get_pipeline()

        # Ensure collection exists
        try:
            if not self.vector_store.collection_exists(collection_name):
                if verbose:
                    self.logger.info(f"Creating collection '{collection_name}'...")
                vector_size = 512  # Voyage-3-lite default
                self.vector_store.backend.ensure_collection(
                    collection_name, vector_size
                )
        except Exception as e:
            if verbose:
                self.logger.debug(f"Collection check/creation: {e}")

        # Run or resume pipeline
        if resume:
            pipeline_result = pipeline.resume(collection_name)
        else:
            pipeline_result = pipeline.run(
                collection_name=collection_name,
                incremental=True,  # Use file cache for unchanged detection
            )

        # Convert PipelineResult to IndexingResult for API compatibility
        return self._convert_pipeline_result(pipeline_result)

    def _convert_pipeline_result(self, pipeline_result: Any) -> IndexingResult:
        """Convert PipelineResult to IndexingResult for backward compatibility.

        Args:
            pipeline_result: Result from IndexingPipeline

        Returns:
            IndexingResult with equivalent data
        """
        return IndexingResult(
            success=pipeline_result.success,
            operation="incremental" if pipeline_result.files_skipped > 0 else "full",
            files_processed=pipeline_result.files_processed,
            files_failed=pipeline_result.files_failed,
            entities_created=pipeline_result.entities_created,
            relations_created=pipeline_result.relations_created,
            implementation_chunks_created=pipeline_result.implementation_chunks,
            processing_time=pipeline_result.total_time_seconds,
            errors=pipeline_result.errors,
            warnings=pipeline_result.warnings,
        )

    def _create_batch_callback(self, collection_name: str) -> Any:
        """Create a callback function for batch processing during streaming."""

        def batch_callback(
            entities: list[Entity], relations: list[Relation], chunks: list[EntityChunk]
        ) -> bool:
            """Process a batch of entities, relations, and chunks immediately."""
            try:
                # Use unified Git+Meta setup
                git_meta = self._prepare_git_meta_context(collection_name, entities)
                # Use existing _store_vectors method for immediate processing
                success = self._store_vectors(
                    collection_name,
                    entities,
                    relations,
                    chunks,
                    git_meta.changed_entity_ids,
                )
                return success
            except Exception as e:
                self.logger.error(f"❌ Batch processing failed: {e}")
                return False

        return batch_callback

    def _populate_signature_table(
        self,
        collection_name: str,
        entities: list[Entity],
        implementation_chunks: list[EntityChunk] | None,
    ) -> None:
        """Populate signature hash table for O(1) duplicate detection.

        Called during indexing to enable Memory Guard Tier 2 fast path.
        Signature tables are stored per-collection for multi-repo support.

        Args:
            collection_name: Collection name for cache organization
            entities: List of parsed entities
            implementation_chunks: List of implementation chunks with code content
        """
        if not implementation_chunks:
            return

        try:
            from utils.signature_table_manager import SignatureTableManager

            sig_manager = SignatureTableManager.get_instance(
                self.project_path / ".index_cache"
            )

            # Build entity lookup for type info
            entity_map = {e.name: e for e in entities}

            # Process implementation chunks
            for chunk in implementation_chunks:
                if chunk.chunk_type != "implementation":
                    continue

                entity = entity_map.get(chunk.entity_name)
                if not entity:
                    continue

                # Only add signatures for function/class/method entities
                entity_type = entity.entity_type.value
                if entity_type not in ("function", "class", "method"):
                    continue

                file_path = str(entity.file_path) if entity.file_path else ""
                sig_manager.update_from_chunk(
                    collection_name,
                    chunk.content,
                    chunk.entity_name,
                    entity_type,
                    file_path,
                )

            # Persist changes
            sig_manager.save_all()

        except ImportError:
            # Memory Guard not installed - silently skip
            pass
        except Exception as e:
            # Non-critical - don't break indexing, just log
            self.logger.debug(f"Signature table update failed: {e}")

    def _parse_light_tier(self, file_path: Path, global_entity_names: set[str]) -> Any:
        """
        Light parsing for generated files and type definitions.
        Extracts only metadata and type definitions without relations or deep analysis.
        """
        from .analysis.entities import Entity, EntityType
        from .analysis.parser import ParserResult

        try:
            # Get basic file info
            file_path.relative_to(self.project_path)

            # Create a simple entity for the file
            entity = Entity(
                name=file_path.stem,
                entity_type=EntityType.FILE,  # Use EntityType enum
                observations=[
                    f"Generated/type definition file: {file_path.suffix}",
                    f"Size: {file_path.stat().st_size} bytes",
                    "Light processing applied - relations skipped",
                ],
                file_path=file_path,
                line_number=1,
            )

            # Return simplified parse result - no 'success' or 'language' fields
            return ParserResult(
                file_path=file_path,
                entities=[entity],
                relations=[],  # No relations for light tier
                implementation_chunks=[],  # No implementations for light tier
                errors=[],  # Empty errors means success=True
                warnings=[],
            )
        except Exception as e:
            self.logger.debug(f"Light parsing failed for {file_path}: {e}")
            return ParserResult(
                file_path=file_path,
                entities=[],
                relations=[],
                implementation_chunks=[],
                errors=[str(e)],  # Add error to errors list
                warnings=[],
            )

    def _should_use_batch_processing(self, file_path: Path) -> bool:
        """Determine if a file should use batch processing during parsing."""
        try:
            # Only JSON files with content_only mode should use batch processing
            if file_path.suffix != ".json":
                return False

            # Check if this is a project that uses content_only mode for JSON
            # Use the same config loading approach as ParserRegistry
            from .config.project_config import ProjectConfigManager

            config_manager = ProjectConfigManager(self.project_path)
            if not config_manager.exists:
                return False

            project_config = config_manager.load()

            # Check if content_only is enabled for JSON parsing
            self.logger.debug(
                f"🔍 Batch check for {file_path.name}: project_config type = {type(project_config)}"
            )
            if (
                hasattr(project_config, "indexing")
                and project_config.indexing
                and hasattr(project_config.indexing, "parser_config")
                and project_config.indexing.parser_config
            ):
                parser_config = project_config.indexing.parser_config
                if isinstance(parser_config, dict):
                    json_parser_config = parser_config.get("json", None)
                else:
                    # Handle Pydantic model attributes
                    json_parser_config = getattr(parser_config, "json", None)
                self.logger.debug(f"🔍 Found JSON config: {json_parser_config}")
                if json_parser_config and getattr(
                    json_parser_config, "content_only", False
                ):
                    self.logger.debug(
                        f"✅ Batch processing enabled for {file_path.name}"
                    )
                    return True

            self.logger.debug(f"❌ Batch processing disabled for {file_path.name}")
            return False

        except Exception as e:
            self.logger.debug(
                f"❌ Batch processing check failed for {file_path.name}: {e}"
            )
            return False

    def _prepare_git_meta_context(
        self, collection_name: str, entities: list[Entity]
    ) -> GitMetaContext:
        """Unified Git+Meta setup for ALL indexing flows."""

        # Critical error check - vector store should always be available in production
        if not self.vector_store:
            self.logger.error(
                "🚨 CRITICAL: Vector store is None - Git+Meta features disabled! This is a major bug if not in test environment."
            )
            self.logger.error(
                "🚨 Indexing will continue with degraded functionality (no deduplication, no incremental updates)"
            )
            return GitMetaContext.empty()

        # Global entity caching (extracted from duplication)
        if not hasattr(self, "_cached_global_entities"):
            self._cached_global_entities = self._get_all_entity_names(collection_name)
            if self._cached_global_entities:
                self.logger.debug(
                    f"🌐 Cached {len(self._cached_global_entities)} global entities for cross-file relation filtering"
                )

        # Content hash analysis (extracted from index_single_file) with safety checks
        unchanged_entities = 0
        if (
            entities
            and hasattr(self.vector_store, "collection_exists")
            and self.vector_store.collection_exists(collection_name)
        ):
            for entity in entities:
                try:
                    # FIX: Use file content hash instead of entity metadata hash
                    # This prevents infinite loops when file content changes but entity metadata stays same
                    content_hash = (
                        self._get_file_hash(entity.file_path)
                        if entity.file_path
                        else ""
                    )

                    # Robustness: Validate hash and vector store capability before checking
                    if not content_hash:
                        self.logger.debug(
                            f"🔄 Git+Meta: Empty content hash for {entity.name}, treating as changed"
                        )
                        continue

                    if not hasattr(self.vector_store, "check_content_exists"):
                        self.logger.debug(
                            "🔄 Git+Meta: Vector store doesn't support content checking, treating as changed"
                        )
                        continue

                    # Check if content exists with fallback handling
                    exists = self.vector_store.check_content_exists(  # type: ignore[attr-defined]
                        collection_name, content_hash
                    )
                    if exists:
                        unchanged_entities += 1
                        self.logger.debug(
                            f"🔄 Git+Meta: Content unchanged for {entity.name}"
                        )
                    else:
                        self.logger.debug(
                            f"🔄 Git+Meta: Content changed for {entity.name}"
                        )

                except Exception as e:
                    self.logger.debug(
                        f"🔄 Git+Meta: Content check failed for {entity.name}: {e}"
                    )
                    # Robustness: Fallback to processing as "changed" (safe default)
                    self.logger.debug(
                        f"🔄 Git+Meta: Falling back to processing {entity.name} as changed"
                    )

        # Changed entity IDs computation (unified from both patterns)
        changed_entity_ids = (
            {
                (
                    f"{entity.file_path}::{entity.name}"
                    if entity.file_path
                    else entity.name
                )
                for entity in entities
            }
            if entities
            else set()
        )

        # Efficiency decision
        should_process = unchanged_entities < len(entities) if entities else True

        # Log efficiency gains if applicable
        if unchanged_entities > 0:
            self.logger.info(
                f"⚡ Git+Meta: {unchanged_entities}/{len(entities)} entities unchanged"
            )

        return GitMetaContext(
            changed_entity_ids=changed_entity_ids,
            unchanged_count=unchanged_entities,
            should_process=should_process,
            global_entities=self._cached_global_entities,
        )

    def _inject_parser_configs(self) -> None:
        """Inject project-specific parser configurations."""
        for _parser in self.parser_registry._parsers:
            # TODO: Fix config_loader access - not available in current context
            # parser_name = parser.__class__.__name__.lower().replace("parser", "")
            # parser_config = self.config_loader.get_parser_config(parser_name)
            # if parser_config and hasattr(parser, "update_config"):
            #     parser.update_config(parser_config)
            pass

    def _get_state_directory(self) -> Path:
        """Get state directory (configurable for test isolation)."""
        # Use configured state directory if provided (for tests)
        if self.config.state_directory is not None:
            state_dir = self.config.state_directory
        else:
            # Default to project-local state directory
            state_dir = self.project_path / ".claude-indexer"

        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir

    def _get_state_file(self, collection_name: str) -> Path:
        """Get collection-specific state file with simple naming."""
        # Simple, predictable naming: just use collection name
        filename = f"{collection_name}.json"
        new_state_file = self._get_state_directory() / filename

        # Auto-migrate from global state directory if exists
        if not new_state_file.exists():
            old_global_state_file = Path.home() / ".claude-indexer" / "state" / filename
            if old_global_state_file.exists():
                try:
                    # Copy state file content to new location
                    with open(old_global_state_file) as old_f:
                        state_data = old_f.read()
                    with open(new_state_file, "w") as new_f:
                        new_f.write(state_data)

                    # Remove old state file
                    old_global_state_file.unlink()
                    self.logger.info(
                        f"Migrated state file: {old_global_state_file} -> {new_state_file}"
                    )
                except Exception as e:
                    self.logger.warning(
                        f"Failed to migrate state file {old_global_state_file}: {e}"
                    )

        return new_state_file

    @property
    def state_file(self) -> Path:
        """Default state file for backward compatibility with tests."""
        return self._get_state_file("default")

    def index_project(
        self, collection_name: str, include_tests: bool = False, verbose: bool = False
    ) -> IndexingResult:
        """Index an entire project with automatic incremental detection."""
        start_time = time.time()

        # Initialize collection if it doesn't exist to avoid warnings
        # Use ensure_collection to properly configure both dense and sparse vectors
        # Note: If we can't determine the embedder dimension, we skip pre-creation
        # and let upsert_points create the collection with the correct dimension
        try:
            if not self.vector_store.collection_exists(collection_name):
                # Get vector size from embedder if available
                vector_size = None
                if self.embedder:
                    if hasattr(self.embedder, "dimension"):
                        vector_size = self.embedder.dimension
                    elif hasattr(self.embedder, "get_model_info"):
                        model_info = self.embedder.get_model_info()
                        if isinstance(model_info, dict) and "dimension" in model_info:
                            vector_size = model_info["dimension"]

                # Only pre-create if we know the dimension
                if vector_size:
                    if verbose:
                        self.logger.info(
                            f"Creating collection '{collection_name}' with sparse vector support..."
                        )
                    # Handle both CachingVectorStore (has .backend) and QdrantStore (is the backend)
                    backend = getattr(self.vector_store, "backend", self.vector_store)
                    backend.ensure_collection(collection_name, vector_size)
                    if verbose:
                        self.logger.info(
                            f"✅ Collection '{collection_name}' created with hybrid search support"
                        )
        except Exception as e:
            # If collection already exists or any other error, continue
            if verbose:
                self.logger.debug(f"Collection check/creation: {e}")

        # Auto-detect incremental mode based on state file existence (like watcher pattern)
        state_file = self._get_state_file(collection_name)
        incremental = state_file.exists()

        if verbose:
            logger.info("🔍 === INDEXING MODE DETECTION ===")
            logger.info(f"   Collection: {collection_name}")
            logger.info(f"   State file exists: {incremental}")
            logger.info(f"   Mode: {'INCREMENTAL' if incremental else 'FULL'}")
            logger.info("   Orphan cleanup will run: YES (both modes)")

        result = IndexingResult(
            success=True, operation="incremental" if incremental else "full"
        )

        try:
            # Find files to process
            if incremental:
                files_to_process, deleted_files = self._find_changed_files(
                    include_tests, collection_name
                )

                # Handle deleted files using consolidated function
                if deleted_files:
                    self._handle_deleted_files(collection_name, deleted_files, verbose)
                    # State cleanup happens automatically in _update_state when no files_to_process
                    if result.warnings is not None:
                        result.warnings.append(
                            f"Handled {len(deleted_files)} deleted files"
                        )
            else:
                files_to_process = self._find_all_files(include_tests)
                deleted_files = []

            if not files_to_process:
                # Even if no files to process, update state to remove deleted files
                if incremental and deleted_files:
                    # Use incremental mode to preserve existing files while removing deleted ones
                    self._update_state(
                        [],
                        collection_name,
                        verbose,
                        full_rebuild=False,
                        deleted_files=deleted_files,
                    )
                if result.warnings is not None:
                    result.warnings.append("No files to process")
                result.processing_time = time.time() - start_time
                return result

            if self.logger:
                self.logger.debug(
                    f"Indexing configuration - collection: {collection_name}, path: {self.project_path}"
                )
                self.logger.debug(f"verbose: {verbose}")
                self.logger.debug(f"Include patterns: {self.config.include_patterns}")
                self.logger.debug(f"Exclude patterns: {self.config.exclude_patterns}")
                self.logger.debug(f"🔍   include_tests: {self.config.include_tests}")
                self.logger.debug(f"🔍   max_file_size: {self.config.max_file_size}")
                self.logger.debug(f"🔍   batch_size: {self.config.batch_size}")
                self.logger.debug(
                    f"🔍   parser registry: {type(self.parser_registry).__name__}"
                )
                self.logger.debug(
                    f"🔍   vector_store: {type(self.vector_store).__name__ if self.vector_store else 'None'}"
                )
                self.logger.debug(
                    f"🔍   embedder: {type(self.embedder).__name__ if self.embedder else 'None'}"
                )

            self.logger.info(f"Found {len(files_to_process)} files to process")

            # Analyze file tiers for optimization
            tier_stats = self.categorizer.get_tier_stats(files_to_process)
            self.logger.info(
                f"📂 File categorization: {tier_stats['light']} light / "
                f"{tier_stats['standard']} standard / {tier_stats['deep']} deep files"
            )

            # Process files in batches with progressive disclosure support
            # Use adaptive batch sizing for large projects - start small and ramp up
            if self.config.batch_size_ramp_up and not incremental:
                # For initial indexing, start with smaller batches
                effective_batch_size = self.config.initial_batch_size
                self.logger.info(
                    f"Using adaptive batch sizing: starting with {effective_batch_size}, ramping up to {self.config.batch_size}"
                )
            else:
                # For incremental or when ramp-up is disabled, use full batch size
                effective_batch_size = self.config.batch_size

            all_entities = []
            all_relations = []
            all_implementation_chunks = []
            all_processed_files = []
            successful_batches = 0

            # Add progress tracking and memory monitoring
            total_files = len(files_to_process)
            files_completed = 0
            start_batch_time = time.time()

            # Import memory monitoring
            import gc
            import os

            import psutil

            # Get process for memory monitoring
            process = psutil.Process(os.getpid())
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_threshold_mb = 2000  # Reduce batch size if we exceed 2GB

            for i in range(0, len(files_to_process), effective_batch_size):
                batch = files_to_process[i : i + effective_batch_size]
                batch_num = (i // effective_batch_size) + 1
                # Recalculate total batches based on current effective_batch_size
                remaining_files = len(files_to_process) - i
                total_batches = batch_num + (
                    (remaining_files - len(batch) + effective_batch_size - 1)
                    // effective_batch_size
                    if remaining_files > len(batch)
                    else 0
                )

                # Check memory usage and adjust batch size if needed
                current_memory = process.memory_info().rss / 1024 / 1024  # MB
                current_memory - initial_memory

                if current_memory > memory_threshold_mb and effective_batch_size > 2:
                    old_size = effective_batch_size
                    effective_batch_size = max(
                        2, effective_batch_size // 2
                    )  # Halve batch size, minimum 2
                    self.logger.warning(
                        f"⚠️ High memory usage ({current_memory:.0f}MB), reducing batch size: {old_size} → {effective_batch_size}"
                    )
                    # Force immediate garbage collection
                    gc.collect()

                # Calculate progress percentage
                progress_pct = (
                    (files_completed / total_files * 100) if total_files > 0 else 0
                )
                elapsed_time = time.time() - start_batch_time
                files_per_sec = (
                    files_completed / elapsed_time if elapsed_time > 0 else 0
                )
                eta_seconds = (
                    (total_files - files_completed) / files_per_sec
                    if files_per_sec > 0
                    else 0
                )
                eta_str = (
                    f"{int(eta_seconds // 60)}m {int(eta_seconds % 60)}s"
                    if eta_seconds > 0
                    else "calculating..."
                )

                # Count light tier files in batch
                light_count = sum(
                    1
                    for f in batch
                    if self.categorizer.categorize_file(f).value == "light"
                )
                tier_info = f" ({light_count} light)" if light_count > 0 else ""

                self.logger.info(
                    f"📊 Batch {batch_num}/{total_batches}{tier_info} | "
                    f"Progress: {files_completed}/{total_files} ({progress_pct:.1f}%) | "
                    f"Speed: {files_per_sec:.1f} files/s | "
                    f"ETA: {eta_str} | "
                    f"Memory: {current_memory:.0f}MB | "
                    f"Batch: {effective_batch_size}"
                )

                (
                    batch_entities,
                    batch_relations,
                    batch_implementation_chunks,
                    batch_errors,
                    batch_processed_files,
                ) = self._process_file_batch(batch, collection_name, verbose)

                all_entities.extend(batch_entities)
                all_relations.extend(batch_relations)
                all_implementation_chunks.extend(batch_implementation_chunks)
                all_processed_files.extend(batch_processed_files)
                if result.errors is not None:
                    result.errors.extend(batch_errors)

                # Track failed files properly
                failed_files_in_batch = [
                    str(f) for f in batch if str(f) in batch_errors
                ]
                if result.failed_files is not None:
                    result.failed_files.extend(failed_files_in_batch)

                # Print specific file errors for debugging
                for error_msg in batch_errors:
                    for file_path in batch:
                        if str(file_path) in error_msg:
                            logger.error(
                                f"❌ Error processing file: {file_path} - {error_msg}"
                            )
                            break

                # Update metrics
                batch_successful = len([f for f in batch if str(f) not in batch_errors])
                result.files_processed += batch_successful
                result.files_failed += len(batch_errors)
                files_completed += len(batch)  # Update progress counter

                # Adaptive batch sizing - ramp up after successful batches
                if (
                    self.config.batch_size_ramp_up
                    and not incremental
                    and len(batch_errors) == 0
                ):
                    successful_batches += 1
                    # Ramp up batch size after every 2 successful batches, up to the configured max
                    if (
                        successful_batches % 2 == 0
                        and effective_batch_size < self.config.batch_size
                    ):
                        old_size = effective_batch_size
                        effective_batch_size = min(
                            effective_batch_size * 2, self.config.batch_size
                        )
                        self.logger.info(
                            f"📈 Ramping up batch size: {old_size} → {effective_batch_size}"
                        )

                # Force garbage collection after each batch to free memory
                import gc

                gc.collect()

                # Clear batch data to free memory immediately
                batch_entities.clear()
                batch_relations.clear()
                batch_implementation_chunks.clear()

                self.logger.debug(
                    f"🧹 Memory cleanup performed after batch {batch_num}"
                )

            # Apply in-memory orphan filtering before storage to avoid wasted embeddings
            if all_relations:
                # Get global entity names for filtering
                global_entity_names = self._get_all_entity_names(collection_name)

                # CRITICAL: Add entities from current batch to avoid filtering legitimate relations
                current_batch_entity_names = {entity.name for entity in all_entities}
                combined_entity_names = global_entity_names | current_batch_entity_names

                if combined_entity_names:
                    original_count = len(all_relations)
                    all_relations = self._filter_orphan_relations_in_memory(
                        all_relations, combined_entity_names
                    )
                    filtered_count = original_count - len(all_relations)
                    self.logger.info(
                        f"🧹 Pre-storage filtering: {filtered_count} orphan relations removed, {len(all_relations)} valid relations kept"
                    )
                    self.logger.debug(
                        f"   Entity awareness: {len(global_entity_names)} from DB + {len(current_batch_entity_names)} from current batch = {len(combined_entity_names)} total"
                    )
                else:
                    self.logger.warning(
                        "⚠️ No entities available for filtering - proceeding without pre-filtering"
                    )

            # RACE CONDITION FIX: Use actual processed files (fix state tracking bug)
            successfully_processed = all_processed_files
            pre_captured_states = None
            if successfully_processed:
                from datetime import datetime

                logger.info(
                    f"🔒 PRE-CAPTURE: Taking atomic file state snapshot at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}"
                )
                pre_captured_states = self._get_current_state(successfully_processed)
                logger.info(
                    f"🔒 PRE-CAPTURE: Captured {len(pre_captured_states)} file states for atomic consistency"
                )

            # Store vectors using direct Qdrant automation with progressive disclosure
            if all_entities or all_relations or all_implementation_chunks:
                # Use unified Git+Meta setup
                git_meta = self._prepare_git_meta_context(collection_name, all_entities)
                # Use direct Qdrant automation via existing _store_vectors method
                storage_success = self._store_vectors(
                    collection_name,
                    all_entities,
                    all_relations,
                    all_implementation_chunks,
                    git_meta.changed_entity_ids,
                )
                if not storage_success:
                    result.success = False
                    if result.errors is not None:
                        result.errors.append("Failed to store vectors in Qdrant")
                else:
                    result.entities_created = len(all_entities)
                    result.relations_created = len(all_relations)
                    result.implementation_chunks_created = len(
                        all_implementation_chunks
                    )

            # Update state file using atomic pre-captured states
            logger.info(f"🚨 FAILED FILES: {result.failed_files}")
            logger.info(
                f"✅ SUCCESS FILES: {len(successfully_processed)} / {len(files_to_process)} total"
            )
            if successfully_processed:
                self._update_state(
                    successfully_processed,
                    collection_name,
                    verbose,
                    deleted_files=deleted_files if incremental else None,
                    pre_captured_state=pre_captured_states,
                )
                # Store processed files in result for test verification
                result.processed_files = [str(f) for f in successfully_processed]

                # Clean up orphaned relations after processing files (both full and incremental modes)
                if successfully_processed or result.entities or result.relations:
                    logger.info("🧹 === ORPHAN CLEANUP TRIGGERED ===")
                    logger.info(f"   Mode: {'INCREMENTAL' if incremental else 'FULL'}")
                    logger.info(f"   Files processed: {len(successfully_processed)}")
                    logger.info("   Starting orphan cleanup...")
                    # Orphan cleanup with null safety
                    orphaned_deleted = 0
                    if self.vector_store and hasattr(
                        self.vector_store, "_cleanup_orphaned_relations"
                    ):
                        orphaned_deleted = (
                            self.vector_store._cleanup_orphaned_relations(
                                collection_name, verbose
                            )
                        )
                    else:
                        logger.info(
                            "✅ No orphaned relations found (vector store not available)"
                        )
                    if orphaned_deleted > 0:
                        logger.info(
                            f"✅ Cleanup complete: {orphaned_deleted} orphaned relations removed"
                        )
                    else:
                        logger.info("✅ No orphaned relations found")
                else:
                    logger.info("🚫 === ORPHAN CLEANUP SKIPPED ===")
                    logger.info(f"   Incremental: {incremental}")
                    logger.info(
                        f"   Successfully processed: {len(successfully_processed) if successfully_processed else 0}"
                    )
                    logger.info("   Reason: No files processed")
            elif verbose:
                logger.warning(
                    f"⚠️  No files to save state for (all {len(files_to_process)} files failed)"
                )

            # Transfer cost data to result
            if hasattr(self, "_session_cost_data"):
                result.total_tokens = int(self._session_cost_data.get("tokens", 0))
                result.total_cost_estimate = self._session_cost_data.get("cost", 0.0)
                result.embedding_requests = int(
                    self._session_cost_data.get("requests", 0)
                )
                # Reset for next operation
                self._session_cost_data = {"tokens": 0, "cost": 0.0, "requests": 0}

        except Exception as e:
            result.success = False
            if result.errors is not None:
                result.errors.append(f"Indexing failed: {e}")

        result.processing_time = time.time() - start_time
        return result

    def index_single_file(
        self, file_path: Path, collection_name: str
    ) -> IndexingResult:
        """Index a single file with Git+Meta deduplication."""
        start_time = time.time()
        result = IndexingResult(success=True, operation="single_file")

        try:
            # Parse file first to get entities for Git+Meta deduplication check
            batch_callback = None
            if self._should_use_batch_processing(file_path):
                batch_callback = self._create_batch_callback(collection_name)
                self.logger.info(
                    f"🚀 Enabling batch processing for large file: {file_path.name}"
                )

            # Parse file using cached global entities (will be set by Git+Meta setup if needed)
            parse_result = self.parser_registry.parse_file(
                file_path,
                batch_callback,
                global_entity_names=getattr(self, "_cached_global_entities", None),
            )

            if not parse_result.success:
                result.success = False
                result.files_failed = 1
                if result.errors is not None and parse_result.errors is not None:
                    result.errors.extend(parse_result.errors)
                return result

            # Use unified Git+Meta setup
            git_meta = self._prepare_git_meta_context(
                collection_name, parse_result.entities
            )

            # Early exit if all entities are unchanged
            if not git_meta.should_process:
                logger.info(
                    f"⚡ Git+Meta: All {git_meta.unchanged_count} entities unchanged, skipping cleanup and storage"
                )

                # Return success with zero operations
                result.files_processed = 1
                result.entities_created = 0
                result.relations_created = 0
                result.implementation_chunks_created = 0
                result.processed_files = [str(file_path)]
                result.total_tokens = 0
                result.total_cost_estimate = 0.0
                result.embedding_requests = 0
                result.processing_time = time.time() - start_time
                return result

            # The Git+Meta context and UnifiedContentProcessor now handle entity-level
            # diffing and cleanup automatically. This explicit, inefficient cleanup
            # step has been removed.

            # Handle storage based on whether batch processing was used
            if batch_callback:
                # Batch processing was used - data already stored via callback
                storage_success = True
                result.files_processed = 1
                result.entities_created = getattr(parse_result, "entities_created", 0)
                result.relations_created = 0  # Relations not used in content_only mode
                result.implementation_chunks_created = getattr(
                    parse_result, "implementation_chunks_created", 0
                )
                result.processed_files = [str(file_path)]
                self.logger.info(
                    f"✅ Streaming batch processing completed for {file_path.name}"
                )
            else:
                # Traditional processing - store accumulated results using unified Git+Meta
                storage_success = self._store_vectors(
                    collection_name,
                    parse_result.entities,
                    parse_result.relations,
                    parse_result.implementation_chunks,
                    git_meta.changed_entity_ids,
                )

                if storage_success:
                    result.files_processed = 1
                    result.entities_created = len(parse_result.entities)
                    result.relations_created = len(parse_result.relations)
                    result.implementation_chunks_created = len(
                        parse_result.implementation_chunks or []
                    )
                    result.processed_files = [str(file_path)]
                else:
                    result.success = False
                    result.files_failed = 1
                    result.errors.append("Failed to store vectors")  # type: ignore[union-attr]

        except Exception as e:
            result.success = False
            result.files_failed = 1
            result.errors.append(f"Failed to index {file_path}: {e}")  # type: ignore[union-attr]

        # Transfer cost data to result
        if hasattr(self, "_session_cost_data"):
            result.total_tokens = int(self._session_cost_data.get("tokens", 0))
            result.total_cost_estimate = self._session_cost_data.get("cost", 0.0)
            result.embedding_requests = int(self._session_cost_data.get("requests", 0))
            # Reset for next operation
            self._session_cost_data = {"tokens": 0, "cost": 0.0, "requests": 0}

        result.processing_time = time.time() - start_time
        return result

    def index_files(
        self, file_paths: list[Path], collection_name: str, verbose: bool = False
    ) -> IndexingResult:
        """Index a specific list of files as a batch.

        This method is optimized for batch operations like git hooks where
        multiple files need to be indexed together. It:
        - Processes all files in a single batch (leveraging parallelization)
        - Uses a single Qdrant transaction for storage
        - Shares embedding API batches across all files (500 relations per call)
        - Pays process startup cost only once

        Expected speedup: 4-15x faster than sequential single-file indexing.

        Args:
            file_paths: List of absolute file paths to index
            collection_name: Name of the collection to store in
            verbose: Enable verbose logging

        Returns:
            IndexingResult with aggregated metrics
        """
        start_time = time.time()
        result = IndexingResult(success=True, operation="batch_files")

        if not file_paths:
            result.warnings = ["No files provided for batch indexing"]
            result.processing_time = time.time() - start_time
            return result

        try:
            # Ensure collection exists
            if not self.vector_store.collection_exists(collection_name):
                if verbose:
                    self.logger.info(f"Creating collection '{collection_name}'...")
                vector_size = 512  # Voyage-3-lite default
                self.vector_store.backend.ensure_collection(
                    collection_name, vector_size
                )

            # Validate all files are within project
            valid_files = []
            for file_path in file_paths:
                try:
                    file_path.relative_to(self.project_path)
                    if file_path.exists() and file_path.is_file():
                        valid_files.append(file_path)
                    else:
                        if result.warnings is None:
                            result.warnings = []
                        result.warnings.append(f"File not found: {file_path}")
                except ValueError:
                    if result.warnings is None:
                        result.warnings = []
                    result.warnings.append(f"File not within project: {file_path}")

            if not valid_files:
                result.success = False
                result.errors = ["No valid files to index"]
                result.processing_time = time.time() - start_time
                return result

            if verbose:
                self.logger.info(f"📁 Batch indexing {len(valid_files)} files")

            # Process all files in a single batch (leverages parallelization for large batches)
            (
                all_entities,
                all_relations,
                all_implementation_chunks,
                errors,
                successfully_processed,
            ) = self._process_file_batch(valid_files, collection_name, verbose)

            if errors:
                if result.errors is None:
                    result.errors = []
                result.errors.extend(errors)

            # Apply orphan filtering before storage
            if all_relations:
                global_entity_names = self._get_all_entity_names(collection_name)
                current_batch_entity_names = {entity.name for entity in all_entities}
                combined_entity_names = global_entity_names | current_batch_entity_names

                if combined_entity_names:
                    original_count = len(all_relations)
                    all_relations = self._filter_orphan_relations_in_memory(
                        all_relations, combined_entity_names
                    )
                    filtered_count = original_count - len(all_relations)
                    if verbose and filtered_count > 0:
                        self.logger.info(
                            f"🧹 Filtered {filtered_count} orphan relations"
                        )

            # Store vectors in a single batch transaction
            if all_entities or all_relations or all_implementation_chunks:
                git_meta = self._prepare_git_meta_context(collection_name, all_entities)
                storage_success = self._store_vectors(
                    collection_name,
                    all_entities,
                    all_relations,
                    all_implementation_chunks,
                    git_meta.changed_entity_ids,
                )

                if not storage_success:
                    result.success = False
                    if result.errors is None:
                        result.errors = []
                    result.errors.append("Failed to store vectors in Qdrant")
                else:
                    result.files_processed = len(successfully_processed)
                    result.entities_created = len(all_entities)
                    result.relations_created = len(all_relations)
                    result.implementation_chunks_created = len(
                        all_implementation_chunks
                    )
                    result.processed_files = [str(f) for f in successfully_processed]

            # Update state for processed files
            if successfully_processed:
                self._update_state(
                    successfully_processed,
                    collection_name,
                    verbose,
                    full_rebuild=False,
                )

            # Transfer cost data
            if hasattr(self, "_session_cost_data"):
                result.total_tokens = int(self._session_cost_data.get("tokens", 0))
                result.total_cost_estimate = self._session_cost_data.get("cost", 0.0)
                result.embedding_requests = int(
                    self._session_cost_data.get("requests", 0)
                )
                self._session_cost_data = {"tokens": 0, "cost": 0.0, "requests": 0}

        except Exception as e:
            result.success = False
            if result.errors is None:
                result.errors = []
            result.errors.append(f"Batch indexing failed: {e}")

        result.processing_time = time.time() - start_time
        return result

    def index_incremental(
        self,
        collection_name: str,
        change_set: ChangeSet | None = None,
        since_commit: str | None = None,
        verbose: bool = False,
    ) -> IndexingResult:
        """Git-aware incremental indexing.

        Detects file changes using git (or hash comparison fallback) and
        processes only the changed files. Handles renames, deletions, and
        new/modified files efficiently.

        Args:
            collection_name: Name of the collection to update
            change_set: Optional pre-computed ChangeSet
            since_commit: Git commit/ref to detect changes from
            verbose: Enable verbose logging

        Returns:
            IndexingResult with processing statistics
        """
        start_time = time.time()
        result = IndexingResult(success=True, operation="incremental")

        try:
            # Detect changes if not provided
            if change_set is None:
                detector = GitChangeDetector(self.project_path)
                previous_state = self._load_state(collection_name)

                if since_commit:
                    change_set = detector.detect_changes(since_commit=since_commit)
                elif detector.is_git_repo():
                    # Use last indexed commit if available
                    last_commit = previous_state.get("_last_indexed_commit")
                    if last_commit:
                        change_set = detector.detect_changes(since_commit=last_commit)
                    else:
                        # No previous commit, fall back to hash detection
                        change_set = detector.detect_changes(
                            previous_state=previous_state
                        )
                else:
                    # Non-git repo: use hash-based detection
                    change_set = detector.detect_changes(previous_state=previous_state)

            if verbose:
                self.logger.info(f"📊 Changes detected: {change_set.summary()}")

            if not change_set.has_changes:
                result.warnings = ["No changes detected"]
                result.processing_time = time.time() - start_time
                return result

            # Step 1: Handle renames first (update paths in place)
            if change_set.renamed_files:
                renamed_count = self._handle_renamed_files(
                    collection_name, change_set.renamed_files, verbose
                )
                if verbose:
                    self.logger.info(f"📝 Updated {renamed_count} entities for renames")

            # Step 2: Handle deletions (remove from index)
            if change_set.deleted_files:
                self._handle_deleted_files(
                    collection_name, change_set.deleted_files, verbose
                )
                if verbose:
                    self.logger.info(
                        f"🗑️ Removed entities for {len(change_set.deleted_files)} deleted files"
                    )

            # Step 3: Index new and modified files
            files_to_index = change_set.files_to_index
            if files_to_index:
                # Use existing batch indexing
                batch_result = self.index_files(
                    files_to_index, collection_name, verbose
                )

                # Transfer batch result stats
                result.files_processed = batch_result.files_processed
                result.entities_created = batch_result.entities_created
                result.relations_created = batch_result.relations_created
                result.implementation_chunks_created = (
                    batch_result.implementation_chunks_created
                )
                result.processed_files = batch_result.processed_files
                result.errors = batch_result.errors
                result.warnings = batch_result.warnings

                if not batch_result.success:
                    result.success = False

            # Step 4: Update state with new commit
            if change_set.is_git_repo and change_set.base_commit:
                self._update_last_indexed_commit(
                    collection_name, change_set.base_commit
                )

            # Add change summary to result
            if result.warnings is None:
                result.warnings = []
            result.warnings.append(f"Incremental: {change_set.summary()}")

        except Exception as e:
            result.success = False
            if result.errors is None:
                result.errors = []
            result.errors.append(f"Incremental indexing failed: {e}")

        result.processing_time = time.time() - start_time
        return result

    def _handle_renamed_files(
        self,
        collection_name: str,
        renamed_files: list[tuple[str, str]],
        verbose: bool = False,
    ) -> int:
        """Handle renamed files by updating file paths in place.

        This preserves entity history and observations rather than
        deleting and recreating entities.

        Args:
            collection_name: Name of the collection
            renamed_files: List of (old_path, new_path) tuples
            verbose: Enable verbose logging

        Returns:
            Number of entities updated
        """
        if not renamed_files:
            return 0

        total_updated = 0

        try:
            # Convert relative paths to absolute for Qdrant
            path_updates = []
            for old_rel, new_rel in renamed_files:
                old_abs = str(self.project_path / old_rel)
                new_abs = str(self.project_path / new_rel)
                path_updates.append((old_abs, new_abs))

                if verbose:
                    self.logger.info(f"📝 Rename: {old_rel} -> {new_rel}")

            # Use the storage layer's update method
            result = self.vector_store.update_file_paths(collection_name, path_updates)

            if result.success:
                total_updated = result.items_processed
                if verbose:
                    self.logger.info(
                        f"✅ Updated {total_updated} entities for {len(renamed_files)} renames"
                    )
            else:
                self.logger.warning(f"⚠️ Some renames failed: {result.errors}")

            # Update file hash cache for renamed files
            for old_rel, new_rel in renamed_files:
                new_path = self.project_path / new_rel
                if new_path.exists():
                    # Update cache with new path
                    if hasattr(self, "_file_hash_cache") and self._file_hash_cache:
                        self._file_hash_cache.remove(self.project_path / old_rel)
                        self._file_hash_cache.update(new_path)

        except Exception as e:
            self.logger.error(f"Error handling renamed files: {e}")

        return total_updated

    def _update_last_indexed_commit(
        self, collection_name: str, commit_sha: str
    ) -> None:
        """Update the last indexed commit in the state file.

        Args:
            collection_name: Name of the collection
            commit_sha: The commit SHA that was indexed
        """
        try:
            state = self._load_state(collection_name)
            state["_last_indexed_commit"] = commit_sha
            state["_last_indexed_time"] = time.time()

            state_file = self._get_state_file(collection_name)
            self._atomic_json_write(state_file, state, "commit state")

            self.logger.debug(f"Updated last indexed commit to {commit_sha}")
        except Exception as e:
            self.logger.warning(f"Failed to update last indexed commit: {e}")

    def search_similar(
        self,
        collection_name: str,
        query: str,
        limit: int = 10,
        filter_type: str | None = None,
        chunk_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar entities/relations.

        Args:
            collection_name: Name of the collection to search
            query: Search query text
            limit: Maximum number of results
            filter_type: Filter by entity type (e.g., 'function', 'class')
            chunk_type: Filter by chunk type (e.g., 'implementation', 'metadata')
        """
        try:
            # Check if collection exists before searching
            if not self.vector_store.collection_exists(collection_name):
                logger.warning(f"Collection '{collection_name}' does not exist")
                return []

            # Generate query embedding
            embedding_result = self.embedder.embed_text(query)
            if not embedding_result.success:
                return []

            # Build filter
            filter_conditions = {}
            if filter_type:
                filter_conditions["type"] = filter_type
            if chunk_type:
                filter_conditions["chunk_type"] = chunk_type

            # Search vector store
            search_result = self.vector_store.search_similar(
                collection_name=collection_name,
                query_vector=embedding_result.embedding,
                limit=limit,
                filter_conditions=filter_conditions,
            )

            return (
                search_result.results
                if search_result.success and search_result.results
                else []
            )

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def clear_collection(
        self, collection_name: str, preserve_manual: bool = True
    ) -> bool:
        """Clear collection data.

        Args:
            collection_name: Name of the collection
            preserve_manual: If True (default), preserve manually-added memories
        """
        try:
            # Clear vector store
            result = self.vector_store.clear_collection(  # type: ignore[attr-defined]
                collection_name, preserve_manual=preserve_manual
            )

            # Clear state file (only tracks code-indexed files)
            state_file = self._get_state_file(collection_name)
            if state_file.exists():
                state_file.unlink()

            return bool(result.success)

        except Exception as e:
            logger.error(f"Failed to clear collection: {e}")
            return False

    def _find_all_files(self, _include_tests: bool = False) -> list[Path]:
        """Find all files matching project patterns."""
        files = set()  # Use set to prevent duplicates

        # Use project-specific patterns
        include_patterns = self.config.include_patterns
        exclude_patterns = self.config.exclude_patterns

        # No fallback patterns - use what's configured
        if not include_patterns:
            raise ValueError("No include patterns configured")

        # Find files matching include patterns
        for pattern in include_patterns:
            # Handle patterns that already include ** vs those that don't
            glob_pattern = pattern if pattern.startswith("**/") else f"**/{pattern}"

            found = list(self.project_path.glob(glob_pattern))
            files.update(found)  # Use update instead of extend to prevent duplicates

        # Filter files using HierarchicalIgnoreManager (preferred) AND config patterns
        filtered_files = []
        for file_path in files:
            relative_path = file_path.relative_to(self.project_path)
            should_exclude = False

            # Check 1: HierarchicalIgnoreManager (if available)
            if self.ignore_manager is not None:
                if self.ignore_manager.should_ignore(relative_path):
                    should_exclude = True

            # Check 2: Config exclude_patterns (always applied if present)
            # This ensures explicit exclude_patterns in config are respected
            if not should_exclude and exclude_patterns:
                relative_str = str(relative_path)

                for pattern in exclude_patterns:
                    # Handle directory patterns (ending with /)
                    if pattern.endswith("/"):
                        # Check if pattern appears anywhere in the path (for nested directories)
                        if (
                            relative_str.startswith(pattern)
                            or f"/{pattern}" in f"/{relative_str}"
                        ):
                            should_exclude = True
                            break
                    # Handle glob patterns and exact matches
                    elif (
                        fnmatch.fnmatch(str(relative_path), pattern)
                        or fnmatch.fnmatch(relative_path.name, pattern)
                        or any(
                            fnmatch.fnmatch(part, pattern)
                            for part in relative_path.parts
                        )
                    ):
                        should_exclude = True
                        break

            if should_exclude:
                continue

            # Check file size
            if file_path.stat().st_size > self.config.max_file_size:
                continue

            filtered_files.append(file_path)

        return list(filtered_files)  # Convert back to list for return type consistency

    def _get_files_needing_processing(
        self, include_tests: bool = False, collection_name: str | None = None
    ) -> list[Path]:
        """Get files that need processing for incremental indexing."""
        return self._find_changed_files(include_tests, collection_name)[0]

    def _get_last_run_time(self, previous_state: dict) -> float:
        """Extract latest mtime from state for timestamp filtering."""
        if not previous_state:
            return 0.0

        last_time = 0.0
        for file_data in previous_state.values():
            if isinstance(file_data, dict) and "mtime" in file_data:
                last_time = max(last_time, file_data["mtime"])

        return last_time

    def _find_files_since(
        self,
        since_time: float,
        include_tests: bool = False,
        collection_name: str | None = None,
    ) -> list[Path]:
        """Find files modified since timestamp using state cache."""
        if since_time <= 0:
            return self._find_all_files(include_tests)

        try:
            # Use cached mtime from state file (O(1) vs O(n) filesystem scan)
            state = self._load_state(collection_name or "default")
            candidates = []

            for state_file_path, _metadata in state.items():
                if state_file_path.startswith("_"):  # Skip metadata keys
                    continue

                path_obj = self.project_path / state_file_path
                if path_obj.exists():  # Verify file still exists
                    try:
                        actual_mtime = path_obj.stat().st_mtime
                        if actual_mtime > since_time:
                            candidates.append(path_obj)
                    except (OSError, FileNotFoundError):
                        continue

            # Detect stale state cache: if no results but state exists, verify with filesystem
            if len(candidates) == 0 and len(state) > 3:
                # Quick sample check for recent files
                all_files = self._find_all_files(include_tests)
                for sample_file in all_files[:5]:  # Check first 5 files only
                    try:
                        if sample_file.stat().st_mtime > since_time:
                            # Found recent files - state cache is stale
                            raise Exception("Stale state cache")
                    except (OSError, FileNotFoundError):
                        continue

            return candidates

        except Exception:
            # Fallback: simple implementation if state cache fails
            all_files = self._find_all_files(include_tests)
            changed_files: list[Path] = []

            for file_path in all_files:
                try:
                    if file_path.stat().st_mtime > since_time:
                        changed_files.append(file_path)
                except (OSError, FileNotFoundError):
                    continue

            return changed_files

    def _find_changed_files(
        self, include_tests: bool = False, collection_name: str | None = None
    ) -> tuple[list[Path], list[str]]:
        """Find files that have changed since last indexing."""
        previous_state = self._load_state(collection_name or "default")
        last_run_time = self._get_last_run_time(previous_state)

        # OPTIMIZATION: Only scan modified files instead of ALL files
        candidate_files = self._find_files_since(
            last_run_time, include_tests, collection_name or "default"
        )
        current_state = self._get_current_state(candidate_files)  # Hash only suspects

        changed_files: list[Path] = []
        deleted_files: list[str] = []

        # Find new and modified files
        for file_path in candidate_files:
            file_key = str(file_path.relative_to(self.project_path))
            current_hash = current_state.get(file_key, {}).get("hash", "")
            previous_hash = previous_state.get(file_key, {}).get("hash", "")

            if current_hash != previous_hash:
                changed_files.append(file_path)

        # Find deleted files and new files (still need full scan)
        all_files = self._find_all_files(include_tests)
        all_current_state = self._get_current_state(all_files)
        current_keys = set(all_current_state.keys())
        previous_keys = {
            k for k in previous_state if not k.startswith("_")
        }  # Exclude metadata keys
        deleted_keys = previous_keys - current_keys
        deleted_files.extend(deleted_keys)

        # Also find NEW files (not in previous state)
        new_keys = current_keys - previous_keys
        for new_key in new_keys:
            new_file_path = self.project_path / new_key
            if new_file_path not in changed_files:  # Avoid duplicates
                changed_files.append(new_file_path)

        return changed_files, deleted_files

    def _categorize_file_changes(
        self, include_tests: bool = False, collection_name: str | None = None
    ) -> tuple[list[Path], list[Path], list[str]]:
        """Categorize files into new, modified, and deleted."""
        current_files = self._find_all_files(include_tests)
        current_state = self._get_current_state(current_files)
        previous_state = self._load_state(collection_name or "default")

        new_files: list[Path] = []
        modified_files: list[Path] = []
        deleted_files: list[str] = []

        # Categorize changed files
        for file_path in current_files:
            file_key = str(file_path.relative_to(self.project_path))
            current_hash = current_state.get(file_key, {}).get("hash", "")
            previous_hash = previous_state.get(file_key, {}).get("hash", "")

            if current_hash != previous_hash:
                if previous_hash == "":  # Not in previous state = new file
                    new_files.append(file_path)
                else:  # In previous state but different hash = modified file
                    modified_files.append(file_path)

        # Find deleted files
        current_keys = set(current_state.keys())
        previous_keys = {
            k for k in previous_state if not k.startswith("_")
        }  # Exclude metadata
        deleted_keys = previous_keys - current_keys
        deleted_files.extend(deleted_keys)

        return new_files, modified_files, deleted_files

    def _get_vectored_files(self, collection_name: str) -> set[str]:
        """Get set of files that currently have entities in the vector database."""
        try:
            # Access the underlying QdrantStore client (bypass CachingVectorStore wrapper)
            if hasattr(self.vector_store, "backend"):
                qdrant_client = self.vector_store.backend.client
            else:
                qdrant_client = self.vector_store.client  # type: ignore[attr-defined]

            # Scroll through all points to get file paths
            file_paths = set()
            scroll_result = qdrant_client.scroll(
                collection_name=collection_name,
                limit=10000,  # Large batch size
                with_payload=True,
                with_vectors=False,
            )

            points = scroll_result[0]  # First element is the points list
            next_page_offset = scroll_result[1]  # Second element is next page offset

            # Process first batch
            for point in points:
                payload = point.payload if hasattr(point, "payload") else {}
                file_path = payload.get("metadata", {}).get("file_path")
                if file_path:
                    # Convert to relative path for consistency
                    try:
                        rel_path = str(Path(file_path).relative_to(self.project_path))
                        file_paths.add(rel_path)
                    except ValueError:
                        # If relative_to fails, use the file_path as-is
                        file_paths.add(file_path)

            # Handle pagination if there are more points
            while next_page_offset is not None:
                scroll_result = qdrant_client.scroll(
                    collection_name=collection_name,
                    offset=next_page_offset,
                    limit=10000,
                    with_payload=True,
                    with_vectors=False,
                )

                points = scroll_result[0]
                next_page_offset = scroll_result[1]

                for point in points:
                    payload = point.payload if hasattr(point, "payload") else {}
                    file_path = payload.get("metadata", {}).get("file_path")
                    if file_path:
                        try:
                            rel_path = str(
                                Path(file_path).relative_to(self.project_path)
                            )
                            file_paths.add(rel_path)
                        except ValueError:
                            file_paths.add(file_path)

            return file_paths
        except Exception as e:
            logger.warning(f"Failed to get vectored files: {e}")
            return set()

    def _categorize_vectored_file_changes(
        self,
        collection_name: str,
        before_vectored_files: set[str] | None = None,
        processed_files: set[str] | None = None,
    ) -> tuple[list[str], list[str], list[str]]:
        """Categorize vectored files (files with entities in database) into new, modified, and deleted."""
        current_vectored_files = self._get_vectored_files(collection_name)

        if before_vectored_files is None:
            # If no before state provided, we can't determine what changed
            # Return empty lists instead of showing all files as modified
            return [], [], []

        new_vectored = list(current_vectored_files - before_vectored_files)
        deleted_vectored = list(before_vectored_files - current_vectored_files)

        # Only show files as modified if they were actually processed AND existed before
        # This prevents showing all existing files as "modified"
        if processed_files:
            # Convert processed_files paths to relative paths for comparison
            processed_relative = set()
            for file_path in processed_files:
                try:
                    # file_path is already a string from set[str]
                    # if isinstance(file_path, Path):
                    #     rel_path = str(file_path.relative_to(self.project_path))
                    # else:
                    # Assume it's already a relative path string
                    rel_path = str(file_path)
                    processed_relative.add(rel_path)
                except (ValueError, AttributeError):
                    # If relative_to fails or file_path is not Path-like
                    processed_relative.add(str(file_path))

            # Modified files are those that were processed AND existed in database before
            modified_vectored = list(
                processed_relative & before_vectored_files & current_vectored_files
            )
        else:
            # No processed files info - can't determine modified files accurately
            modified_vectored = []

        return new_vectored, modified_vectored, deleted_vectored

    # Minimum batch size to justify parallelization overhead
    # Process creation has ~200-500ms overhead per worker, and serialization adds more
    # Only enable for very large batches where the total sequential time would exceed overhead
    # Testing shows 50 files takes ~0.8s sequential vs ~1.6s parallel (0.49x speedup)
    # So only parallelize for 100+ files where we expect sequential time > 2s
    MIN_PARALLEL_BATCH = 100

    def _dict_to_entity(self, data: dict) -> Entity:
        """Convert dictionary from parallel worker back to Entity dataclass."""
        from .analysis.entities import EntityType

        return Entity(
            name=data["name"],
            entity_type=EntityType(data["entity_type"]),
            observations=data.get("observations", []),
            file_path=Path(data["file_path"]) if data.get("file_path") else None,
            line_number=data.get("line_number"),
            end_line_number=data.get("end_line_number"),
            docstring=data.get("docstring"),
            signature=data.get("signature"),
            complexity_score=data.get("complexity_score"),
            metadata=data.get("metadata", {}),
        )

    def _dict_to_relation(self, data: dict) -> Relation:
        """Convert dictionary from parallel worker back to Relation dataclass."""
        from .analysis.entities import RelationType

        return Relation(
            from_entity=data["from_entity"],
            to_entity=data["to_entity"],
            relation_type=RelationType(data["relation_type"]),
            context=data.get("context"),
            confidence=data.get("confidence", 1.0),
            metadata=data.get("metadata", {}),
        )

    def _dict_to_chunk(self, data: dict) -> EntityChunk:
        """Convert dictionary from parallel worker back to EntityChunk dataclass."""
        return EntityChunk(
            id=data["id"],
            entity_name=data["entity_name"],
            chunk_type=data["chunk_type"],
            content=data["content"],
            metadata=data.get("metadata", {}),
        )

    def _process_files_parallel(
        self, files: list[Path], collection_name: str, _verbose: bool = False
    ) -> tuple[list[Entity], list[Relation], list[EntityChunk], list[str], list[Path]]:
        """Process files using parallel workers for significant speedup.

        Args:
            files: List of files to process
            collection_name: Name of the collection
            _verbose: Enable verbose logging

        Returns:
            Tuple of (entities, relations, implementation_chunks, errors, successfully_processed_files)
        """
        self.logger.info(
            f"🚀 Starting parallel processing of {len(files)} files with {self.parallel_processor.current_workers} workers"
        )

        processing_config = {
            "max_file_size": self.config.max_file_size,
            "collection_name": collection_name,
        }

        # Run parallel processing
        results = self.parallel_processor.process_files_parallel(
            files, collection_name, processing_config
        )

        # Get tier stats for logging
        tier_stats = self.parallel_processor.get_tier_stats(results)
        self.logger.info(
            f"📊 Parallel results: {tier_stats.get('standard', 0)} standard, "
            f"{tier_stats.get('light', 0)} light, {tier_stats.get('error', 0)} errors"
        )

        # Convert results back to expected format
        all_entities: list[Entity] = []
        all_relations: list[Relation] = []
        all_chunks: list[EntityChunk] = []
        errors: list[str] = []
        successful_files: list[Path] = []

        for result in results:
            file_path_str = result.get("file_path", "")

            if result["status"] == "success":
                # Convert dicts back to dataclass objects
                entities = [self._dict_to_entity(e) for e in result.get("entities", [])]
                relations = [
                    self._dict_to_relation(r) for r in result.get("relations", [])
                ]
                chunks = [self._dict_to_chunk(c) for c in result.get("chunks", [])]

                all_entities.extend(entities)
                all_relations.extend(relations)
                all_chunks.extend(chunks)
                successful_files.append(Path(file_path_str))

                # Populate signature table for O(1) duplicate detection (Memory Guard Tier 2)
                self._populate_signature_table(collection_name, entities, chunks)

            elif result["status"] == "skipped":
                # Skipped files (too large) aren't errors but also aren't processed
                reason = result.get("reason", "Unknown")
                self.logger.debug(f"  Skipped {file_path_str}: {reason}")

            elif result["status"] == "no_parser":
                # No parser available - not an error, just unsupported file type
                self.logger.debug(f"  No parser for {file_path_str}")

            else:
                # Error or timeout
                error_msg = result.get("error", "Unknown error")
                errors.append(f"{file_path_str}: {error_msg}")
                if _verbose and result.get("traceback"):
                    self.logger.debug(f"  Traceback: {result['traceback']}")

        self.logger.info(
            f"✅ Parallel processing complete: {len(all_entities)} entities, "
            f"{len(all_relations)} relations, {len(errors)} errors"
        )

        return all_entities, all_relations, all_chunks, errors, successful_files

    def _filter_orphan_relations_in_memory(
        self, relations: list["Relation"], global_entity_names: set
    ) -> list["Relation"]:
        """Filter out relations pointing to non-existent entities - handles CALLS and IMPORTS."""
        if not global_entity_names:
            self.logger.warning("No global entities available - keeping all relations")
            return relations

        def resolve_module_name(module_name: str) -> bool:
            """Check if module name resolves to any existing entity."""
            if module_name in global_entity_names:
                return True

            # Handle relative imports (.chat.parser, ..config, etc.)
            if module_name.startswith("."):
                clean_name = module_name.lstrip(".")
                for entity_name in global_entity_names:
                    # Direct pattern match first
                    if entity_name.endswith(
                        f"/{clean_name}.py"
                    ) or entity_name.endswith(f"\\{clean_name}.py"):
                        return True
                    # Handle dot notation (chat.parser -> chat/parser.py)
                    if "." in clean_name:
                        path_version = clean_name.replace(".", "/")
                        if entity_name.endswith(
                            f"/{path_version}.py"
                        ) or entity_name.endswith(f"\\{path_version}.py"):
                            return True
                    # Fallback: contains check
                    if clean_name in entity_name and entity_name.endswith(".py"):
                        return True

            # Handle absolute module paths (claude_indexer.analysis.entities)
            elif "." in module_name:
                path_parts = module_name.split(".")
                for entity_name in global_entity_names:
                    # Check if entity path contains module structure and ends with .py
                    if (
                        all(part in entity_name for part in path_parts)
                        and entity_name.endswith(".py")
                        and path_parts[-1] in entity_name
                    ):
                        return True

            return False

        valid_relations = []
        orphan_count = 0
        import_orphan_count = 0

        for relation in relations:
            # For CALLS relations, check if target entity exists
            if relation.relation_type.value == "calls":
                if relation.to_entity in global_entity_names:
                    valid_relations.append(relation)
                    # self.logger.debug(f"✅ Kept relation: {relation.from_entity} -> {relation.to_entity}")
                else:
                    orphan_count += 1
                    self.logger.debug(
                        f"🚫 Filtered orphan: {relation.from_entity} -> {relation.to_entity}"
                    )

            # For IMPORTS relations, use module resolution logic
            elif relation.relation_type.value == "imports":
                if resolve_module_name(relation.to_entity):
                    valid_relations.append(relation)
                    # self.logger.debug(f"✅ Kept import: {relation.to_entity}")
                else:
                    import_orphan_count += 1
                    # self.logger.debug(f"🚫 Filtered external import: {relation.to_entity}")
            else:
                # Keep all other relations (contains, inherits, etc.)
                valid_relations.append(relation)

        self.logger.info(
            f"Filtered {orphan_count} orphan CALLS relations, {import_orphan_count} external imports"
        )
        return valid_relations

    def _get_all_entity_names(self, collection_name: str) -> set:
        """Get all entity names from vector store for global entity awareness."""
        try:
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            # Use storage layer's _scroll_collection method which handles collection existence
            points = self.vector_store._scroll_collection(
                collection_name=collection_name,
                scroll_filter=Filter(
                    must_not=[
                        FieldCondition(key="type", match=MatchValue(value="relation"))
                    ]
                ),
                limit=1000,
                with_vectors=False,
                handle_pagination=True,
            )

            entity_names = set()
            # Extract entity names from payloads (both chunks and entities)
            for point in points:
                payload = point.payload
                if payload:
                    # Try entity_name first (chunks), then name (legacy entities)
                    entity_name = payload.get("entity_name") or payload.get("name")
                    if entity_name:
                        entity_names.add(entity_name)

            self.logger.debug(
                f"🌐 Retrieved {len(entity_names)} global entity names for entity-aware filtering"
            )
            return entity_names

        except Exception as e:
            self.logger.warning(f"Failed to get global entities: {e}")
            return set()

    def _process_file_batch(
        self, files: list[Path], collection_name: str, _verbose: bool = False
    ) -> tuple[list[Entity], list[Relation], list[EntityChunk], list[str], list[Path]]:
        """Process a batch of files with progressive disclosure support.

        Routes to parallel processing for large batches (>= MIN_PARALLEL_BATCH files)
        when parallel processing is enabled. Falls back to sequential processing
        for small batches or if parallel processing fails.

        Returns:
            Tuple of (entities, relations, implementation_chunks, errors, successfully_processed_files)
        """
        # Route to parallel processing for large batches
        if (
            self.parallel_processor is not None
            and len(files) >= self.MIN_PARALLEL_BATCH
            and self.config.use_parallel_processing
        ):
            try:
                return self._process_files_parallel(files, collection_name, _verbose)
            except Exception as e:
                self.logger.warning(
                    f"⚠️ Parallel processing failed, falling back to sequential: {e}"
                )
                # Fall through to sequential processing

        # Only log batch info in verbose mode
        if _verbose and self.logger:
            self.logger.debug(
                f"Processing batch of {len(files)} files for {collection_name}"
            )

        all_entities: list[Entity] = []
        all_relations: list[Relation] = []
        all_implementation_chunks: list[EntityChunk] = []
        errors: list[str] = []
        successfully_processed_files = []

        for file_path in files:
            try:
                relative_path = file_path.relative_to(self.project_path)

                # Determine file status using existing changed files logic
                current_state = self._get_current_state([file_path])
                previous_state = self._load_state(collection_name)

                file_key = str(relative_path)
                if file_key not in previous_state:
                    file_status = "ADDED"
                else:
                    current_hash = current_state.get(file_key, {}).get("hash", "")
                    previous_hash = previous_state.get(file_key, {}).get("hash", "")
                    file_status = (
                        "MODIFIED" if current_hash != previous_hash else "UNCHANGED"
                    )

                # Only log file processing for non-standard tiers
                processing_config = self.categorizer.get_processing_config(file_path)
                tier = processing_config["tier"]

                if tier != "standard":
                    self.logger.debug(
                        f"Processing [{file_status}] {tier} tier: {relative_path}"
                    )
                elif file_status != "UNCHANGED":
                    self.logger.debug(f"Processing [{file_status}]: {relative_path}")

                # Check for batch processing (streaming for large JSON files)
                batch_callback = None
                if self._should_use_batch_processing(file_path):
                    batch_callback = self._create_batch_callback(collection_name)
                    self.logger.info(
                        f"🚀 Enabling batch processing for large file: {file_path.name}"
                    )

                # Get global entity names for entity-aware filtering (use unified Git+Meta setup)
                # This ensures global entities are cached consistently across all flows
                self._prepare_git_meta_context(
                    collection_name, []
                )  # Empty entities just to trigger caching

                # Use cached global entities with fallback to empty set
                global_entity_names: set[str] = getattr(
                    self, "_cached_global_entities", set()
                )

                # Parse file with tier-appropriate processing
                if tier == "light":
                    # For light tier, we'll get a simplified result
                    result = self._parse_light_tier(file_path, global_entity_names)
                else:
                    # Standard and deep tiers use normal parsing
                    result = self.parser_registry.parse_file(
                        file_path,
                        batch_callback,
                        global_entity_names=global_entity_names,
                    )

                # DEBUG: Show parse result details
                # self.logger.debug(f"🔍 PARSE RESULT DEBUG for {file_path.name}:")
                # self.logger.debug(f"🔍   result.success: {result.success}")
                # self.logger.debug(f"🔍   result.errors: {getattr(result, 'errors', 'No errors attribute')}")
                # if hasattr(result, 'error_message'):
                #     self.logger.debug(f"🔍   result.error_message: {result.error_message}")

                # DEBUG: Track execution flow - where do entities go next?
                # self.logger.debug(f"🔍 FLOW DEBUG: {file_path.name} parse successful, entities will go to:")
                # self.logger.debug(f"🔍   - all_entities.extend() - no processing")
                # self.logger.debug(f"🔍   - Direct storage without unified processor")

                if result.success:
                    all_entities.extend(result.entities)
                    all_relations.extend(result.relations)
                    all_implementation_chunks.extend(result.implementation_chunks or [])
                    successfully_processed_files.append(file_path)

                    # Populate signature table for O(1) duplicate detection (Memory Guard Tier 2)
                    self._populate_signature_table(
                        collection_name, result.entities, result.implementation_chunks
                    )

                    # Only log if we found something meaningful (reduce noise)
                    if result.entities or result.relations:
                        self.logger.info(
                            f"  Found {len(result.entities)} entities, {len(result.relations)} relations"
                        )
                else:
                    # Check if it's a syntax error - if so, use fallback parser
                    error_str = (
                        ", ".join(result.errors) if result.errors else "Unknown error"
                    )
                    if "syntax" in error_str.lower() or "parse" in error_str.lower():
                        self.logger.debug(
                            f"  Syntax error detected, using fallback parser for {relative_path}"
                        )

                        # Use fallback parser to extract what we can
                        from .fallback_parser import FallbackParser

                        fallback_result = FallbackParser.parse_with_fallback(
                            file_path, error_str
                        )

                        if fallback_result.entities:
                            all_entities.extend(fallback_result.entities)
                            all_relations.extend(fallback_result.relations)
                            all_implementation_chunks.extend(
                                fallback_result.implementation_chunks or []
                            )
                            successfully_processed_files.append(file_path)

                            # Populate signature table for O(1) duplicate detection (Memory Guard Tier 2)
                            self._populate_signature_table(
                                collection_name,
                                fallback_result.entities,
                                fallback_result.implementation_chunks,
                            )

                            self.logger.info(
                                f"  Fallback parser recovered {len(fallback_result.entities)} entities, "
                                f"{len(fallback_result.relations)} relations from {relative_path}"
                            )
                        else:
                            errors.append(
                                f"Failed to parse {relative_path} even with fallback: {error_str}"
                            )
                            self.logger.debug(
                                f"  Fallback parsing also failed for {relative_path}"
                            )
                    else:
                        # Non-syntax error, regular failure
                        errors.append(f"Failed to parse {relative_path}: {error_str}")
                        if result.errors:
                            self.logger.debug(f"  Parse failed: {error_str}")

            except Exception as e:
                error_msg = f"Error processing {file_path}: {e}"
                errors.append(error_msg)
                self.logger.debug(f"  Processing error: {e}")

        return (
            all_entities,
            all_relations,
            all_implementation_chunks,
            errors,
            successfully_processed_files,
        )

    def _store_vectors(
        self,
        collection_name: str,
        entities: list[Entity],
        relations: list[Relation],
        implementation_chunks: list[EntityChunk] | None = None,
        changed_entity_ids: set | None = None,
    ) -> bool:
        """Store entities, relations, and implementation chunks with Git+Meta content deduplication."""
        if implementation_chunks is None:
            implementation_chunks = []
        if changed_entity_ids is None:
            changed_entity_ids = set()

        logger = self.logger if hasattr(self, "logger") else None

        # RACE CONDITION DEBUG: Track storage timing
        from datetime import datetime

        if logger:
            logger.info(
                f"💾 STORAGE START: {len(entities)} entities at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}"
            )
            file_paths = (
                {entity.file_path for entity in entities} if entities else {"none"}
            )
            logger.info(f"💾 Files being stored: {file_paths}")

        # Critical error check - vector store should always be available in production
        if not self.vector_store:
            if logger:
                logger.error(
                    "🚨 CRITICAL: Vector store is None during storage operation! This is a major bug if not in test environment."
                )
                logger.error("🚨 Simulating storage success but NO DATA WILL BE SAVED")
            return True

        if logger:
            logger.debug(
                f"🔄 Starting Git+Meta storage: {len(entities)} entities, {len(relations)} relations, {len(implementation_chunks)} chunks"
            )
            logger.debug(
                f"📊 Git+Meta changed entity IDs: {len(changed_entity_ids)} entities flagged as changed"
            )

        try:
            # Create unified processor (NEW)
            from .processing import UnifiedContentProcessor

            processor = UnifiedContentProcessor(
                self.vector_store, self.embedder, logger
            )

            result = processor.process_all_content(
                collection_name,
                entities,
                relations,
                implementation_chunks,
                changed_entity_ids,
            )

            if not result.success:
                if logger:
                    logger.error(f"❌ Unified processing failed: {result.error}")
                return False

            # Store session cost data (PRESERVED)
            if not hasattr(self, "_session_cost_data"):
                self._session_cost_data = {"tokens": 0, "cost": 0.0, "requests": 0}

            self._session_cost_data["tokens"] += result.total_tokens
            self._session_cost_data["cost"] += result.total_cost
            self._session_cost_data["requests"] += result.total_requests

            # RACE CONDITION DEBUG: Track storage completion
            if logger:
                logger.info(
                    f"💾 STORAGE COMPLETE: Success at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}"
                )

            return True

        except Exception as e:
            if logger:
                logger.error(f"Error in _store_vectors: {e}")
            return False

    def _entity_to_text(self, entity: Entity) -> str:
        """Convert entity to text for embedding."""
        parts = [
            f"{entity.entity_type.value}: {entity.name}",
            " ".join(entity.observations),
        ]

        if entity.docstring:
            parts.append(f"Description: {entity.docstring}")

        if entity.signature:
            parts.append(f"Signature: {entity.signature}")

        return " | ".join(parts)

    def _relation_to_text(self, relation: Relation) -> str:
        """Convert relation to text for embedding."""
        text = f"Relation: {relation.from_entity} {relation.relation_type.value} {relation.to_entity}"

        if relation.context:
            text += f" | Context: {relation.context}"

        return text

    def _get_current_state(self, files: list[Path]) -> dict[str, dict[str, Any]]:
        """Get current state of files."""
        state = {}

        for file_path in files:
            try:
                relative_path = str(file_path.relative_to(self.project_path))
                file_hash = self._get_file_hash(file_path)

                state[relative_path] = {
                    "hash": file_hash,
                    "size": file_path.stat().st_size,
                    "mtime": file_path.stat().st_mtime,
                }
            except (OSError, ValueError) as e:
                self.logger.warning(f"Failed to get state for file {file_path}: {e}")
                continue
            except Exception as e:
                self.logger.error(
                    f"Unexpected error getting state for file {file_path}: {e}"
                )
                continue

        return state

    def _get_file_hash(self, file_path: Path) -> str:
        """Get SHA256 hash of file contents."""
        try:
            with open(file_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except OSError as e:
            self.logger.warning(f"Failed to read file for hashing {file_path}: {e}")
            return ""
        except Exception as e:
            self.logger.error(f"Unexpected error hashing file {file_path}: {e}")
            return ""

    def _load_state(self, collection_name: str) -> dict[str, dict[str, Any]]:
        """Load previous indexing state."""
        try:
            state_file = self._get_state_file(collection_name)
            if state_file.exists():
                with open(state_file) as f:
                    return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            self.logger.warning(
                f"Failed to load state for collection {collection_name}: {e}"
            )
        except Exception as e:
            self.logger.error(
                f"Unexpected error loading state for collection {collection_name}: {e}"
            )
        return {}

    def _load_previous_statistics(self, collection_name: str) -> dict[str, int]:
        """Load previous run statistics from state file."""
        state = self._load_state(collection_name)
        return state.get("_statistics", {})

    def _atomic_json_write(
        self, file_path: Path, data: dict, description: str = "file"
    ) -> None:
        """Atomically write JSON data to a file using temp file + rename pattern.

        Args:
            file_path: Target file path
            data: Dictionary to write as JSON
            description: Description for error logging
        """
        try:
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Create temp file and write data
            temp_file = file_path.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(data, f, indent=2)

            # Atomic rename
            temp_file.rename(file_path)

        except Exception as e:
            # Clean up temp file if it exists
            temp_file = file_path.with_suffix(".tmp")
            if temp_file.exists():
                with contextlib.suppress(Exception):
                    temp_file.unlink()
            raise RuntimeError(f"Failed to atomically write {description}: {e}") from e

    def _save_statistics_to_state(self, collection_name: str, result: "IndexingResult"):
        """Save current statistics to state file."""
        import time

        try:
            state = self._load_state(collection_name)
            state["_statistics"] = {
                "files_processed": result.files_processed,
                "entities_created": result.entities_created,
                "relations_created": result.relations_created,
                "implementation_chunks_created": result.implementation_chunks_created,
                "processing_time": result.processing_time,
                "timestamp": time.time(),
            }

            state_file = self._get_state_file(collection_name)
            self._atomic_json_write(state_file, state, "statistics state")

        except Exception as e:
            logger.debug(f"Failed to save statistics to state: {e}")

    def _update_state(
        self,
        new_files: list[Path],
        collection_name: str,
        verbose: bool = False,
        full_rebuild: bool = False,
        deleted_files: list[str] | None = None,
        pre_captured_state: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Update state file by merging new files with existing state, or do full rebuild."""
        try:
            from datetime import datetime

            logger.info(
                f"🔍 STATE UPDATE START: {len(new_files)} files at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}"
            )
            logger.info(
                f"🔍 Input files: {[str(f.name) for f in new_files[:5]]}{'...' if len(new_files) > 5 else ''}"
            )

            if pre_captured_state:
                # Use pre-captured state (fixes race condition)
                logger.info(
                    f"🔍 USING PRE-CAPTURED STATE: {len(pre_captured_state)} files from atomic snapshot"
                )
                if full_rebuild:
                    final_state = pre_captured_state
                    operation_desc = "rebuilt"
                    file_count_desc = f"{len(new_files)} files tracked"
                else:
                    # Incremental update: merge pre-captured state with existing
                    existing_state = self._load_state(collection_name)
                    final_state = existing_state.copy()
                    final_state.update(pre_captured_state)
                    operation_desc = "updated"
                    file_count_desc = f"{len(new_files)} new files added, {len(final_state)} total files tracked"
            elif full_rebuild:
                # Fallback: Full rebuild without pre-captured state
                logger.info(
                    f"🔍 SNAPSHOT TIME: Taking state snapshot at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}"
                )
                final_state = self._get_current_state(new_files)
                operation_desc = "rebuilt"
                file_count_desc = f"{len(new_files)} files tracked"
            else:
                # Fallback: Incremental update with fresh scanning
                existing_state = self._load_state(collection_name)
                logger.info(
                    f"🔍 SNAPSHOT TIME: Taking state snapshot for {len(new_files)} files at {datetime.now().strftime('%H:%M:%S.%f')[:-3]}"
                )
                new_state = self._get_current_state(new_files)
                logger.info(
                    f"🔍 SNAPSHOT RESULT: {len(new_state)} files captured in snapshot"
                )

                final_state = existing_state.copy()
                final_state.update(new_state)
                operation_desc = "updated"
                file_count_desc = f"{len(new_files)} new files added, {len(final_state)} total files tracked"

            # Remove deleted files from final state
            if deleted_files:
                files_removed = 0
                for deleted_file in deleted_files:
                    logger.info(
                        f"🗑️ DEBUG: About to check for deletion from JSON state: '{deleted_file}' (exists in state: {deleted_file in final_state})"
                    )
                    if deleted_file in final_state:
                        logger.info(
                            f"🗑️ DEBUG: DELETING '{deleted_file}' from JSON state"
                        )
                        del final_state[deleted_file]
                        files_removed += 1
                        if verbose:
                            logger.debug(f"   Removed {deleted_file} from state")
                    else:
                        logger.info(
                            f"⚠️ DEBUG: File '{deleted_file}' NOT FOUND in state for deletion"
                        )

                if files_removed > 0:
                    # Update description to reflect deletions
                    if operation_desc == "updated":
                        file_count_desc = f"{len(new_files)} new files added, {files_removed} files removed, {len(final_state)} total files tracked"
                    else:  # rebuilt
                        file_count_desc = f"{len(new_files)} files tracked, {files_removed} deleted files removed"

            # Save state atomically using consolidated utility
            state_file = self._get_state_file(collection_name)
            self._atomic_json_write(state_file, final_state, "state file")

            # Verify saved state
            with open(state_file) as f:
                saved_state = json.load(f)

            if full_rebuild and len(saved_state) != len(new_files):
                raise ValueError(
                    f"State validation failed: expected {len(new_files)} files, got {len(saved_state)}"
                )
            # Note: For incremental updates, we cannot validate the final count
            # because it depends on both additions and deletions

            if verbose:
                logger.info(f"✅ State {operation_desc}: {file_count_desc}")

        except Exception as e:
            error_msg = (
                f"❌ Failed to {'rebuild' if full_rebuild else 'update'} state: {e}"
            )
            logger.error(error_msg)
            import traceback

            traceback.print_exc()
            # For incremental updates, fallback to full rebuild if update fails
            if not full_rebuild:
                logger.warning("🔄 Falling back to full state rebuild...")
                self._update_state(
                    self._find_all_files(include_tests=False),
                    collection_name,
                    verbose,
                    full_rebuild=True,
                    deleted_files=None,
                )

    def _rebuild_full_state(self, collection_name: str, verbose: bool = False):
        """Rebuild full state file from all current files."""
        try:
            if verbose:
                logger.info("🔄 Rebuilding complete state from all project files...")

            # Get all current files
            all_files = self._find_all_files(include_tests=False)

            # Use unified _update_state method with full_rebuild=True
            self._update_state(
                all_files,
                collection_name,
                verbose,
                full_rebuild=True,
                deleted_files=None,
            )

        except Exception as e:
            error_msg = f"❌ Failed to rebuild state: {e}"
            logger.error(error_msg)
            import traceback

            traceback.print_exc()

    def _collect_embedding_cost_data(
        self, embedding_results: list[Any]
    ) -> dict[str, int | float]:
        """Collect cost data from embedding results."""
        total_tokens = 0
        total_cost = 0.0
        total_requests = 0

        # Collect cost data from embedding results
        for embedding_result in embedding_results:
            if (
                hasattr(embedding_result, "token_count")
                and embedding_result.token_count
            ):
                total_tokens += embedding_result.token_count
            if (
                hasattr(embedding_result, "cost_estimate")
                and embedding_result.cost_estimate
            ):
                total_cost += embedding_result.cost_estimate

        # Count successful requests
        if hasattr(self.embedder, "get_usage_stats"):
            stats_before = getattr(self, "_last_usage_stats", {"total_requests": 0})
            current_stats = self.embedder.get_usage_stats()
            total_requests += max(
                0,
                current_stats.get("total_requests", 0)
                - stats_before.get("total_requests", 0),
            )
            self._last_usage_stats = current_stats

        return {"tokens": total_tokens, "cost": total_cost, "requests": total_requests}

    def _cleanup_temp_file(self, temp_file: Path | None):
        """Safely clean up temporary file with exception handling."""
        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
            except OSError as e:
                self.logger.warning(f"Failed to cleanup temp file {temp_file}: {e}")
            except Exception as e:
                self.logger.error(
                    f"Unexpected error cleaning up temp file {temp_file}: {e}"
                )

    def _handle_deleted_files(
        self,
        collection_name: str,
        deleted_files: str | list[str],
        verbose: bool = False,
    ):
        """Handle deleted files by removing their entities and orphaned relations."""
        # Convert single path to list for unified handling
        if isinstance(deleted_files, str):
            deleted_files = [deleted_files]

        if not deleted_files:
            return

        total_entities_deleted = 0

        try:
            for deleted_file in deleted_files:
                logger.info(f"🗑️ Handling deleted file: {deleted_file}")

                # State file always stores relative paths, construct the full path
                # Note: deleted_file is always relative from state file (see _get_current_state)
                # Don't use .resolve() as it adds /private on macOS, but entities are stored without it
                full_path = str(self.project_path / deleted_file)

                if verbose:
                    logger.debug(f"   📁 Resolved to: {full_path}")

                # Use the vector store's find_entities_for_file method
                logger.debug(f"   🔍 Finding ALL entities for file: {full_path}")

                point_ids = []
                try:
                    # Use the elegant single-query method
                    found_entities = self.vector_store.find_entities_for_file(
                        collection_name, full_path
                    )

                    if found_entities:
                        logger.debug(
                            f"   ✅ Found {len(found_entities)} entities for file"
                        )
                        for entity in found_entities:
                            entity_name = entity.get("name", "Unknown")
                            entity_type = entity.get("type", "unknown")
                            entity_id = entity.get("id")
                            logger.debug(
                                f"      🆔 ID: {entity_id}, name: '{entity_name}', type: {entity_type}"
                            )

                        # Extract point IDs for deletion
                        point_ids = [entity["id"] for entity in found_entities]
                    else:
                        logger.debug(f"   ⚠️ No entities found for {deleted_file}")

                except Exception as e:
                    logger.error(f"   ❌ Error finding entities: {e}")
                    point_ids = []

                # Remove duplicates and delete all found points
                point_ids = list(set(point_ids))
                logger.info(f"   🎯 Total unique point IDs to delete: {len(point_ids)}")
                if point_ids and verbose:
                    logger.debug(f"      🆔 Point IDs: {point_ids}")

                if point_ids:
                    # Delete the points
                    logger.info(
                        f"🗑️ DEBUG: About to DELETE from Qdrant - file: '{deleted_file}' resolved to: '{full_path}' with {len(point_ids)} points"
                    )
                    logger.info(f"   🗑️ Attempting to delete {len(point_ids)} points...")
                    delete_result = self.vector_store.delete_points(
                        collection_name, point_ids
                    )

                    if delete_result.success:
                        entities_deleted = len(point_ids)
                        total_entities_deleted += entities_deleted
                        logger.info(
                            f"   ✅ Successfully removed {entities_deleted} entities from {deleted_file}"
                        )
                    else:
                        logger.error(
                            f"   ❌ Failed to remove entities from {deleted_file}: {delete_result.errors}"
                        )
                else:
                    logger.warning(
                        f"   ⚠️ No entities found for {deleted_file} - nothing to delete"
                    )

            # NEW: Clean up orphaned relations after entity deletion
            if total_entities_deleted > 0:
                if verbose:
                    logger.info(
                        f"🔍 Starting orphan cleanup after deleting {total_entities_deleted} entities from {len(deleted_files)} files:"
                    )
                    for df in deleted_files:
                        logger.info(f"   📁 {df}")

                # Orphan cleanup with null safety
                orphaned_deleted = 0
                if self.vector_store and hasattr(
                    self.vector_store, "_cleanup_orphaned_relations"
                ):
                    orphaned_deleted = self.vector_store._cleanup_orphaned_relations(
                        collection_name, verbose
                    )
                else:
                    logger.info(
                        "✅ No orphaned relations found (vector store not available)"
                    )
                if verbose and orphaned_deleted > 0:
                    logger.info(
                        f"✅ Cleanup complete: {total_entities_deleted} entities, {orphaned_deleted} orphaned relations removed"
                    )
                elif verbose:
                    logger.info(
                        f"✅ Cleanup complete: {total_entities_deleted} entities removed, no orphaned relations found"
                    )

        except Exception as e:
            logger.error(f"Error handling deleted files: {e}")

    def _is_test_file(self, _file_path: Path) -> bool:
        """Check if a file is a test file - DISABLED."""
        return False
