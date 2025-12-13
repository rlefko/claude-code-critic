"""
Enhanced _process_file_batch method with parallel processing support.

This module provides a replacement method that can be integrated into CoreIndexer.
"""

from pathlib import Path

from .analysis.entities import Entity
from .analysis.entities import EntityChunk as ChunkMetadata
from .analysis.entities import Relation


def process_file_batch_with_parallel(
    self, files: list[Path], collection_name: str, _verbose: bool = False
) -> tuple[list[Entity], list[Relation], list[ChunkMetadata], list[str], list[Path]]:
    """
    Enhanced version of _process_file_batch with parallel processing support.

    This method can switch between sequential and parallel processing based on:
    1. Configuration (use_parallel_processing flag)
    2. Batch size (only use parallel for larger batches)
    3. Memory constraints

    Returns:
        Tuple of (entities, relations, implementation_chunks, errors, successfully_processed_files)
    """
    # DEBUG logging
    if self.logger:
        self.logger.debug("🚨 DEBUG _process_file_batch CALL:")
        self.logger.debug(f"🚨   files: {[str(f) for f in files]}")
        self.logger.debug(f"🚨   collection_name: {collection_name}")
        self.logger.debug(f"🚨   verbose: {_verbose}")

    # Check collection health (existing logic)
    try:
        if hasattr(self.vector_store, "backend"):
            qdrant_client = self.vector_store.backend.client
        else:
            qdrant_client = self.vector_store.client

        total_points = qdrant_client.count(collection_name).count
        self.logger.debug(f"🚨   existing_points_in_collection: {total_points}")
    except Exception as e:
        self.logger.debug(f"🚨   existing_points_check_failed: {e}")

    # Initialize result containers
    all_entities: list[Entity] = []
    all_relations: list[Relation] = []
    all_implementation_chunks: list[ChunkMetadata] = []
    errors: list[str] = []
    successfully_processed_files: list[Path] = []

    # Determine whether to use parallel processing
    use_parallel = (
        self.parallel_processor is not None
        and self.config.use_parallel_processing
        and len(files) >= 3  # Only parallelize for 3+ files
    )

    if use_parallel:
        self.logger.info(f"⚡ Processing {len(files)} files in parallel")

        # Prepare processing configuration
        processing_config = {
            "max_file_size": self.config.max_file_size,
            "include_tests": self.config.include_tests,
        }

        # Process files in parallel
        results = self.parallel_processor.process_files_parallel(
            files, collection_name, processing_config
        )

        # Get tier statistics
        tier_stats = self.parallel_processor.get_tier_stats(results)
        self.logger.info(
            f"📊 Parallel processing complete: "
            f"{tier_stats['light']} light, {tier_stats['standard']} standard, "
            f"{tier_stats['deep']} deep, {tier_stats['error']} errors"
        )

        # Convert results back to entities/relations/chunks
        for result in results:
            file_path = Path(result["file_path"])

            if result["status"] == "success":
                # Reconstruct entities from dictionaries
                for entity_dict in result["entities"]:
                    entity = Entity(
                        name=entity_dict["name"],
                        type=entity_dict["type"],
                        file_path=entity_dict["file_path"],
                        content=entity_dict["content"],
                        collection_name=entity_dict["collection_name"],
                        metadata=entity_dict.get("metadata", {}),
                    )
                    all_entities.append(entity)

                # Reconstruct relations
                for relation_dict in result["relations"]:
                    relation = Relation(
                        source=relation_dict["source"],
                        target=relation_dict["target"],
                        type=relation_dict["type"],
                        metadata=relation_dict.get("metadata", {}),
                    )
                    all_relations.append(relation)

                # Reconstruct chunks
                for chunk_dict in result["chunks"]:
                    chunk = ChunkMetadata(
                        file_path=chunk_dict["file_path"],
                        entity_names=chunk_dict["entity_names"],
                        chunk_type=chunk_dict["chunk_type"],
                        content=chunk_dict["content"],
                        start_line=chunk_dict["start_line"],
                        end_line=chunk_dict["end_line"],
                        metadata=chunk_dict.get("metadata", {}),
                    )
                    all_implementation_chunks.append(chunk)

                successfully_processed_files.append(file_path)

                # Log success
                self.logger.info(
                    f"  Found {result['stats']['entity_count']} entities, "
                    f"{result['stats']['relation_count']} relations, "
                    f"{result['stats']['chunk_count']} implementation chunks"
                )

            elif result["status"] in ["error", "timeout"]:
                error_msg = f"Error processing {file_path}: {result.get('error', 'Unknown error')}"
                errors.append(error_msg)
                self.logger.error(f"❌ {error_msg}")

            elif result["status"] == "skipped":
                self.logger.debug(
                    f"⏭️ Skipped {file_path}: {result.get('reason', 'Unknown reason')}"
                )

    else:
        # Fall back to sequential processing (existing logic)
        self.logger.debug(f"📝 Processing {len(files)} files sequentially")

        # Use the original sequential processing logic
        # (This would be the existing code from _process_file_batch)
        # For now, we'll call the original method if it exists
        if hasattr(self, "_process_file_batch_original"):
            return self._process_file_batch_original(files, collection_name, _verbose)
        else:
            # If no original method saved, use basic sequential processing
            for file_path in files:
                try:
                    # Get processing config
                    processing_config = self.categorizer.get_processing_config(
                        file_path
                    )
                    tier = processing_config["tier"]

                    # Parse file
                    if tier == "light":
                        result = self._parse_light_tier(file_path, set())
                    else:
                        result = self.parser_registry.parse_file(
                            file_path, None, global_entity_names=set()
                        )

                    if result.success:
                        all_entities.extend(result.entities)
                        all_relations.extend(result.relations)
                        all_implementation_chunks.extend(
                            result.implementation_chunks or []
                        )
                        successfully_processed_files.append(file_path)

                        self.logger.info(
                            f"  Found {len(result.entities)} entities, "
                            f"{len(result.relations)} relations, "
                            f"{len(result.implementation_chunks or [])} implementation chunks"
                        )
                    else:
                        error_msg = f"Failed to parse {file_path}"
                        errors.append(error_msg)
                        self.logger.error(f"❌ {error_msg}")

                except Exception as e:
                    error_msg = f"Error processing {file_path}: {str(e)}"
                    errors.append(error_msg)
                    self.logger.error(f"❌ {error_msg}")

    return (
        all_entities,
        all_relations,
        all_implementation_chunks,
        errors,
        successfully_processed_files,
    )
