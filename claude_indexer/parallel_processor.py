"""
Parallel file processing for efficient indexing.

This module implements multiprocessing-based parallel parsing to speed up
indexing of large projects while managing memory efficiently.
"""

import gc
import logging
import multiprocessing as mp
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import psutil

from .analysis.entities import Entity, EntityChunk, EntityType, Relation
from .analysis.parser import ParserRegistry
from .categorization import FileCategorizationSystem, ProcessingTier


# Configure logging for child processes
def init_worker():
    """Initialize worker process with proper logging."""
    # Disable most logging in workers to avoid output confusion
    logging.basicConfig(level=logging.ERROR)
    # Force garbage collection on worker start
    gc.collect()


def parse_file_worker(args: tuple[Path, str, dict[str, Any]]) -> dict[str, Any]:
    """
    Worker function for parsing a single file.
    Runs in a separate process for true parallelism.

    Args:
        args: Tuple of (file_path, collection_name, processing_config)

    Returns:
        Dictionary containing parsing results or error information
    """
    file_path, collection_name, processing_config = args

    try:
        # Initialize components in worker process
        # Use file's parent directory as project root for parser initialization
        project_root = file_path.parent
        parser_registry = ParserRegistry(project_root)
        categorizer = FileCategorizationSystem()

        # Get processing tier and config
        tier = categorizer.categorize_file(file_path)
        categorizer.get_processing_config(file_path)

        # Skip if file is too large
        try:
            file_size = file_path.stat().st_size
            max_size = processing_config.get("max_file_size", 1048576)
            if file_size > max_size:
                return {
                    "status": "skipped",
                    "file_path": str(file_path),
                    "reason": f"File too large: {file_size} bytes",
                    "tier": tier.value,
                }
        except OSError:
            pass

        # Parse based on tier
        if tier == ProcessingTier.LIGHT:
            # Light parsing - metadata only
            entities, relations, chunks = parse_light_tier(
                file_path, parser_registry, collection_name
            )
        else:
            # Standard or deep parsing
            # ParserRegistry.parse_file signature: (file_path, batch_callback=None, global_entity_names=None)
            parse_result = parser_registry.parse_file(
                file_path=file_path, batch_callback=None, global_entity_names=set()
            )

            if not parse_result:
                return {
                    "status": "no_parser",
                    "file_path": str(file_path),
                    "tier": tier.value,
                }

            entities = parse_result.entities
            relations = parse_result.relations
            chunks = parse_result.implementation_chunks

        # Convert to serializable format
        return {
            "status": "success",
            "file_path": str(file_path),
            "tier": tier.value,
            "entities": [entity_to_dict(e) for e in entities],
            "relations": [relation_to_dict(r) for r in relations],
            "chunks": [chunk_to_dict(c) for c in chunks],
            "stats": {
                "entity_count": len(entities),
                "relation_count": len(relations),
                "chunk_count": len(chunks),
            },
        }

    except Exception as e:
        return {
            "status": "error",
            "file_path": str(file_path),
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


def parse_light_tier(
    file_path: Path, parser_registry: ParserRegistry, collection_name: str
) -> tuple[list[Entity], list[Relation], list[EntityChunk]]:
    """
    Simplified parsing for light tier files (generated code, type definitions).

    Returns minimal metadata without deep analysis.
    """
    entities = []
    chunks = []

    # Create file entity using proper Entity dataclass
    file_entity = Entity(
        name=str(file_path.absolute()),
        entity_type=EntityType.FILE,
        observations=[
            f"File: {file_path.name}",
            "Tier: light (generated/type definition)",
            f"Type: {file_path.suffix}",
        ],
        file_path=file_path,
        line_number=1,
        metadata={
            "tier": "light",
            "generated": True,
            "file_type": file_path.suffix,
            "collection_name": collection_name,
        },
    )
    entities.append(file_entity)

    # Create minimal metadata chunk using proper EntityChunk dataclass
    import hashlib

    chunk_id = hashlib.md5(f"{file_path}::file::metadata".encode()).hexdigest()[:16]
    chunk = EntityChunk(
        id=f"{file_path}::file::{file_path.name}::metadata::{chunk_id}",
        entity_name=str(file_path.absolute()),
        chunk_type="metadata",
        content=f"Generated file: {file_path.name} | Tier: light",
        metadata={"tier": "light", "file_path": str(file_path)},
    )
    chunks.append(chunk)

    # Try to extract just interface/type names without full parsing
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")[
            :5000
        ]  # First 5KB only

        # Quick regex for TypeScript interfaces/types
        if file_path.suffix in [".ts", ".tsx", ".d.ts"]:
            import re

            # Find interface and type declarations
            interface_pattern = r"(?:export\s+)?interface\s+(\w+)"
            type_pattern = r"(?:export\s+)?type\s+(\w+)"

            interfaces = re.findall(interface_pattern, content)
            types = re.findall(type_pattern, content)

            for name in interfaces[:10]:  # Limit to first 10
                entity = Entity(
                    name=name,
                    entity_type=EntityType.INTERFACE,
                    observations=[
                        f"Interface: {name}",
                        f"Defined in: {file_path.name}",
                        "Tier: light (extracted without deep parsing)",
                    ],
                    file_path=file_path,
                    metadata={
                        "tier": "light",
                        "generated": True,
                        "collection_name": collection_name,
                    },
                )
                entities.append(entity)

            for name in types[:10]:  # Limit to first 10
                entity = Entity(
                    name=name,
                    entity_type=EntityType.VARIABLE,  # Use VARIABLE for type aliases
                    observations=[
                        f"Type alias: {name}",
                        f"Defined in: {file_path.name}",
                        "Tier: light (extracted without deep parsing)",
                    ],
                    file_path=file_path,
                    metadata={
                        "tier": "light",
                        "generated": True,
                        "collection_name": collection_name,
                    },
                )
                entities.append(entity)

    except Exception:
        # Ignore errors in light parsing
        pass

    return entities, [], chunks  # No relations for light tier


