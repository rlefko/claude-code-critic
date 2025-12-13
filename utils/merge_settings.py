#!/usr/bin/env python3
"""
DEPRECATED: This utility is no longer used in automated setup.

As of the .mcp.json migration, setup.sh creates .mcp.json directly in the
project root instead of merging into .claude/settings.local.json.

This file is preserved for backward compatibility and manual use cases,
but is not invoked by setup.sh.

Previous Purpose:
Merge MCP server configuration into settings.local.json.
Handles merging new MCP server config with existing settings without
overwriting other MCP servers or configurations.
"""

import json
import sys
from pathlib import Path


def merge_mcp_config(settings_file: Path, new_config: dict) -> None:
    """
    Merge new MCP configuration into existing settings.local.json.

    Args:
        settings_file: Path to settings.local.json
        new_config: New configuration to merge
    """
    existing_config = {}

    # Load existing configuration if file exists
    if settings_file.exists():
        try:
            with open(settings_file) as f:
                existing_config = json.load(f)
        except json.JSONDecodeError:
            print(
                f"Warning: Existing {settings_file} is not valid JSON, overwriting",
                file=sys.stderr,
            )
            existing_config = {}

    # Merge mcpServers
    if "mcpServers" not in existing_config:
        existing_config["mcpServers"] = {}

    if "mcpServers" in new_config:
        existing_config["mcpServers"].update(new_config["mcpServers"])

    # Merge hooks
    if "hooks" not in existing_config:
        existing_config["hooks"] = {}

    if "hooks" in new_config:
        for hook_type, hook_configs in new_config["hooks"].items():
            if hook_type not in existing_config["hooks"]:
                existing_config["hooks"][hook_type] = []

            # Add new hook configs if they don't already exist
            for new_hook_config in hook_configs:
                # Check if this hook already exists (by matcher + command)
                exists = False
                for existing_hook in existing_config["hooks"][hook_type]:
                    if existing_hook.get("matcher") == new_hook_config.get(
                        "matcher"
                    ) and existing_hook.get("hooks", [{}])[0].get(
                        "command"
                    ) == new_hook_config.get(
                        "hooks", [{}]
                    )[
                        0
                    ].get(
                        "command"
                    ):
                        exists = True
                        break

                if not exists:
                    existing_config["hooks"][hook_type].append(new_hook_config)

    # Write merged configuration
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    with open(settings_file, "w") as f:
        json.dump(existing_config, f, indent=2)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: merge_settings.py <settings_file> <new_config_json>",
            file=sys.stderr,
        )
        sys.exit(1)

    settings_file = Path(sys.argv[1])
    new_config_json = sys.argv[2]

    try:
        new_config = json.loads(new_config_json)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in new_config: {e}", file=sys.stderr)
        sys.exit(1)

    merge_mcp_config(settings_file, new_config)
    print(f"✓ Merged configuration into {settings_file}")
