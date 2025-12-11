"""Click-based CLI interface for the Claude Code indexer."""

import subprocess
import sys
from pathlib import Path
from typing import Any

import click

from .config import load_config
from .embeddings.registry import create_embedder_from_config
from .indexer import CoreIndexer
from .indexer_logging import setup_logging
from .storage.registry import create_store_from_config

# Only import these if they're available
try:
    from .git_hooks import GitHooksManager
    from .service import IndexingService

    SERVICE_AVAILABLE = True
except ImportError:
    SERVICE_AVAILABLE = False

try:
    import click

    CLICK_AVAILABLE = True
except ImportError:
    CLICK_AVAILABLE = False


# Minimal CLI function for when Click is not available
def cli() -> None:
    """Claude Code Memory Indexer - Universal semantic indexing for codebases."""
    if not CLICK_AVAILABLE:
        from .indexer_logging import get_logger

        logger = get_logger()
        logger.error("Click not available. Install with: pip install click")
        sys.exit(1)


# Skip Click decorators and complex CLI setup when Click is not available
if not CLICK_AVAILABLE:
    # Early exit to prevent decorator errors during import
    import sys

    # Don't process the rest of the file to avoid decorator errors
    sys.modules[__name__].__dict__.update(locals())
    if __name__ == "__main__":
        cli()
        sys.exit(1)