def entity_to_dict(entity: Entity) -> dict[str, Any]:
    """Convert Entity to serializable dictionary for cross-process transfer."""
    return {
        "name": entity.name,
        "entity_type": entity.entity_type.value,
        "observations": list(entity.observations),
        "file_path": str(entity.file_path) if entity.file_path else None,
        "line_number": entity.line_number,
        "end_line_number": entity.end_line_number,
        "docstring": entity.docstring,
        "signature": entity.signature,
        "complexity_score": entity.complexity_score,
        "metadata": dict(entity.metadata) if entity.metadata else {},
    }


def relation_to_dict(relation: Relation) -> dict[str, Any]:
    """Convert Relation to serializable dictionary for cross-process transfer."""
    return {
        "from_entity": relation.from_entity,
        "to_entity": relation.to_entity,
        "relation_type": relation.relation_type.value,
        "context": relation.context,
        "confidence": relation.confidence,
        "metadata": dict(relation.metadata) if relation.metadata else {},
    }


def chunk_to_dict(chunk: EntityChunk) -> dict[str, Any]:
    """Convert EntityChunk to serializable dictionary for cross-process transfer."""
    return {
        "id": chunk.id,
        "entity_name": chunk.entity_name,
        "chunk_type": chunk.chunk_type,
        "content": chunk.content,
        "metadata": dict(chunk.metadata) if chunk.metadata else {},
    }


class ParallelFileProcessor:
    """
    Manages parallel file processing for efficient indexing.
    """

    def __init__(
        self,
        max_workers: int | None = None,
        memory_limit_mb: int = 2000,
        logger: logging.Logger | None = None,
    ):
        """
        Initialize the parallel processor.

        Args:
            max_workers: Maximum number of worker processes (default: CPU count - 1)
            memory_limit_mb: Memory limit before reducing workers
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

        # Determine optimal worker count
        cpu_count = mp.cpu_count()
        if max_workers is None:
            # Leave one CPU for main process and system
            self.max_workers = max(1, cpu_count - 1)
        else:
            self.max_workers = min(max_workers, cpu_count)

        self.memory_limit_mb = memory_limit_mb
        self.categorizer = FileCategorizationSystem()

        # Track current worker count (can be adjusted dynamically)
        self.current_workers = self.max_workers

        self.logger.info(
            f"💪 Parallel processor initialized with {self.current_workers} workers"
        )

    def process_files_parallel(
        self,
        file_paths: list[Path],
        collection_name: str,
        processing_config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Process multiple files in parallel.

        Args:
            file_paths: List of file paths to process
            collection_name: Name of the collection
            processing_config: Configuration for processing

        Returns:
            List of parsing results
        """
        if not file_paths:
            return []

        # Check current memory usage
        memory_usage = psutil.Process().memory_info().rss / 1024 / 1024

        # Adjust worker count based on memory
        if memory_usage > self.memory_limit_mb:
            self.current_workers = max(1, self.current_workers // 2)
            self.logger.warning(
                f"High memory usage ({memory_usage:.0f}MB), reducing to {self.current_workers} workers"
            )
            gc.collect()

        # Categorize files first for better work distribution
        file_tiers = []
        for file_path in file_paths:
            tier = self.categorizer.categorize_file(file_path)
            file_tiers.append((file_path, tier))

        # Sort by tier - process light files first for quick wins
        file_tiers.sort(
            key=lambda x: (
                0
                if x[1] == ProcessingTier.LIGHT
                else 1 if x[1] == ProcessingTier.STANDARD else 2
            )
        )

        # Prepare worker arguments
        worker_args = [
            (file_path, collection_name, processing_config)
            for file_path, _ in file_tiers
        ]

        results = []
        processed = 0

        # Process files in parallel
        with ProcessPoolExecutor(
            max_workers=self.current_workers, initializer=init_worker
        ) as executor:
            # Submit all tasks
            future_to_file = {
                executor.submit(parse_file_worker, args): args[0]
                for args in worker_args
            }

            # Collect results as they complete
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    result = future.result(timeout=30)  # 30 second timeout per file
                    results.append(result)
                    processed += 1

                    # Log progress
                    if processed % 10 == 0:
                        self.logger.debug(
                            f"Processed {processed}/{len(file_paths)} files in parallel"
                        )

                except Exception as e:
                    self.logger.error(f"Error processing {file_path}: {e}")
                    results.append(
                        {
                            "status": "timeout",
                            "file_path": str(file_path),
                            "error": str(e),
                        }
                    )

        # Force garbage collection after batch
        gc.collect()

        return results

    def get_tier_stats(self, results: list[dict[str, Any]]) -> dict[str, int]:
        """
        Get statistics about processed file tiers.

        Args:
            results: List of processing results

        Returns:
            Dictionary with tier counts
        """
        stats = {"light": 0, "standard": 0, "deep": 0, "error": 0, "skipped": 0}

        for result in results:
            if result["status"] == "success":
                tier = result.get("tier", "standard")
                stats[tier] = stats.get(tier, 0) + 1
            else:
                stats[result["status"]] = stats.get(result["status"], 0) + 1

        return stats
