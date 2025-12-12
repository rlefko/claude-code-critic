# Troubleshooting Guide

> Common issues and solutions for Claude Code Memory

This guide covers the most common issues you may encounter when using Claude Code Memory and provides step-by-step solutions.

---

## Table of Contents

1. [Installation Issues](#installation-issues)
2. [Qdrant Connection Issues](#qdrant-connection-issues)
3. [Indexing Problems](#indexing-problems)
4. [MCP Server Issues](#mcp-server-issues)
5. [Memory Guard Issues](#memory-guard-issues)
6. [Hook System Issues](#hook-system-issues)
7. [Performance Issues](#performance-issues)
8. [API Key Issues](#api-key-issues)
9. [Getting Help](#getting-help)

---

## Installation Issues

### "claude-indexer: command not found"

**Cause**: The CLI is not in your PATH or installation incomplete.

**Solutions**:

1. **Re-run the installer**:
   ```bash
   ./install.sh
   ```

2. **Manually add to PATH**:
   ```bash
   # Add to ~/.bashrc or ~/.zshrc
   export PATH="$PATH:$HOME/Claude-code-memory"
   source ~/.bashrc  # or ~/.zshrc
   ```

3. **Create symlink manually**:
   ```bash
   sudo ln -s /path/to/Claude-code-memory/claude-indexer /usr/local/bin/claude-indexer
   ```

4. **Verify installation**:
   ```bash
   which claude-indexer
   claude-indexer --version
   ```

### Python Version Errors

**Cause**: Claude Code Memory requires Python 3.9 or higher (3.12 recommended).

**Solutions**:

1. **Check your Python version**:
   ```bash
   python3 --version
   ```

2. **Install Python 3.12 with pyenv**:
   ```bash
   # Install pyenv
   curl https://pyenv.run | bash

   # Install Python 3.12
   pyenv install 3.12
   pyenv global 3.12
   ```

3. **On macOS with Homebrew**:
   ```bash
   brew install python@3.12
   ```

4. **On Ubuntu/Debian**:
   ```bash
   sudo apt update
   sudo apt install python3.12 python3.12-venv
   ```

### Node.js Version Errors

**Cause**: The MCP server requires Node.js 18 or higher.

**Solutions**:

1. **Check your Node version**:
   ```bash
   node --version
   ```

2. **Install Node.js with nvm**:
   ```bash
   # Install nvm
   curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash

   # Install Node 18+
   nvm install 18
   nvm use 18
   ```

3. **On macOS**:
   ```bash
   brew install node@18
   ```

---

## Qdrant Connection Issues

### "Connection refused" or "Cannot connect to Qdrant"

**Cause**: Qdrant is not running or not accessible on the expected port.

**Solutions**:

1. **Check if Qdrant is running**:
   ```bash
   curl http://localhost:6333/health
   # Should return: {"status":"ok"}
   ```

2. **Start Qdrant with Docker**:
   ```bash
   docker run -d -p 6333:6333 -v $(pwd)/qdrant_storage:/qdrant/storage qdrant/qdrant
   ```

3. **Check Docker container status**:
   ```bash
   docker ps | grep qdrant
   docker logs <container_id>
   ```

4. **Verify port availability**:
   ```bash
   lsof -i :6333
   ```

5. **Check firewall settings** (Linux):
   ```bash
   sudo ufw allow 6333
   ```

### "Authentication failed" or "Invalid API key"

**Cause**: API key mismatch between settings and Qdrant configuration.

**Solutions**:

1. **Check settings.txt**:
   ```bash
   cat settings.txt | grep QDRANT
   ```

2. **Verify API key matches Qdrant config**:
   ```bash
   # If using Qdrant Cloud, ensure the key matches your dashboard
   # If local without auth, remove QDRANT_API_KEY from settings.txt
   ```

3. **Test connection with API key**:
   ```bash
   curl -H "api-key: YOUR_KEY" http://localhost:6333/health
   ```

### "Collection not found"

**Cause**: The specified collection doesn't exist in Qdrant.

**Solutions**:

1. **List existing collections**:
   ```bash
   claude-indexer collections list
   ```

2. **Re-run init to create collection**:
   ```bash
   claude-indexer init -p /path/to/project -c your-collection-name
   ```

3. **Check collection name in MCP config**:
   ```bash
   cat ~/.claude/settings.json | grep collection
   ```

---

## Indexing Problems

### "No entities created" or "0 files indexed"

**Cause**: Files may be excluded, wrong directory, or unsupported file types.

**Solutions**:

1. **Check supported file types**:
   - Python: `.py`
   - JavaScript: `.js`, `.jsx`
   - TypeScript: `.ts`, `.tsx`
   - JSON: `.json`
   - YAML: `.yaml`, `.yml`
   - HTML: `.html`
   - CSS: `.css`
   - Markdown: `.md`

2. **Check .claudeignore patterns**:
   ```bash
   cat .claudeignore
   # Ensure your files aren't excluded
   ```

3. **Run with verbose mode**:
   ```bash
   claude-indexer index -p . -c collection-name --verbose
   ```

4. **Check file permissions**:
   ```bash
   ls -la /path/to/files
   ```

### Slow Indexing

**Cause**: Large repository, network latency to embedding API, or insufficient resources.

**Solutions**:

1. **Use batch indexing**:
   ```bash
   # Index specific files for faster updates
   echo "src/file1.py
   src/file2.py" | claude-indexer index -p . -c collection --files-from-stdin
   ```

2. **Reduce batch size** (in settings.txt):
   ```
   BATCH_SIZE=25  # Default is 50
   ```

3. **Check embedding API latency**:
   ```bash
   time curl -s https://api.voyageai.com/v1/embeddings -H "Authorization: Bearer $VOYAGE_API_KEY" -d '{"input":"test","model":"voyage-3-lite"}' > /dev/null
   ```

4. **Use incremental indexing**:
   ```bash
   # Only index changed files since last commit
   claude-indexer index -p . -c collection --since HEAD~1
   ```

### Memory Issues During Indexing

**Cause**: Large files or too many files processed at once.

**Solutions**:

1. **Reduce parallel workers**:
   ```bash
   claude-indexer index -p . -c collection --workers 2
   ```

2. **Exclude large files** (add to .claudeignore):
   ```gitignore
   # Large data files
   *.csv
   *.json  # if data files
   data/
   ```

3. **Monitor memory usage**:
   ```bash
   # Watch memory while indexing
   watch -n 1 'ps aux | grep claude-indexer'
   ```

---

## MCP Server Issues

### "MCP server not loading" in Claude Code

**Cause**: Configuration issues, path problems, or server not built.

**Solutions**:

1. **Rebuild the MCP server**:
   ```bash
   cd mcp-qdrant-memory
   npm install
   npm run build
   ```

2. **Verify MCP configuration** in `~/.claude/settings.json`:
   ```json
   {
     "mcpServers": {
       "your-project-memory": {
         "command": "node",
         "args": ["/absolute/path/to/mcp-qdrant-memory/dist/index.js"],
         "env": {
           "COLLECTION_NAME": "your-collection",
           "QDRANT_URL": "http://localhost:6333"
         }
       }
     }
   }
   ```

3. **Check paths are absolute** (not relative):
   ```bash
   # Good: /Users/you/Claude-code-memory/mcp-qdrant-memory/dist/index.js
   # Bad: ./mcp-qdrant-memory/dist/index.js
   ```

4. **Restart Claude Code** after config changes.

5. **Check MCP logs**:
   ```bash
   tail -f ~/Library/Caches/claude-cli-nodejs/*/mcp-logs-*/$(ls -t ~/Library/Caches/claude-cli-nodejs/*/mcp-logs-*/ | head -1)
   ```

### "Collection not found" in MCP

**Cause**: Collection name mismatch between MCP config and Qdrant.

**Solutions**:

1. **Verify collection exists**:
   ```bash
   claude-indexer collections list
   ```

2. **Check MCP env vars**:
   ```bash
   cat ~/.claude/settings.json | grep -A5 "your-project-memory"
   ```

3. **Ensure consistent naming**: Collection name must match exactly (case-sensitive).

### Search Returns No Results

**Cause**: Empty collection, embedding provider mismatch, or query issues.

**Solutions**:

1. **Verify collection has data**:
   ```bash
   claude-indexer collections show your-collection
   ```

2. **Test search directly**:
   ```bash
   claude-indexer search "your query" -p . -c your-collection
   ```

3. **Check embedding provider consistency**:
   - Index and search must use the same embedding provider
   - Check settings.txt for `EMBEDDING_PROVIDER`

---

## Memory Guard Issues

### Memory Guard Not Triggering

**Cause**: Hooks not configured or not enabled.

**Solutions**:

1. **Verify hooks in settings.json**:
   ```bash
   cat ~/.claude/settings.json | grep -A10 "hooks"
   ```

2. **Check both required hooks are present**:
   ```json
   {
     "hooks": {
       "UserPromptSubmit": [...],
       "PreToolUse": [...]
     }
   }
   ```

3. **Ensure hook scripts are executable**:
   ```bash
   chmod +x ~/.claude/hooks/*.sh
   chmod +x /path/to/project/.claude/hooks/*.sh
   ```

4. **Check debug log**:
   ```bash
   cat memory_guard_debug.txt
   ```

### Too Many False Positives

**Cause**: Rules too strict for your codebase.

**Solutions**:

1. **Use inline override comments**:
   ```python
   # @allow-duplicate: Legacy API compatibility required
   def legacy_function():
       pass
   ```

2. **Disable specific checks** (in `.guard.conf`):
   ```bash
   DISABLE_CHECKS="todo_without_ticket debug_statement"
   ```

3. **Adjust severity threshold**:
   ```bash
   # In .guard.conf
   MIN_SEVERITY=2  # Only HIGH and CRITICAL
   ```

4. **Temporarily disable Memory Guard**:
   ```
   You: dups off
   Claude: Memory Guard disabled for this session
   ```

### Debug Logging

**Location**: Memory Guard logs are in your project root.

```bash
# View debug log
cat memory_guard_debug.txt

# View guard event log
cat ~/.claude-code-memory/guard.log

# Enable verbose logging (in .guard.conf)
ENABLE_LOGGING=true
```

---

## Hook System Issues

### Hooks Not Executing

**Cause**: Permission issues, wrong paths, or shell compatibility.

**Solutions**:

1. **Check permissions**:
   ```bash
   ls -la ~/.claude/hooks/
   chmod +x ~/.claude/hooks/*.sh
   ```

2. **Verify absolute paths** in settings.json:
   ```json
   "command": "/absolute/path/to/hook.sh"
   ```

3. **Test hook manually**:
   ```bash
   /path/to/your/hook.sh
   echo $?  # Check exit code
   ```

4. **Check shell compatibility**:
   ```bash
   # Ensure shebang is correct
   head -1 /path/to/hook.sh
   # Should be: #!/bin/bash or #!/usr/bin/env bash
   ```

### Session Control Not Working

**Cause**: UserPromptSubmit hook not properly configured.

**Solutions**:

1. **Verify hook is registered**:
   ```bash
   cat ~/.claude/settings.json | grep -A5 "UserPromptSubmit"
   ```

2. **Check prompt_handler.py exists**:
   ```bash
   ls -la /path/to/hooks/prompt_handler.py
   ```

3. **Test manually**:
   ```bash
   echo "dups status" | python3 /path/to/hooks/prompt_handler.py
   ```

---

## Performance Issues

### Slow Search

**Cause**: Large collection, no caching, or inefficient search mode.

**Solutions**:

1. **Use metadata-first search**:
   ```python
   # Fast: search metadata only
   search_similar("query", entityTypes=["metadata"])

   # Slower: full implementation search
   search_similar("query", entityTypes=["implementation"])
   ```

2. **Enable query cache** (check if enabled):
   ```bash
   claude-indexer perf cache-stats
   ```

3. **Use semantic mode for concept queries**:
   ```python
   search_similar("concept query", searchMode="semantic")
   ```

4. **Use keyword mode for exact terms**:
   ```python
   search_similar("exact_function_name", searchMode="keyword")
   ```

### High Memory Usage

**Cause**: Large collections, caching, or memory leaks.

**Solutions**:

1. **Reduce batch size**:
   ```bash
   # In settings.txt
   BATCH_SIZE=25
   ```

2. **Clear cache**:
   ```bash
   claude-indexer perf clear
   ```

3. **Check collection size**:
   ```bash
   claude-indexer collections show your-collection
   ```

4. **Consider splitting large projects** into multiple collections.

---

## API Key Issues

### "Invalid API key" Errors

**Cause**: Wrong key format, expired key, or wrong provider.

**Solutions**:

1. **Check settings.txt format**:
   ```bash
   # Correct format (no quotes around values)
   VOYAGE_API_KEY=pa-xxxxx
   OPENAI_API_KEY=sk-xxxxx
   ```

2. **Verify key is valid**:
   ```bash
   # Test Voyage AI
   curl https://api.voyageai.com/v1/embeddings \
     -H "Authorization: Bearer $VOYAGE_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"input":"test","model":"voyage-3-lite"}'

   # Test OpenAI
   curl https://api.openai.com/v1/embeddings \
     -H "Authorization: Bearer $OPENAI_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"input":"test","model":"text-embedding-3-small"}'
   ```

3. **Check environment variables aren't overriding**:
   ```bash
   env | grep -E "(VOYAGE|OPENAI)"
   ```

### Rate Limiting

**Cause**: Too many API calls too quickly.

**Solutions**:

1. **Reduce batch size**:
   ```bash
   # In settings.txt
   BATCH_SIZE=10
   ```

2. **Use incremental indexing** instead of full:
   ```bash
   claude-indexer index -p . -c collection --since HEAD~5
   ```

3. **Check your API plan limits** on the provider's dashboard.

4. **Add delays between batches** (for very large indexes):
   ```bash
   # In settings.txt
   BATCH_DELAY_MS=1000
   ```

---

## Getting Help

### Debug Mode

Run commands with verbose output:

```bash
claude-indexer index -p . -c collection --verbose
claude-indexer search "query" -p . -c collection --verbose
claude-indexer doctor --verbose
```

### Log Locations

| Log | Location |
|-----|----------|
| Indexer logs | `logs/<collection>.log` |
| Guard logs | `~/.claude-code-memory/guard.log` |
| Debug log | `memory_guard_debug.txt` (project root) |
| MCP logs | `~/Library/Caches/claude-cli-nodejs/*/mcp-logs-*/` |
| Service logs | `~/.claude-indexer/logs/service.log` |

### System Health Check

Run the doctor command to diagnose issues:

```bash
claude-indexer doctor -p . -c your-collection --verbose
```

### GitHub Issues

For bugs or feature requests:
- [Open an issue](https://github.com/Durafen/Claude-code-memory/issues)
- Include: error messages, logs, system info, steps to reproduce

### Community

- Check existing issues for solutions
- Include `claude-indexer doctor` output in bug reports
- Provide minimal reproduction steps

---

## Quick Reference

| Issue | First Step |
|-------|------------|
| Command not found | `./install.sh` |
| Qdrant connection | `docker ps` |
| No results | `claude-indexer collections show NAME` |
| MCP not loading | Check absolute paths in settings.json |
| Memory Guard silent | Check hooks in settings.json |
| Slow performance | Use `--verbose` flag |

---

## Related Documentation

- [Installation Guide](installation.md) - Setup instructions
- [CLI Reference](CLI_REFERENCE.md) - All commands
- [Memory Guard](MEMORY_GUARD.md) - Quality checks
- [Hooks System](HOOKS.md) - Hook configuration
- [Configuration](CONFIGURATION.md) - All settings
