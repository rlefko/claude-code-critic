# Installation Guide

> Platform-specific setup instructions for Claude Code Memory

This guide provides detailed installation instructions for all supported platforms.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Install (Recommended)](#quick-install-recommended)
3. [Manual Installation](#manual-installation)
4. [Platform-Specific Notes](#platform-specific-notes)
5. [Verification](#verification)
6. [Post-Installation](#post-installation)

---

## Prerequisites

### Required Software

| Software | Minimum Version | Recommended | Purpose |
|----------|-----------------|-------------|---------|
| Python | 3.9+ | 3.12 | Core indexer engine |
| Node.js | 18+ | 20 | MCP server |
| Docker | 20+ | Latest | Qdrant database |
| Claude Code | Latest | Latest | AI assistant integration |
| Git | 2.0+ | Latest | Version control hooks |

### API Keys

You need at least one embedding provider:

| Provider | Required | Purpose | Get Key |
|----------|----------|---------|---------|
| Voyage AI | Recommended | Embeddings (cost-effective) | [voyageai.com](https://voyageai.com) |
| OpenAI | Alternative | Embeddings + Chat analysis | [platform.openai.com](https://platform.openai.com) |

### System Requirements

- **Memory**: 4GB RAM minimum (8GB recommended for large projects)
- **Disk**: 2GB for software + space for vector storage
- **Network**: Internet access for embedding API calls

---

## Quick Install (Recommended)

The fastest way to get started:

```bash
# 1. Clone the repository
git clone https://github.com/Durafen/Claude-code-memory.git
cd Claude-code-memory

# 2. Run automated setup
./setup.sh -p /path/to/your/project -c your-project-name

# 3. Done! Claude now has memory of your codebase.
```

The setup script will:
- Install Python dependencies
- Build the MCP server
- Start Qdrant (Docker required)
- Create configuration files
- Index your project
- Configure Claude Code integration

### Setup Script Options

```bash
./setup.sh [OPTIONS]

Options:
  -p PATH        Project path to index (required)
  -c NAME        Collection name (required)
  -t TYPE        Project type: python|javascript|typescript|react|generic
  --no-index     Skip initial indexing
  --no-hooks     Skip hook installation
  --force        Overwrite existing configuration
  -h, --help     Show help message
```

---

## Manual Installation

For more control over the installation process.

### Step 1: Clone and Setup Python Environment

```bash
# Clone repository
git clone https://github.com/Durafen/Claude-code-memory.git
cd Claude-code-memory

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Install the CLI

```bash
# Make executable and install globally
./install.sh

# Verify installation
claude-indexer --version
```

### Step 3: Configure API Keys

Create `settings.txt` in the project root:

```bash
# Embedding Provider (choose one)
VOYAGE_API_KEY=pa-xxxxxxxxxxxxxxxx
# OR
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx

# Qdrant Configuration
QDRANT_URL=http://localhost:6333
# QDRANT_API_KEY=your-key  # Only if using Qdrant Cloud

# Optional: OpenAI for chat analysis
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
```

### Step 4: Install and Build MCP Server

```bash
cd mcp-qdrant-memory

# Install Node dependencies
npm install

# Build TypeScript
npm run build

# Verify build
ls -la dist/index.js
```

### Step 5: Start Qdrant Database

```bash
# Using Docker (recommended)
docker run -d \
  -p 6333:6333 \
  -v $(pwd)/qdrant_storage:/qdrant/storage \
  --name qdrant \
  qdrant/qdrant

# Verify Qdrant is running
curl http://localhost:6333/health
# Should return: {"status":"ok"}
```

### Step 6: Index Your Project

```bash
# Navigate back to Claude-code-memory root
cd ..

# Initialize and index your project
claude-indexer init -p /path/to/your/project -c your-project-name
```

### Step 7: Configure Claude Code Integration

Add MCP server to Claude Code settings (`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "your-project-memory": {
      "command": "node",
      "args": ["/absolute/path/to/Claude-code-memory/mcp-qdrant-memory/dist/index.js"],
      "env": {
        "COLLECTION_NAME": "your-project-name",
        "QDRANT_URL": "http://localhost:6333",
        "VOYAGE_API_KEY": "pa-xxxxxxxx"
      }
    }
  }
}
```

---

## Platform-Specific Notes

### macOS

**Prerequisites**:

```bash
# Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.12
brew install python@3.12

# Install Node.js
brew install node@18

# Install Docker Desktop
brew install --cask docker
# Then launch Docker Desktop from Applications
```

**Apple Silicon (M1/M2/M3)**:

Docker works natively. No special configuration needed.

```bash
# Verify architecture
uname -m  # Should show arm64

# Qdrant uses native ARM images automatically
docker run -d -p 6333:6333 qdrant/qdrant
```

### Linux (Ubuntu/Debian)

**Prerequisites**:

```bash
# Update package list
sudo apt update

# Install Python 3.12
sudo apt install python3.12 python3.12-venv python3-pip

# Install Node.js 18
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install nodejs

# Install Docker
sudo apt install docker.io
sudo systemctl start docker
sudo systemctl enable docker

# Add user to docker group (logout required)
sudo usermod -aG docker $USER
```

**Firewall Configuration**:

```bash
# Allow Qdrant port
sudo ufw allow 6333
```

### Linux (RHEL/CentOS/Fedora)

```bash
# Install Python 3.12
sudo dnf install python3.12 python3.12-pip

# Install Node.js 18
sudo dnf module install nodejs:18

# Install Docker
sudo dnf install docker
sudo systemctl start docker
sudo systemctl enable docker
```

### Windows (via WSL2)

Claude Code Memory is best run on Windows using WSL2:

1. **Install WSL2**:
   ```powershell
   # Run in PowerShell as Administrator
   wsl --install -d Ubuntu
   ```

2. **Install Docker Desktop**:
   - Download from [docker.com](https://www.docker.com/products/docker-desktop)
   - Enable WSL2 integration in Docker Desktop settings

3. **Setup in WSL2**:
   ```bash
   # Inside Ubuntu WSL2
   sudo apt update
   sudo apt install python3.12 python3.12-venv nodejs npm

   # Clone and setup
   git clone https://github.com/Durafen/Claude-code-memory.git
   cd Claude-code-memory
   ./setup.sh -p /path/to/project -c project-name
   ```

4. **Path Considerations**:
   - Use WSL paths: `/mnt/c/Users/...` for Windows files
   - Store projects in WSL filesystem for better performance

---

## Verification

After installation, verify everything is working:

### Run the Doctor Command

```bash
claude-indexer doctor -p /path/to/your/project -c your-collection

# Expected output:
# ✅ Python 3.12.x
# ✅ Node.js 18.x
# ✅ Qdrant (localhost:6333)
# ✅ Collection: your-collection (1234 entities)
# ✅ Voyage AI API key configured
# ✅ Claude Code CLI available
```

### Test Search

```bash
# Search for something in your codebase
claude-indexer search "main function" -p /path/to/project -c your-collection

# Should return relevant code snippets
```

### Test MCP Connection

In a Claude Code session:

```
You: What functions are available in this codebase?
Claude: [Uses memory tools to search and respond with codebase information]
```

---

## Post-Installation

### Create CLAUDE.md for Your Project

Copy the template to your project:

```bash
cp /path/to/Claude-code-memory/templates/CLAUDE.md.template /path/to/your/project/CLAUDE.md
```

Edit it to include your MCP collection name:

```markdown
# Project Instructions

## Memory Integration
Use `mcp__your-project-memory__` prefix for all memory operations.
```

### Install Git Hooks

For automatic indexing on commits:

```bash
claude-indexer hooks install -p /path/to/your/project
```

This installs:
- **post-commit**: Index changed files after commits
- **post-checkout**: Re-index on branch switches
- **post-merge**: Index new files after merges

### Configure Memory Guard

For code quality enforcement, ensure hooks are in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/hooks/prompt_handler.sh"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Write|Edit|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/hooks/pre-tool-guard.sh"
          }
        ]
      }
    ]
  }
}
```

### Set Up Multiple Projects

For additional projects:

```bash
# Index another project with a unique collection
claude-indexer init -p /path/to/other/project -c other-project-name

# Add another MCP server entry to settings.json
# Each project needs its own mcpServers entry
```

---

## Updating

### Update Claude Code Memory

```bash
cd /path/to/Claude-code-memory
git pull origin master

# Rebuild Python environment
source .venv/bin/activate
pip install -r requirements.txt

# Rebuild MCP server
cd mcp-qdrant-memory
npm install
npm run build
```

### Re-index After Updates

```bash
# Full re-index (recommended after major updates)
claude-indexer index -p /path/to/project -c collection-name --force
```

---

## Uninstallation

### Remove Configuration

```bash
# Remove Claude Code memory integration
rm -rf ~/.claude-code-memory
rm -rf ~/.claude-indexer

# Remove MCP server entries from ~/.claude/settings.json
# (edit manually)
```

### Remove Qdrant Data

```bash
# Stop and remove Qdrant container
docker stop qdrant
docker rm qdrant

# Remove stored data
rm -rf /path/to/Claude-code-memory/qdrant_storage
```

### Remove Installation

```bash
# Remove repository
rm -rf /path/to/Claude-code-memory

# Remove symlink
sudo rm /usr/local/bin/claude-indexer
```

---

## Related Documentation

- [Troubleshooting](TROUBLESHOOTING.md) - Common issues
- [CLI Reference](CLI_REFERENCE.md) - All commands
- [Configuration](CONFIGURATION.md) - Settings reference
- [Memory Functions](memory-functions.md) - MCP tools