else:
    # Only define Click-based CLI when Click is available

    # Common options as decorators
    def common_options(f: Any) -> Any:
        """Common options for indexing commands."""
        f = click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")(
            f
        )
        f = click.option(
            "--quiet", "-q", is_flag=True, help="Suppress non-error output"
        )(f)
        f = click.option(
            "--config", type=click.Path(exists=True), help="Configuration file path"
        )(f)
        return f

    def project_options(f: Any) -> Any:
        """Project-specific options."""
        f = click.option(
            "--project",
            "-p",
            type=click.Path(),
            required=True,
            help="Project directory path",
        )(f)
        f = click.option(
            "--collection",
            "-c",
            required=True,
            help="Collection name for vector storage",
        )(f)
        return f

    @click.group(invoke_without_command=True)
    @click.version_option(version="1.0.0")
    @click.pass_context
    def cli(ctx: Any) -> None:
        """Claude Code Memory Indexer - Universal semantic indexing for codebases."""
        # If no subcommand, this will be handled by the default routing in wrapper
        pass

    @cli.command()
    @project_options
    @common_options
    @click.option(
        "--include-tests", is_flag=True, help="Include test files in indexing"
    )
    @click.option(
        "--clear",
        is_flag=True,
        help="Clear code-indexed memories before indexing (preserves manual memories)",
    )
    @click.option(
        "--clear-all",
        is_flag=True,
        help="Clear ALL memories before indexing (including manual ones)",
    )
    @click.option(
        "--depth",
        type=click.Choice(["basic", "full"]),
        default="full",
        help="Analysis depth",
    )
    @click.option(
        "--files-from-stdin",
        is_flag=True,
        help="Read file paths from stdin (one per line) for batch indexing",
    )
    def index(
        project,
        collection,
        verbose,
        quiet,
        config,
        include_tests,
        clear,
        clear_all,
        depth,
        files_from_stdin,
    ):
        """Index an entire project or specific files from stdin."""

        if quiet and verbose:
            click.echo("Error: --quiet and --verbose are mutually exclusive", err=True)
            sys.exit(1)

        try:
            # Validate project path first
            project_path = Path(project).resolve()
            if not project_path.exists():
                click.echo(
                    f"Error: Project path does not exist: {project_path}", err=True
                )
                sys.exit(1)

            # Setup logging with collection-specific file logging and project path
            setup_logging(
                quiet=quiet,
                verbose=verbose,
                collection_name=collection,
                project_path=project_path,
            )

            # Load configuration
            config_obj = load_config(Path(config) if config else None)

            # Create components using direct Qdrant integration
            # Enable persistent embedding cache in project directory
            cache_dir = Path(project_path) / ".index_cache"
            embedder = create_embedder_from_config(config_obj, cache_dir=cache_dir)

            vector_store = create_store_from_config(
                {
                    "backend": "qdrant",
                    "url": config_obj.qdrant_url,
                    "api_key": config_obj.qdrant_api_key,
                    "enable_caching": True,
                }
            )

            if not quiet and verbose:
                provider_name = (
                    config_obj.embedding_provider.title()
                    if config_obj.embedding_provider
                    else "OpenAI"
                )
                click.echo(f"⚡ Using Qdrant + {provider_name} (direct mode)")

            # Create indexer
            indexer = CoreIndexer(config_obj, embedder, vector_store, project_path)

            # Clear collection if requested
            if clear or clear_all:
                if clear and clear_all:
                    click.echo(
                        "Error: --clear and --clear-all are mutually exclusive",
                        err=True,
                    )
                    sys.exit(1)

                preserve_manual = (
                    not clear_all
                )  # clear preserves manual, clear_all doesn't
                if not quiet:
                    if clear_all:
                        click.echo(
                            f"🗑️ Clearing ALL memories in collection: {collection}"
                        )
                    else:
                        click.echo(
                            f"🗑️ Clearing code-indexed memories in collection: {collection}"
                        )

                # Clear the log file for this collection
                from .indexer_logging import clear_log_file
                log_cleared = clear_log_file(collection, project_path)
                if not quiet and log_cleared:
                    click.echo(f"🗑️ Cleared log file for collection: {collection}")

                success = indexer.clear_collection(
                    collection, preserve_manual=preserve_manual
                )
                if not success:
                    click.echo("❌ Failed to clear collection", err=True)
                    sys.exit(1)
                elif not quiet:
                    if clear_all:
                        click.echo("✅ All memories cleared")
                    else:
                        click.echo(
                            "✅ Code-indexed memories cleared (manual memories preserved)"
                        )

                # Exit after clearing - don't auto-index
                return

            # Handle --files-from-stdin for batch indexing of specific files
            if files_from_stdin:
                import sys as sys_module

                # Read file paths from stdin
                file_paths = []
                for line in sys_module.stdin:
                    line = line.strip()
                    if line:
                        file_path = Path(line)
                        # Handle relative paths
                        if not file_path.is_absolute():
                            file_path = project_path / file_path
                        file_path = file_path.resolve()

                        # Validate file exists and is within project
                        if file_path.exists() and file_path.is_file():
                            try:
                                file_path.relative_to(project_path)
                                file_paths.append(file_path)
                            except ValueError:
                                if not quiet:
                                    click.echo(f"⚠️ Skipping {line}: not within project", err=True)
                        elif not quiet:
                            click.echo(f"⚠️ Skipping {line}: file not found", err=True)

                if not file_paths:
                    if not quiet:
                        click.echo("No valid files to index from stdin")
                    return

                if not quiet:
                    click.echo(f"📁 Batch indexing {len(file_paths)} files from stdin")

                # Use batch indexing method
                result = indexer.index_files(
                    file_paths=file_paths,
                    collection_name=collection,
                )

                # Report results
                if result.success:
                    if not quiet:
                        click.echo(f"✅ Batch indexing completed in {result.processing_time:.1f}s")
                        click.echo(f"   Files processed: {result.files_processed}")
                        click.echo(f"   Entities: {result.entities_created}")
                        click.echo(f"   Relations: {result.relations_created}")
                else:
                    click.echo("❌ Batch indexing failed", err=True)
                    for error in result.errors or []:
                        click.echo(f"   {error}", err=True)
                    sys.exit(1)

                return

            # Auto-detect incremental mode and run indexing only if not clearing
            state_file = indexer._get_state_file(collection)
            incremental = state_file.exists()

            if not quiet and verbose:
                click.echo(f"🔄 Indexing project: {project_path}")
                click.echo(f"📦 Collection: {collection}")
                if incremental:
                    click.echo("⚡ Mode: Incremental (auto-detected)")
                else:
                    click.echo("🔄 Mode: Full (auto-detected)")

            result = indexer.index_project(
                collection_name=collection, include_tests=include_tests
            )

            # Report results
            if result.success:
                if not quiet:
                    # Load previous statistics for comparison
                    from .indexer import format_change

                    prev_stats = indexer._load_previous_statistics(collection)

                    # Get total tracked files from state (not just current run)
                    state = indexer._load_state(collection)
                    total_tracked = len(
                        [k for k in state if not k.startswith("_")]
                    )

                    # Get file change details for this run
                    new_files, modified_files, deleted_files = (
                        indexer._categorize_file_changes(False, collection)
                    )

                    click.echo(
                        f"✅ Indexing completed in {result.processing_time:.1f}s"
                    )
                    click.echo(
                        f"   Total Vectored Files:    {format_change(total_tracked, prev_stats.get('total_tracked', 0)):>6}"
                    )
                    click.echo(
                        f"   Total tracked files:     {format_change(total_tracked, prev_stats.get('total_tracked', 0)):>6}"
                    )

                    # Show file changes if any
                    if new_files or modified_files or deleted_files:
                        click.echo("   📁 File Changes:")
                        for file_path in new_files:
                            rel_path = file_path.relative_to(indexer.project_path)
                            click.echo(f"      + {rel_path}")
                        for file_path in modified_files:
                            rel_path = file_path.relative_to(indexer.project_path)
                            click.echo(f"      = {rel_path}")
                        for deleted_file in deleted_files:
                            click.echo(f"      - {deleted_file}")
                    # Get actual database counts using direct Qdrant client
                    try:
                        from qdrant_client.http import models

                        # Access the underlying QdrantStore client (bypass ManagedVectorStore wrapper)
                        if hasattr(indexer.vector_store, "backend"):
                            qdrant_client = indexer.vector_store.backend.client
                        else:
                            qdrant_client = indexer.vector_store.client

                        # Direct database count queries (proven to work)
                        metadata_filter = models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="chunk_type",
                                    match=models.MatchValue(value="metadata"),
                                )
                            ]
                        )
                        implementation_filter = models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="chunk_type",
                                    match=models.MatchValue(value="implementation"),
                                )
                            ]
                        )
                        relation_filter = models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="chunk_type",
                                    match=models.MatchValue(value="relation"),
                                )
                            ]
                        )

                        metadata_count = qdrant_client.count(
                            collection, count_filter=metadata_filter
                        ).count
                        implementation_count = qdrant_client.count(
                            collection, count_filter=implementation_filter
                        ).count
                        relation_count = qdrant_client.count(
                            collection, count_filter=relation_filter
                        ).count

                    except Exception:
                        # Fallback to current run counts if database query fails
                        metadata_count = result.entities_created
                        implementation_count = result.implementation_chunks_created
                        relation_count = result.relations_created

                    click.echo(
                        f"   💻 Implementation:      {format_change(implementation_count, prev_stats.get('implementation_chunks_created', 0)):>6}"
                    )
                    click.echo(
                        f"   🔗 Relation:         {format_change(relation_count, prev_stats.get('relations_created', 0)):>6}"
                    )
                    click.echo(
                        f"   📋 Metadata:          {format_change(metadata_count, prev_stats.get('entities_created', 0)):>6}"
                    )

                    # Save current statistics for next run (including total tracked count)
                    import time

                    state = indexer._load_state(collection)
                    state["_statistics"] = {
                        "files_processed": result.files_processed,
                        "total_tracked": total_tracked,
                        "entities_created": metadata_count,
                        "relations_created": relation_count,
                        "implementation_chunks_created": implementation_count,
                        "processing_time": result.processing_time,
                        "timestamp": time.time(),
                    }

                    # Save updated state
                    state_file = indexer._get_state_file(collection)
                    state_file.parent.mkdir(parents=True, exist_ok=True)
                    temp_file = state_file.with_suffix(".tmp")
                    import json

                    with open(temp_file, "w") as f:
                        json.dump(state, f, indent=2)
                    temp_file.rename(state_file)

                    # Report cost information if available
                    if result.total_tokens > 0:
                        click.echo("💰 OpenAI Usage:")
                        click.echo(f"   Tokens consumed: {result.total_tokens:,}")
                        if result.embedding_requests > 0:
                            click.echo(f"   API requests: {result.embedding_requests}")
                        if result.total_cost_estimate > 0:
                            # Format cost nicely based on amount
                            if result.total_cost_estimate < 0.01:
                                click.echo(
                                    f"   Estimated cost: ${result.total_cost_estimate:.6f}"
                                )
                            else:
                                click.echo(
                                    f"   Estimated cost: ${result.total_cost_estimate:.4f}"
                                )

                        # Check pricing accuracy and show current model info
                        if hasattr(embedder, "get_model_info"):
                            model_info = embedder.get_model_info()
                            model_name = model_info.get("model", "unknown")
                            cost_per_1k = model_info.get("cost_per_1k_tokens", 0)
                            click.echo(
                                f"   Model: {model_name} (${cost_per_1k:.5f}/1K tokens)"
                            )

                    if result.warnings and verbose:
                        click.echo("⚠️  Warnings:")
                        for warning in result.warnings:
                            click.echo(f"   {warning}")
            else:
                click.echo("❌ Indexing failed", err=True)
                for error in result.errors:
                    click.echo(f"   {error}", err=True)
                sys.exit(1)

        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            if verbose:
                import traceback

                traceback.print_exc()
            sys.exit(1)

    @cli.command()
    @click.option(
        "-p",
        "--project",
        "project_path",
        required=True,
        type=click.Path(exists=True),
        help="Project directory path",
    )
    @click.option("-c", "--collection", required=True, help="Collection name")
    @click.option("--force", is_flag=True, help="Overwrite existing config")
    def init(project_path: str, collection: str, force: bool) -> None:
        """Initialize project configuration."""
        from .config.project_config import ProjectConfigManager

        manager = ProjectConfigManager(Path(project_path))

        # Derive project name from path
        name = Path(project_path).name

        # Check if already exists
        if manager.exists and not force:
            click.echo(f"❌ Project config already exists at {manager.config_path}")
            click.echo("Use --force to overwrite")
            return

        # Create default config
        config = manager.create_default(name, collection)

        # Save it
        manager.save(config)

        click.echo(f"✅ Created project config at {manager.config_path}")
        click.echo(f"📁 Project: {name}")
        click.echo(f"🗄️  Collection: {collection}")
        click.echo(
            f"📝 Include patterns: {', '.join(config.indexing.file_patterns.include)}"
        )

    @cli.command()
    @click.option(
        "-p",
        "--project",
        "project_path",
        type=click.Path(exists=True),
        help="Project directory path",
    )
    def show_config(project_path: str) -> None:
        """Show effective configuration for project."""
        from .config.config_loader import ConfigLoader

        path = Path(project_path) if project_path else Path.cwd()
        loader = ConfigLoader(path)

        try:
            config = loader.load()

            click.echo("📋 Effective Configuration:")
            click.echo(f"📁 Project Path: {path}")
            click.echo(
                f"🗄️  Collection: {getattr(config, 'collection_name', 'Not set')}"
            )
            click.echo(f"📝 Include Patterns: {', '.join(config.include_patterns)}")
            click.echo(f"🚫 Exclude Patterns: {', '.join(config.exclude_patterns)}")
            click.echo(f"📏 Max File Size: {config.max_file_size:,} bytes")
            click.echo(f"⏱️  Debounce: {config.debounce_seconds}s")

        except Exception as e:
            click.echo(f"❌ Failed to load configuration: {e}", err=True)
            sys.exit(1)

    @cli.command()
    @project_options
    @common_options
    @click.argument("file_path", type=click.Path(exists=True))
    def file(project, collection, file_path, verbose, quiet, config) -> None:
        """Index a single file."""

        try:
            # Load configuration
            config_obj = load_config(Path(config) if config else None)

            # Validate paths
            project_path = Path(project).resolve()
            target_file = Path(file_path).resolve()

            # Ensure file is within project
            try:
                target_file.relative_to(project_path)
            except ValueError:
                click.echo("Error: File must be within project directory", err=True)
                sys.exit(1)

            # Create components using dynamic provider detection
            # Enable persistent embedding cache
            cache_dir = project_path / ".index_cache"
            embedder = create_embedder_from_config(config_obj, cache_dir=cache_dir)

            vector_store = create_store_from_config(
                {
                    "backend": "qdrant",
                    "url": config_obj.qdrant_url,
                    "api_key": config_obj.qdrant_api_key,
                    "enable_caching": True,
                }
            )

            # Create indexer and process file
            indexer = CoreIndexer(config_obj, embedder, vector_store, project_path)

            if not quiet:
                click.echo(f"🔄 Indexing file: {target_file.relative_to(project_path)}")

            result = indexer.index_single_file(target_file, collection)

            # Report results
            if result.success:
                if not quiet:
                    click.echo(f"✅ File indexed in {result.processing_time:.1f}s")
                    click.echo(f"   Entities: {result.entities_created}")
                    click.echo(f"   Relations: {result.relations_created}")
            else:
                click.echo("❌ File indexing failed", err=True)
                for error in result.errors:
                    click.echo(f"   {error}", err=True)
                sys.exit(1)

        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            sys.exit(1)

    @cli.group()
    def watch() -> None:
        """File watching commands."""
        pass

    @watch.command()
    @project_options
    @common_options
    @click.option(
        "--debounce",
        type=float,
        default=2.0,
        help="Debounce delay in seconds (default: 2.0)",
    )
    @click.option(
        "--clear",
        is_flag=True,
        help="Clear code-indexed memories before watching (preserves manual memories)",
    )
    @click.option(
        "--clear-all",
        is_flag=True,
        help="Clear ALL memories before watching (including manual ones)",
    )
    @click.pass_context
    def start(
        ctx, project, collection, verbose, quiet, config, debounce, clear, clear_all
    ):
        """Start file watching for real-time indexing."""

        try:
            from watchdog.observers import Observer

            from .service import IndexingService
            from .watcher.handler import IndexingEventHandler

            # Validate project path first
            project_path = Path(project).resolve()
            if not project_path.exists():
                click.echo(
                    f"Error: Project path does not exist: {project_path}", err=True
                )
                sys.exit(1)

            # Setup logging with project path
            logger = setup_logging(
                quiet=quiet,
                verbose=verbose,
                collection_name=collection,
                project_path=project_path,
            )

            # Load configuration
            config_obj = load_config(Path(config) if config else None)

            # Handle clearing if requested
            if clear or clear_all:
                if clear and clear_all:
                    click.echo(
                        "Error: --clear and --clear-all are mutually exclusive",
                        err=True,
                    )
                    sys.exit(1)

                # Create components for clearing
                cache_dir = project_path / ".index_cache"
                embedder = create_embedder_from_config(config_obj, cache_dir=cache_dir)
                vector_store = create_store_from_config(
                    {
                        "backend": "qdrant",
                        "url": config_obj.qdrant_url,
                        "api_key": config_obj.qdrant_api_key,
                        "enable_caching": True,
                    }
                )
                indexer = CoreIndexer(config_obj, embedder, vector_store, project_path)

                preserve_manual = (
                    not clear_all
                )  # clear preserves manual, clear_all doesn't
                if not quiet:
                    if clear_all:
                        click.echo(
                            f"🗑️ Clearing ALL memories in collection: {collection}"
                        )
                    else:
                        click.echo(
                            f"🗑️ Clearing code-indexed memories in collection: {collection}"
                        )

                success = indexer.clear_collection(
                    collection, preserve_manual=preserve_manual
                )
                if not success:
                    click.echo("❌ Failed to clear collection", err=True)
                    sys.exit(1)
                elif not quiet:
                    if clear_all:
                        click.echo("✅ All memories cleared")
                    else:
                        click.echo(
                            "✅ Code-indexed memories cleared (manual memories preserved)"
                        )

            # Load project configuration for file patterns
            from claude_indexer.config.project_config import ProjectConfigManager

            try:
                project_manager = ProjectConfigManager(project_path)
                include_patterns = project_manager.get_include_patterns()
                exclude_patterns = project_manager.get_exclude_patterns()
            except Exception as e:
                logger.debug(f"Could not load project config, using defaults: {e}")
                include_patterns = [
                    "*.py",
                    "*.pyi",
                    "*.js",
                    "*.jsx",
                    "*.ts",
                    "*.tsx",
                    "*.mjs",
                    "*.cjs",
                    "*.html",
                    "*.htm",
                    "*.css",
                    "*.json",
                    "*.yaml",
                    "*.yml",
                    "*.md",
                    "*.txt",
                ]
                exclude_patterns = [
                    "*.pyc",
                    "__pycache__/",
                    ".git/",
                    ".venv/",
                    "node_modules/",
                    "dist/",
                    "build/",
                    "*.min.js",
                    ".env",
                    "*.log",
                    "logs/",
                    ".mypy_cache/",
                    ".pytest_cache/",
                    ".tox/",
                    ".coverage",
                    "htmlcov/",
                    "coverage/",
                    ".cache/",
                    "test-results/",
                    "playwright-report/",
                    ".idea/",
                    ".vscode/",
                    ".zed/",
                    ".DS_Store",
                    "Thumbs.db",
                    "Desktop.ini",
                    ".npm/",
                    ".next/",
                    ".parcel-cache/",
                    "*.tsbuildinfo",
                    "*.map",
                    "*.db",
                    "*.sqlite3",
                    "chroma_db/",
                    "*.tmp",
                    "*.bak",
                    "*.old",
                    "debug/",
                    "qdrant_storage/",
                    "backups/",
                    "*.egg-info",
                    "settings.txt",
                    ".claude-indexer/",
                    ".claude/",
                    "package-lock.json",
                    "memory_guard_debug.txt",
                ]

            # Load service configuration for other settings
            service = IndexingService()
            service_config = service.load_config()
            service_settings = service_config.get("settings", {})

            # Determine effective debounce using proper configuration hierarchy
            # CLI override > settings.txt > built-in default (no JSON config)
            debounce_explicitly_set = (
                "debounce" in ctx.params
                and ctx.get_parameter_source("debounce")
                != click.core.ParameterSource.DEFAULT
            )
            if debounce_explicitly_set:
                effective_debounce = debounce
            elif hasattr(config_obj, "debounce_seconds"):
                effective_debounce = config_obj.debounce_seconds
            else:
                effective_debounce = 2.0

            # Create event handler with project and service configuration
            settings = {
                "debounce_seconds": effective_debounce,
                "watch_patterns": include_patterns,  # Use project config patterns
                "ignore_patterns": exclude_patterns,  # Use project config patterns
                "max_file_size": service_settings.get("max_file_size", 1048576),
                "enable_logging": service_settings.get("enable_logging", True),
            }

            event_handler = IndexingEventHandler(
                project_path=str(project_path),
                collection_name=collection,
                debounce_seconds=effective_debounce,
                settings=settings,
                verbose=verbose,
            )

            # Run initial incremental indexing before starting file watching
            logger.info("🔄 Running initial incremental indexing...")

            from claude_indexer.main import run_indexing

            try:
                run_indexing(
                    project_path=str(project_path),
                    collection_name=collection,
                    quiet=quiet,
                    verbose=verbose,
                )
                logger.info("✅ Initial indexing complete")
            except Exception as e:
                logger.warning(f"⚠️ Initial indexing failed: {e}")
                logger.info("📁 Continuing with file watching...")

            # Start observer
            observer = Observer()
            observer.schedule(event_handler, str(project_path), recursive=True)
            observer.start()

            logger.info(f"👁️  Watching: {project_path}")
            logger.info(f"📦 Collection: {collection}")
            logger.info(f"⏱️  Debounce: {effective_debounce}s")
            logger.info("Press Ctrl+C to stop")

            # Setup signal handling
            import signal

            def signal_handler(signum, frame):
                observer.stop()
                logger.info(f"\n🛑 Received signal {signum}, stopping file watcher...")
                raise KeyboardInterrupt()

            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

            try:
                while True:
                    import time

                    time.sleep(1)
            except KeyboardInterrupt:
                observer.stop()
                observer.join(timeout=3)  # Add timeout
                if observer.is_alive():
                    logger.warning("⚠️ Force stopping watcher")

            logger.info("✅ File watcher stopped")

        except ImportError:
            click.echo(
                "Error: Watchdog not available. Install with: pip install watchdog",
                err=True,
            )
            sys.exit(1)
        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            sys.exit(1)

    @cli.group()
    def service() -> None:
        """Background service commands."""
        pass

    @service.command("start")
    @common_options
    @click.option(
        "--config-file", type=click.Path(), help="Service configuration file path"
    )
    def start_service(verbose, quiet, config, config_file):
        """Start the background indexing service."""

        try:
            svc = IndexingService(config_file)

            if not quiet:
                click.echo("🚀 Starting background indexing service...")

            success = svc.start()

            if not success:
                click.echo("❌ Failed to start service", err=True)
                sys.exit(1)

        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            sys.exit(1)

    @service.command("add-project")
    @click.argument("project_path", type=click.Path(exists=True))
    @click.argument("collection_name")
    @common_options
    @click.option(
        "--config-file", type=click.Path(), help="Service configuration file path"
    )
    def add_project(project_path, collection_name, verbose, quiet, config, config_file):
        """Add a project to the service watch list."""

        try:
            svc = IndexingService(config_file)
            project_path = str(Path(project_path).resolve())

            success = svc.add_project(project_path, collection_name)

            if success:
                if not quiet:
                    click.echo(f"✅ Added project: {project_path} -> {collection_name}")
            else:
                click.echo("❌ Failed to add project", err=True)
                sys.exit(1)

        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            sys.exit(1)

    @service.command("status")
    @common_options
    @click.option(
        "--config-file", type=click.Path(), help="Service configuration file path"
    )
    def service_status(verbose, quiet, config, config_file):
        """Show service status."""

        try:
            svc = IndexingService(config_file)
            status_info = svc.get_status()

            click.echo(
                f"Service Status: {'🟢 Running' if status_info['running'] else '🔴 Stopped'}"
            )
            click.echo(f"Config file: {status_info['config_file']}")
            click.echo(f"Projects: {status_info['total_projects']}")
            click.echo(f"Active watchers: {status_info['active_watchers']}")

            if verbose and status_info["watchers"]:
                click.echo("\nWatchers:")
                for project, info in status_info["watchers"].items():
                    status = "🟢 Running" if info["running"] else "🔴 Stopped"
                    click.echo(f"  {project}: {status}")

        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            sys.exit(1)

    @cli.group()
    def hooks():
        """Git hooks management."""
        pass

    @hooks.command()
    @project_options
    @common_options
    @click.option("--indexer-path", help="Path to indexer executable")
    def install(project, collection, verbose, quiet, config, indexer_path):
        """Install git pre-commit hook."""

        try:
            project_path = Path(project).resolve()
            hooks_manager = GitHooksManager(str(project_path), collection)

            success = hooks_manager.install_pre_commit_hook(indexer_path, quiet=quiet)

            if not success:
                sys.exit(1)

        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            sys.exit(1)

    @hooks.command()
    @project_options
    @common_options
    def uninstall(project, collection, verbose, quiet, config):
        """Uninstall git pre-commit hook."""

        try:
            project_path = Path(project).resolve()
            hooks_manager = GitHooksManager(str(project_path), collection)

            success = hooks_manager.uninstall_pre_commit_hook(quiet=quiet)

            if not success:
                sys.exit(1)

        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            sys.exit(1)

    @hooks.command("status")
    @project_options
    @common_options
    def hooks_status(project, collection, verbose, quiet, config):
        """Show git hooks status."""

        try:
            project_path = Path(project).resolve()
            hooks_manager = GitHooksManager(str(project_path), collection)

            status_info = hooks_manager.get_hook_status()

            click.echo(
                f"Git repository: {'✅' if status_info['is_git_repo'] else '❌'}"
            )
            click.echo(
                f"Hooks directory: {'✅' if status_info['hooks_dir_exists'] else '❌'}"
            )
            click.echo(
                f"Pre-commit hook: {'✅ Installed' if status_info['hook_installed'] else '❌ Not installed'}"
            )

            if status_info["hook_installed"]:
                click.echo(
                    f"Hook executable: {'✅' if status_info['hook_executable'] else '❌'}"
                )
                if verbose and "indexer_command" in status_info:
                    click.echo(f"Command: {status_info['indexer_command']}")

        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            sys.exit(1)

    @cli.command()
    @project_options
    @click.argument("query")
    @click.option("--limit", type=int, default=10, help="Maximum results")
    @click.option(
        "--type",
        "result_type",
        type=click.Choice(["entity", "relation", "chat", "all"]),
        help="Filter by result type (default: all)",
    )
    @common_options
    def search(project, collection, query, limit, result_type, verbose, quiet, config):
        """Search across code entities, relations, and chat conversations."""

        try:
            # Load configuration
            config_obj = load_config(Path(config) if config else None)

            # Create components using dynamic provider detection
            # Enable persistent cache for search queries
            project_path = Path(project).resolve() if project else Path.cwd()
            cache_dir = project_path / ".index_cache"
            embedder = create_embedder_from_config(config_obj, cache_dir=cache_dir)

            vector_store = create_store_from_config(
                {
                    "backend": "qdrant",
                    "url": config_obj.qdrant_url,
                    "api_key": config_obj.qdrant_api_key,
                }
            )

            # Create indexer and search
            project_path = Path(project).resolve()
            indexer = CoreIndexer(config_obj, embedder, vector_store, project_path)

            # Handle unified search across different types
            if result_type == "all" or result_type is None:
                # Search all types and combine results
                all_results = []

                # Search code entities and relations
                code_results = indexer.search_similar(collection, query, limit, None)
                all_results.extend(code_results)

                # Search chat conversations specifically
                chat_results = indexer.search_similar(
                    collection, query, limit, "chat_history"
                )
                all_results.extend(chat_results)

                # Sort by score and limit to requested amount
                all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
                results = all_results[:limit]
            elif result_type == "chat":
                # Search only chat conversations
                results = indexer.search_similar(
                    collection, query, limit, "chat_history"
                )
            else:
                # Search specific type (entity, relation)
                results = indexer.search_similar(collection, query, limit, result_type)

            if results:
                if not quiet:
                    click.echo(f"🔍 Found {len(results)} results for: {query}")
                    click.echo()

                for i, result in enumerate(results, 1):
                    score = result.get("score", 0)
                    payload = result.get("payload", {})

                    # Try both 'name' and 'entity_name' fields for compatibility
                    entity_name = payload.get("name") or payload.get(
                        "entity_name", "Unknown"
                    )
                    click.echo(f"{i}. {entity_name} (score: {score:.3f})")

                    if verbose:
                        entity_type = payload.get(
                            "entity_type", payload.get("type", "unknown")
                        )
                        click.echo(f"   Type: {entity_type}")

                        if payload.get("metadata", {}).get("file_path"):
                            click.echo(f"   File: {payload.get('metadata', {}).get('file_path')}")

                        if "observations" in payload:
                            obs = payload["observations"][:2]  # First 2 observations
                            for ob in obs:
                                click.echo(f"   📝 {ob}")

                        click.echo()
            else:
                if not quiet:
                    click.echo(f"🔍 No results found for: {query}")

        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            sys.exit(1)

    @cli.command("add-mcp")
    @click.option(
        "--collection", "-c", required=True, help="Collection name for MCP server"
    )
    @common_options
    def add_mcp(collection, verbose, quiet, config):
        """Add MCP server configuration for a collection."""

        try:
            # Validate collection name
            if not collection.replace("-", "").replace("_", "").isalnum():
                click.echo(
                    "❌ Collection name should only contain letters, numbers, hyphens, and underscores",
                    err=True,
                )
                sys.exit(1)

            if not quiet:
                click.echo(f"🔧 Setting up MCP server for collection: {collection}")

            # Load configuration
            config_obj = load_config(Path(config) if config else None)

            # Determine MCP server path (relative to current script location)
            script_dir = Path(
                __file__
            ).parent.parent.absolute()  # Go up to project root
            mcp_server_path = script_dir / "mcp-qdrant-memory" / "dist" / "index.js"

            if not mcp_server_path.exists():
                click.echo(f"❌ MCP server not found at: {mcp_server_path}", err=True)
                click.echo("Run the installation steps first:", err=True)
                click.echo(
                    "git clone https://github.com/delorenj/mcp-qdrant-memory.git",
                    err=True,
                )
                click.echo(
                    "cd mcp-qdrant-memory && npm install && npm run build", err=True
                )
                sys.exit(1)

            server_name = f"{collection}-memory"

            # Build command to add MCP server
            cmd = [
                "claude",
                "mcp",
                "add",
                server_name,
                "-e",
                f"OPENAI_API_KEY={config_obj.openai_api_key}",
                "-e",
                f"QDRANT_API_KEY={config_obj.qdrant_api_key}",
                "-e",
                f"QDRANT_URL={config_obj.qdrant_url}",
                "-e",
                f"QDRANT_COLLECTION_NAME={collection}",
                "--",
                "node",
                str(mcp_server_path),
            ]

            # Add Voyage AI settings if configured
            if hasattr(config_obj, "voyage_api_key") and config_obj.voyage_api_key:
                cmd.insert(-3, "-e")
                cmd.insert(-3, f"VOYAGE_API_KEY={config_obj.voyage_api_key}")

            if (
                hasattr(config_obj, "embedding_provider")
                and config_obj.embedding_provider
            ):
                cmd.insert(-3, "-e")
                cmd.insert(-3, f"EMBEDDING_PROVIDER={config_obj.embedding_provider}")

            if hasattr(config_obj, "voyage_model") and config_obj.voyage_model:
                cmd.insert(-3, "-e")
                cmd.insert(-3, f"EMBEDDING_MODEL={config_obj.voyage_model}")

            if verbose:
                click.echo(f"🚀 Adding MCP server: {server_name}")
                click.echo(f"📊 Collection name: {collection}")
                click.echo(f"🔗 Server path: {mcp_server_path}")

            # Execute the command
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                if not quiet:
                    click.echo("✅ MCP server added successfully!")
                    click.echo(f"🎯 Server name: {server_name}")
                    click.echo(f"📁 Collection: {collection}")
                    click.echo()
                    click.echo("Next steps:")
                    click.echo("1. Restart Claude Code")
                    click.echo(
                        f"2. Index your project: claude-indexer --project /path/to/project --collection {collection}"
                    )
                    click.echo(
                        f"3. Test search: mcp__{server_name.replace('-', '_')}__search_similar('your query')"
                    )
            else:
                click.echo("❌ Failed to add MCP server", err=True)
                if verbose:
                    click.echo(f"STDOUT: {result.stdout}", err=True)
                    click.echo(f"STDERR: {result.stderr}", err=True)
                sys.exit(1)

        except FileNotFoundError:
            click.echo("❌ 'claude' command not found", err=True)
            click.echo("Make sure Claude Code is installed and in your PATH", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            if verbose:
                import traceback

                traceback.print_exc()
            sys.exit(1)

    @cli.group()
    def chat():
        """Chat history indexing and summarization commands."""
        pass

    @chat.command("index")
    @project_options
    @common_options
    @click.option(
        "--limit",
        "-l",
        type=int,
        default=None,
        help="Limit number of conversations to process",
    )
    @click.option(
        "--inactive-hours",
        type=float,
        default=1.0,
        help="Consider conversations inactive after N hours",
    )
    def chat_index(project, collection, verbose, quiet, config, limit, inactive_hours):
        """Index Claude Code chat history files for a project."""
        try:
            # Load configuration
            config_obj = load_config(Path(config) if config else None)

            # Create components with persistent cache
            project_path = Path(project).resolve() if project else Path.cwd()
            cache_dir = project_path / ".index_cache"
            embedder = create_embedder_from_config(config_obj, cache_dir=cache_dir)
            store = create_store_from_config(config_obj)

            # Import chat modules
            from .chat.parser import ChatParser
            from .chat.summarizer import ChatSummarizer

            if not quiet:
                click.echo("⚡ Starting chat history indexing...")

            # Initialize chat parser and summarizer
            parser = ChatParser()
            summarizer = ChatSummarizer(config_obj)

            # Parse conversations
            project_path = Path(project).resolve()
            conversations = parser.parse_all_chats(project_path, limit=limit)

            if not conversations:
                if not quiet:
                    click.echo("📭 No chat conversations found")
                return

            # Filter inactive conversations if requested
            if inactive_hours > 0:
                active_conversations = [
                    conv
                    for conv in conversations
                    if not conv.metadata.is_inactive(inactive_hours)
                ]
                if not quiet and len(active_conversations) != len(conversations):
                    click.echo(
                        f"🔍 Filtered to {len(active_conversations)} active conversations (inactive threshold: {inactive_hours}h)"
                    )
                conversations = active_conversations

            if not conversations:
                if not quiet:
                    click.echo("📭 No active conversations found")
                return

            if not quiet:
                click.echo(f"📚 Processing {len(conversations)} conversations...")

            # Generate summaries
            summaries = summarizer.batch_summarize(conversations)

            # Store summaries as entities
            success_count = 0
            error_count = 0

            for conversation, summary in zip(conversations, summaries, strict=False):
                try:
                    # Create chat chunk from summary for v2.4 pure architecture
                    from .analysis.entities import ChatChunk

                    # Generate embedding
                    chat_content = " | ".join(summary.to_observations())
                    embedding_result = embedder.embed_text(chat_content)

                    if embedding_result.success:
                        # Create chat chunk
                        chat_chunk = ChatChunk(
                            id=f"chat::{conversation.summary_key}::summary",
                            chat_id=conversation.summary_key,
                            chunk_type="chat_summary",
                            content=chat_content,
                            timestamp=str(conversation.metadata.start_time)
                            if hasattr(conversation.metadata, "start_time")
                            else None,
                        )

                        # Create vector point
                        point = store.create_chat_chunk_point(
                            chat_chunk, embedding_result.embedding, collection
                        )

                        # Store in vector database
                        result = store.batch_upsert(collection, [point])

                        if result.success:
                            success_count += 1
                            if verbose:
                                click.echo(
                                    f"  ✅ Indexed: {conversation.metadata.session_id}"
                                )
                        else:
                            error_count += 1
                            if verbose:
                                click.echo(
                                    f"  ❌ Failed to store: {conversation.metadata.session_id}"
                                )
                    else:
                        error_count += 1
                        if verbose:
                            click.echo(
                                f"  ❌ Failed to embed: {conversation.metadata.session_id}"
                            )

                except Exception as e:
                    error_count += 1
                    if verbose:
                        click.echo(
                            f"  ❌ Error processing {conversation.metadata.session_id}: {e}"
                        )

            # Summary output
            if not quiet:
                if success_count > 0:
                    click.echo(
                        f"✅ Successfully indexed {success_count} chat conversations"
                    )
                if error_count > 0:
                    click.echo(f"❌ Failed to index {error_count} conversations")

        except Exception as e:
            click.echo(f"❌ Chat indexing failed: {e}", err=True)
            if verbose:
                import traceback

                traceback.print_exc()
            sys.exit(1)

    @chat.command()
    @project_options
    @common_options
    @click.option(
        "--output-dir", type=click.Path(), help="Output directory for summary files"
    )
    @click.option(
        "--format",
        type=click.Choice(["json", "markdown", "text"]),
        default="markdown",
        help="Output format",
    )
    def summarize(project, collection, verbose, quiet, config, output_dir, format):
        """Generate summary files from indexed chat conversations."""
        try:
            # Load configuration
            config_obj = load_config(Path(config) if config else None)

            # Import chat modules
            from .chat.parser import ChatParser
            from .chat.summarizer import ChatSummarizer

            if not quiet:
                click.echo("📝 Generating chat conversation summaries...")

            # Initialize components
            parser = ChatParser()
            summarizer = ChatSummarizer(config_obj)

            # Parse conversations
            project_path = Path(project).resolve()
            conversations = parser.parse_all_chats(project_path)

            if not conversations:
                if not quiet:
                    click.echo("📭 No chat conversations found")
                return

            # Generate summaries
            summaries = summarizer.batch_summarize(conversations)

            # Prepare output directory
            if output_dir:
                output_path = Path(output_dir)
                output_path.mkdir(parents=True, exist_ok=True)
            else:
                output_path = project_path / "chat_summaries"
                output_path.mkdir(exist_ok=True)

            # Write summary files
            success_count = 0
            for conversation, summary in zip(conversations, summaries, strict=False):
                try:
                    session_id = conversation.metadata.session_id

                    if format == "json":
                        import json

                        filename = f"{session_id}_summary.json"
                        content = {
                            "session_id": session_id,
                            "project_path": conversation.metadata.project_path,
                            "summary": summary.summary,
                            "key_insights": summary.key_insights,
                            "topics": summary.topics,
                            "category": summary.category,
                            "code_patterns": summary.code_patterns,
                            "debugging_info": summary.debugging_info,
                            "message_count": conversation.metadata.message_count,
                            "duration_minutes": conversation.metadata.duration_minutes,
                        }
                        with open(output_path / filename, "w") as f:
                            json.dump(content, f, indent=2)

                    elif format == "markdown":
                        filename = f"{session_id}_summary.md"
                        content = f"""# Chat Summary: {session_id}

**Project:** {conversation.metadata.project_path}
**Duration:** {conversation.metadata.duration_minutes:.1f} minutes
**Messages:** {conversation.metadata.message_count}
**Category:** {summary.category or "uncategorized"}

## Summary
{summary.summary}

## Key Insights
{chr(10).join(f"- {insight}" for insight in summary.key_insights)}

## Topics
{", ".join(summary.topics)}

## Code Patterns
{chr(10).join(f"- {pattern}" for pattern in summary.code_patterns)}

## Debugging Information
{chr(10).join(f"- **{k}:** {v}" for k, v in summary.debugging_info.items())}
"""
                        with open(output_path / filename, "w") as f:
                            f.write(content)

                    else:  # text format
                        filename = f"{session_id}_summary.txt"
                        content = f"""Chat Summary: {session_id}
Project: {conversation.metadata.project_path}
Duration: {conversation.metadata.duration_minutes:.1f} minutes
Messages: {conversation.metadata.message_count}
Category: {summary.category or "uncategorized"}

Summary:
{summary.summary}

Key Insights:
{chr(10).join(f"- {insight}" for insight in summary.key_insights)}

Topics: {", ".join(summary.topics)}
Code Patterns: {", ".join(summary.code_patterns)}
"""
                        with open(output_path / filename, "w") as f:
                            f.write(content)

                    success_count += 1
                    if verbose:
                        click.echo(f"  ✅ Generated: {filename}")

                except Exception as e:
                    if verbose:
                        click.echo(
                            f"  ❌ Failed to generate summary for {conversation.metadata.session_id}: {e}"
                        )

            if not quiet:
                click.echo(
                    f"✅ Generated {success_count} summary files in {output_path}"
                )

        except Exception as e:
            click.echo(f"❌ Summary generation failed: {e}", err=True)
            if verbose:
                import traceback

                traceback.print_exc()
            sys.exit(1)

    @chat.command("search")
    @project_options
    @common_options
    @click.argument("query")
    @click.option(
        "--limit", "-l", type=int, default=10, help="Maximum number of results"
    )
    def chat_search(project, collection, verbose, quiet, config, query, limit):
        """Search indexed chat conversations by content."""
        try:
            # Load configuration and create components with persistent cache
            config_obj = load_config(Path(config) if config else None)
            project_path = Path(project).resolve() if project else Path.cwd()
            cache_dir = project_path / ".index_cache"
            embedder = create_embedder_from_config(config_obj, cache_dir=cache_dir)
            store = create_store_from_config(config_obj)

            if not quiet:
                click.echo(f"🔍 Searching chat conversations for: {query}")

            # Generate query embedding
            embedding_result = embedder.embed_text(query)
            if not embedding_result.success:
                click.echo("❌ Failed to generate embedding for query", err=True)
                sys.exit(1)

            # Search vector store with chat_history filter
            search_result = store.search_similar(
                collection_name=collection,
                query_vector=embedding_result.embedding,
                limit=limit,
                filter_conditions={"type": "chat_history"},
            )

            if search_result.success and search_result.results:
                if not quiet:
                    click.echo(
                        f"📚 Found {len(search_result.results)} relevant conversations:"
                    )

                for i, result in enumerate(search_result.results, 1):
                    score = result.get("score", 0.0)
                    name = result.get("name", "Unknown")
                    observations = result.get("observations", [])

                    click.echo(f"\n{i}. **{name}** (similarity: {score:.3f})")
                    for obs in observations[:3]:  # Show first 3 observations
                        click.echo(f"   {obs}")
                    if len(observations) > 3:
                        click.echo(f"   ... and {len(observations) - 3} more")
            else:
                if not quiet:
                    click.echo(f"🔍 No chat conversations found for: {query}")

        except Exception as e:
            click.echo(f"❌ Search failed: {e}", err=True)
            if verbose:
                import traceback

                traceback.print_exc()
            sys.exit(1)

    @chat.command()
    @project_options
    @common_options
    @click.option(
        "--output",
        "-o",
        type=click.Path(),
        help="Output HTML file path (auto-generated if not specified)",
    )
    @click.option(
        "--conversation-id",
        help="Specific conversation ID to generate report for (uses most recent if not specified)",
    )
    def html_report(
        project, collection, verbose, quiet, config, output, conversation_id
    ):
        """Generate HTML report with GPT analysis and full conversation display."""
        try:
            # Load configuration
            config_obj = load_config(Path(config) if config else None)

            if not quiet:
                click.echo("📄 Generating HTML chat report...")

            # Import chat modules
            from .chat.html_report import ChatHtmlReporter
            from .chat.parser import ChatParser

            project_path = Path(project).resolve()
            if not project_path.exists():
                click.echo(f"❌ Project directory not found: {project_path}", err=True)
                sys.exit(1)

            # Initialize reporter and parser
            reporter = ChatHtmlReporter(config_obj)
            parser = ChatParser()

            # Determine conversation input
            if conversation_id:
                # Try to find specific conversation file
                chat_files = parser.get_chat_files(project_path)
                conversation_file = None
                for file_path in chat_files:
                    if conversation_id in file_path.stem:
                        conversation_file = file_path
                        break

                if not conversation_file:
                    click.echo(
                        f"❌ Conversation ID '{conversation_id}' not found", err=True
                    )
                    sys.exit(1)

                conversation_input = conversation_file
            else:
                # Use most recent conversation
                chat_files = parser.get_chat_files(project_path)
                if not chat_files:
                    click.echo(
                        f"❌ No chat conversations found for project: {project_path}",
                        err=True,
                    )
                    sys.exit(1)

                conversation_input = chat_files[0]  # Most recent

            if verbose:
                click.echo(f"📝 Processing conversation: {conversation_input}")

            # Generate output path if not specified
            output_path = None
            if output:
                output_path = Path(output)

            # Generate HTML report
            html_file = reporter.generate_report(conversation_input, output_path)

            if not quiet:
                click.echo(f"✅ HTML report generated: {html_file}")
                click.echo(f"🌐 Open in browser: file://{html_file.absolute()}")

        except Exception as e:
            click.echo(f"❌ HTML report generation failed: {e}", err=True)
            if verbose:
                import traceback

                traceback.print_exc()
            sys.exit(1)

    # ========================================
    # Quality Gates Commands (UI Consistency)
    # ========================================

    @cli.group("quality-gates")
    def quality_gates():
        """Quality gate commands for UI consistency checking."""
        pass

    @quality_gates.command("run")
    @click.argument("gate_type", type=click.Choice(["ui", "all"]))
    @click.option(
        "--project",
        "-p",
        type=click.Path(exists=True),
        default=".",
        help="Project directory path",
    )
    @click.option(
        "--base-branch",
        default="main",
        help="Base branch for comparison",
    )
    @click.option(
        "--format",
        "output_format",
        type=click.Choice(["json", "cli", "sarif"]),
        default="cli",
        help="Output format",
    )
    @click.option(
        "--output",
        "-o",
        type=click.Path(),
        help="Output file path",
    )
    @click.option(
        "--update-baseline",
        is_flag=True,
        help="Update baseline with current findings",
    )
    @click.option(
        "--no-cache",
        is_flag=True,
        help="Disable caching",
    )
    @click.option(
        "--no-clustering",
        is_flag=True,
        help="Disable cross-file clustering",
    )
    @common_options
    def run_quality_gate(
        gate_type,
        project,
        base_branch,
        output_format,
        output,
        update_baseline,
        no_cache,
        no_clustering,
        verbose,
        quiet,
        config,
    ):
        """Run quality gates.

        Examples:
            claude-indexer quality-gates run ui
            claude-indexer quality-gates run ui --format sarif --output report.sarif
            claude-indexer quality-gates run ui --base-branch develop
        """
        try:
            from .ui.ci import CIAuditConfig, CIAuditRunner
            from .ui.reporters.sarif import SARIFExporter

            project_path = Path(project).resolve()

            if not quiet:
                click.echo(f"🔍 Running UI quality gate on: {project_path}")

            # Create audit config
            audit_config = CIAuditConfig(
                base_branch=base_branch,
                enable_caching=not no_cache,
                enable_clustering=not no_clustering,
                update_baseline=update_baseline,
            )

            # Run audit
            runner = CIAuditRunner(
                project_path=project_path,
                audit_config=audit_config,
            )

            result = runner.run()

            # Output based on format
            if output_format == "sarif":
                exporter = SARIFExporter()
                sarif_doc = exporter.export(
                    result, Path(output) if output else None
                )
                if not output:
                    import json
                    click.echo(json.dumps(sarif_doc, indent=2))
            elif output_format == "json":
                import json
                output_data = result.to_dict()
                if output:
                    with open(output, "w") as f:
                        json.dump(output_data, f, indent=2)
                else:
                    click.echo(json.dumps(output_data, indent=2))
            else:
                # CLI format
                if not quiet:
                    click.echo()
                    click.echo(f"📊 UI Quality Gate Results")
                    click.echo(f"   Analysis time: {result.analysis_time_ms:.0f}ms")
                    click.echo(f"   Files analyzed: {result.files_analyzed}")
                    click.echo(f"   Cache hit rate: {result.cache_hit_rate:.1%}")
                    click.echo()

                    # New findings
                    if result.new_findings:
                        click.echo(f"🆕 New Findings ({len(result.new_findings)}):")
                        for finding in result.new_findings:
                            severity_icon = {
                                "FAIL": "❌",
                                "WARN": "⚠️",
                                "INFO": "ℹ️",
                            }.get(finding.severity.name, "•")
                            location = ""
                            if finding.source_ref:
                                location = f"{finding.source_ref.file_path}:{finding.source_ref.start_line}"
                            click.echo(
                                f"   {severity_icon} [{finding.rule_id}] {finding.summary}"
                            )
                            if location:
                                click.echo(f"      📍 {location}")
                        click.echo()

                    # Baseline findings summary
                    if result.baseline_findings:
                        click.echo(
                            f"📋 Baseline Findings: {len(result.baseline_findings)} (not blocking)"
                        )
                        click.echo()

                    # Cross-file clusters
                    if result.cross_file_clusters:
                        clusters = result.cross_file_clusters
                        if clusters.cross_file_duplicates:
                            click.echo(
                                f"🔗 Cross-file Duplicates: {len(clusters.cross_file_duplicates)}"
                            )
                            for dup in clusters.cross_file_duplicates[:5]:
                                click.echo(
                                    f"   • {dup.duplicate_type}: {len(dup.file_locations)} locations "
                                    f"({dup.impact_estimate} impact)"
                                )
                            if len(clusters.cross_file_duplicates) > 5:
                                click.echo(
                                    f"   ... and {len(clusters.cross_file_duplicates) - 5} more"
                                )
                            click.echo()

                    # Cleanup map
                    if result.cleanup_map:
                        cmap = result.cleanup_map
                        click.echo(f"🧹 Cleanup Map ({cmap.total_baseline_issues} issues):")
                        click.echo(f"   Estimated effort: {cmap.estimated_total_effort}")
                        for item in cmap.items[:5]:
                            click.echo(
                                f"   • [{item.rule_id}] {item.count} issues "
                                f"(priority {item.priority}, {item.estimated_effort} effort)"
                            )
                        click.echo()

                    # Final status
                    if result.should_fail:
                        click.echo("❌ Quality gate FAILED - new blocking issues found")
                    else:
                        click.echo("✅ Quality gate PASSED")

            sys.exit(result.exit_code)

        except ImportError as e:
            click.echo(f"❌ UI module not available: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            if verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)

    @quality_gates.command("baseline")
    @click.argument("action", type=click.Choice(["show", "update", "reset"]))
    @click.option(
        "--project",
        "-p",
        type=click.Path(exists=True),
        default=".",
        help="Project directory path",
    )
    @common_options
    def manage_baseline(action, project, verbose, quiet, config):
        """Manage UI quality baseline.

        Actions:
            show   - Display current baseline statistics
            update - Update baseline with current findings
            reset  - Clear baseline and start fresh
        """
        try:
            from .ui.ci import BaselineManager, CIAuditRunner
            from .ui.config import load_ui_config

            project_path = Path(project).resolve()
            ui_config = load_ui_config(project_path)
            baseline_manager = BaselineManager(project_path, ui_config)

            if action == "show":
                baseline = baseline_manager.load()
                if not quiet:
                    click.echo(f"📋 Baseline for: {project_path}")
                    click.echo(f"   Total entries: {baseline.total_entries}")
                    click.echo(f"   Suppressed: {baseline.suppressed_count}")
                    click.echo(f"   Created: {baseline.created_at}")
                    click.echo(f"   Last updated: {baseline.last_updated}")
                    click.echo()
                    if baseline.rule_counts:
                        click.echo("   Rule counts:")
                        for rule_id, count in sorted(
                            baseline.rule_counts.items(),
                            key=lambda x: -x[1]
                        ):
                            click.echo(f"      {rule_id}: {count}")

            elif action == "update":
                if not quiet:
                    click.echo("🔄 Running audit to update baseline...")

                # Run audit
                from .ui.ci import CIAuditConfig

                audit_config = CIAuditConfig(update_baseline=True)
                runner = CIAuditRunner(
                    project_path=project_path,
                    audit_config=audit_config,
                )
                result = runner.run()

                if not quiet:
                    click.echo(f"✅ Baseline updated with {result.total_findings} findings")

            elif action == "reset":
                baseline_manager.reset()
                if not quiet:
                    click.echo("✅ Baseline reset")

        except ImportError as e:
            click.echo(f"❌ UI module not available: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            if verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)

    @quality_gates.group("metrics")
    def metrics():
        """Metrics tracking and reporting commands."""
        pass

    @metrics.command("show")
    @click.option(
        "--project",
        "-p",
        type=click.Path(exists=True),
        default=".",
        help="Project directory path",
    )
    @click.option(
        "--format",
        "output_format",
        type=click.Choice(["cli", "json", "markdown"]),
        default="cli",
        help="Output format",
    )
    @common_options
    def show_metrics(project, output_format, verbose, quiet, config):
        """Display current metrics and target status.

        Shows UI quality metrics including token drift reduction,
        deduplication progress, suppression rates, and performance.

        Examples:
            claude-indexer quality-gates metrics show
            claude-indexer quality-gates metrics show --format json
        """
        try:
            import json as json_module
            from .ui.config import load_ui_config
            from .ui.metrics import MetricsAggregator, MetricsCollector

            project_path = Path(project).resolve()
            ui_config = load_ui_config(project_path)
            collector = MetricsCollector(project_path, ui_config)
            report = collector.load()
            aggregator = MetricsAggregator(report)
            summary = aggregator.generate_summary()

            if output_format == "json":
                click.echo(json_module.dumps(summary, indent=2))

            elif output_format == "markdown":
                click.echo("# UI Quality Metrics Dashboard\n")
                click.echo("## Token Drift Reduction")
                colors = summary["token_drift"]["colors"]
                click.echo(f"- Unique hardcoded colors: {colors['baseline']} -> {colors['current']} ({colors['reduction_percent']}% reduction)")
                click.echo(f"- Target: {colors['target']}% reduction | {'ON TRACK' if colors['on_track'] else 'NEEDS WORK'}")
                click.echo("\n## Deduplication Progress")
                dedup = summary["deduplication"]
                click.echo(f"- Current clusters: {dedup['current_clusters']}")
                click.echo(f"- Resolved this month: {dedup['resolved_this_month']} | Target: {dedup['target']}")
                click.echo("\n## Quality Indicators")
                click.echo(f"- Suppression rate: {summary['suppression_rate']['current']}%")
                click.echo(f"- Plan adoption: {summary['plan_adoption']['current']}%")
                click.echo("\n## Performance (p95)")
                for tier_name, tier_key in [("Tier 0", "tier_0"), ("Tier 1", "tier_1"), ("Tier 2", "tier_2")]:
                    perf = summary["performance"][tier_key]
                    p95 = perf.get("p95_ms", 0)
                    target = perf.get("target_p95_ms", 0)
                    on_track = perf.get("on_track", True)
                    click.echo(f"- {tier_name}: {p95:.0f}ms | Target: <{target}ms | {'ON TRACK' if on_track else 'NEEDS WORK'}")

            else:  # cli format
                click.echo("\nUI Quality Metrics Dashboard")
                click.echo("=" * 40)
                click.echo()

                # Token Drift
                click.echo("Token Drift Reduction")
                colors = summary["token_drift"]["colors"]
                status = "✅" if colors["on_track"] else "⚠️"
                click.echo(f"  Unique hardcoded colors:  {colors['baseline']} -> {colors['current']} ({colors['reduction_percent']}% reduction) {status}")
                click.echo(f"  [TARGET: {colors['target']}%]")
                click.echo()

                # Deduplication
                click.echo("Deduplication Progress")
                dedup = summary["deduplication"]
                status = "✅" if dedup["on_track"] else "⚠️"
                click.echo(f"  Duplicate clusters:       {dedup['current_clusters']} remaining")
                click.echo(f"  Resolved this month:      {dedup['resolved_this_month']} [TARGET: {dedup['target']}] {status}")
                click.echo()

                # Quality Indicators
                click.echo("Quality Indicators")
                supp = summary["suppression_rate"]
                status = "✅" if supp["on_track"] else "⚠️"
                click.echo(f"  Suppression rate:         {supp['current']}% [TARGET: <{supp['target_max']}%] {status}")
                adopt = summary["plan_adoption"]
                status = "✅" if adopt["on_track"] else "⚠️"
                click.echo(f"  /redesign plan adoption:  {adopt['current']}% [TARGET: >{adopt['target_min']}%] {status}")
                click.echo()

                # Performance
                click.echo("Performance (p95)")
                tier_names = [
                    ("Tier 0 (pre-commit)", "tier_0"),
                    ("Tier 1 (CI audit)", "tier_1"),
                    ("Tier 2 (/redesign)", "tier_2"),
                ]
                for name, key in tier_names:
                    perf = summary["performance"][key]
                    p95 = perf.get("p95_ms", 0)
                    target = perf.get("target_p95_ms", 0)
                    on_track = perf.get("on_track", True)
                    status = "✅" if on_track else "⚠️"
                    if p95 >= 60000:
                        p95_str = f"{p95 / 60000:.1f}min"
                    else:
                        p95_str = f"{p95:.0f}ms"
                    if target >= 60000:
                        target_str = f"<{target / 60000:.0f}min"
                    else:
                        target_str = f"<{target}ms"
                    click.echo(f"  {name:20}  {p95_str:>8} [TARGET: {target_str}] {status}")
                click.echo()

                # Overall status
                all_on_track = all([
                    colors["on_track"],
                    dedup["on_track"],
                    supp["on_track"],
                    adopt["on_track"],
                ] + [summary["performance"][t]["on_track"] for t in ["tier_0", "tier_1", "tier_2"]])

                if all_on_track:
                    click.echo("✅ All targets ON TRACK")
                else:
                    click.echo("⚠️  Some targets need attention")

        except ImportError as e:
            click.echo(f"❌ UI metrics module not available: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            if verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)

    @metrics.command("history")
    @click.option(
        "--project",
        "-p",
        type=click.Path(exists=True),
        default=".",
        help="Project directory path",
    )
    @click.option(
        "--days",
        "-d",
        type=int,
        default=30,
        help="Number of days to show",
    )
    @click.option(
        "--metric",
        "-m",
        type=click.Choice([
            "colors", "spacings", "clusters", "suppression",
            "tier0_time", "tier1_time", "tier2_time", "findings"
        ]),
        default="colors",
        help="Metric to show trend for",
    )
    @click.option(
        "--format",
        "output_format",
        type=click.Choice(["cli", "json", "csv"]),
        default="cli",
        help="Output format",
    )
    @common_options
    def history_metrics(project, days, metric, output_format, verbose, quiet, config):
        """Show metrics history and trends.

        Examples:
            claude-indexer quality-gates metrics history --days 90
            claude-indexer quality-gates metrics history --metric colors --format csv
        """
        try:
            import json as json_module
            from .ui.config import load_ui_config
            from .ui.metrics import MetricsAggregator, MetricsCollector

            project_path = Path(project).resolve()
            ui_config = load_ui_config(project_path)
            collector = MetricsCollector(project_path, ui_config)
            report = collector.load()
            aggregator = MetricsAggregator(report)

            trend_data = aggregator.get_trend_data(metric, days)

            if output_format == "json":
                click.echo(json_module.dumps(trend_data, indent=2))

            elif output_format == "csv":
                click.echo("timestamp,value")
                for point in trend_data:
                    click.echo(f"{point['timestamp']},{point['value']}")

            else:  # cli format
                if not trend_data:
                    click.echo(f"No data for metric '{metric}' in the last {days} days")
                    return

                click.echo(f"\nTrend for '{metric}' (last {days} days)")
                click.echo("-" * 40)
                for point in trend_data[-20:]:  # Show last 20 points
                    ts = point["timestamp"][:10]  # Date only
                    value = point["value"]
                    click.echo(f"  {ts}  {value}")

                if len(trend_data) > 20:
                    click.echo(f"  ... ({len(trend_data) - 20} more entries)")

        except ImportError as e:
            click.echo(f"❌ UI metrics module not available: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            if verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)

    @metrics.command("export")
    @click.option(
        "--project",
        "-p",
        type=click.Path(exists=True),
        default=".",
        help="Project directory path",
    )
    @click.option(
        "--output",
        "-o",
        type=click.Path(),
        required=True,
        help="Output file path",
    )
    @click.option(
        "--format",
        "output_format",
        type=click.Choice(["json", "csv", "prometheus"]),
        default="json",
        help="Export format",
    )
    @click.option(
        "--days",
        "-d",
        type=int,
        default=30,
        help="Number of days to export (for CSV)",
    )
    @common_options
    def export_metrics(project, output, output_format, days, verbose, quiet, config):
        """Export metrics for CI dashboards.

        Examples:
            claude-indexer quality-gates metrics export -o metrics.json
            claude-indexer quality-gates metrics export -o metrics.txt --format prometheus
        """
        try:
            import json as json_module
            from .ui.config import load_ui_config
            from .ui.metrics import MetricsAggregator, MetricsCollector

            project_path = Path(project).resolve()
            ui_config = load_ui_config(project_path)
            collector = MetricsCollector(project_path, ui_config)
            report = collector.load()
            aggregator = MetricsAggregator(report)

            output_path = Path(output)

            if output_format == "json":
                summary = aggregator.generate_summary()
                summary["report"] = report.to_dict()
                output_path.write_text(json_module.dumps(summary, indent=2))

            elif output_format == "csv":
                header = aggregator.export_csv_header()
                rows = aggregator.export_csv_rows(days)
                content = header + "\n" + "\n".join(rows)
                output_path.write_text(content)

            elif output_format == "prometheus":
                content = aggregator.export_prometheus()
                output_path.write_text(content)

            if not quiet:
                click.echo(f"✅ Exported metrics to {output_path}")

        except ImportError as e:
            click.echo(f"❌ UI metrics module not available: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            if verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)

    @metrics.command("reset")
    @click.option(
        "--project",
        "-p",
        type=click.Path(exists=True),
        default=".",
        help="Project directory path",
    )
    @click.option(
        "--confirm",
        is_flag=True,
        help="Confirm reset without prompting",
    )
    @common_options
    def reset_metrics(project, confirm, verbose, quiet, config):
        """Reset metrics history (start fresh baseline).

        This clears all historical metrics data. Use with caution.

        Examples:
            claude-indexer quality-gates metrics reset --confirm
        """
        try:
            from .ui.config import load_ui_config
            from .ui.metrics import MetricsCollector

            project_path = Path(project).resolve()
            ui_config = load_ui_config(project_path)
            collector = MetricsCollector(project_path, ui_config)

            if not confirm:
                if not click.confirm("Are you sure you want to reset all metrics history?"):
                    click.echo("Aborted")
                    return

            collector.reset()
            if not quiet:
                click.echo("✅ Metrics history reset")

        except ImportError as e:
            click.echo(f"❌ UI metrics module not available: {e}", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            if verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)

    # End of Click-available conditional block

if __name__ == "__main__":
    cli()
