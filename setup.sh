#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/.venv"
SETTINGS_FILE="$SCRIPT_DIR/settings.txt"
TEMPLATE_FILE="$SCRIPT_DIR/templates/CLAUDE.md.template"
MCP_DIR="$SCRIPT_DIR/mcp-qdrant-memory"

# Helper functions
print_header() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Usage information
usage() {
    cat << EOF
Usage: $0 -p PROJECT_PATH [-c COLLECTION_NAME] [-r] [-h]

Automated setup script for semantic code memory system.

Required:
  -p PROJECT_PATH       Path to the project to index

Optional:
  -c COLLECTION_NAME    Collection name (defaults to project folder name)
  -r, --recreate        Force recreate collection (useful for corrupted collections)
  -h                    Show this help message

Examples:
  $0 -p ~/my-project
  $0 -p ~/my-project -c my-collection
  $0 -p ~/my-project -c my-collection --recreate

This script will:
  1. Verify environment and dependencies
  2. Configure API keys (interactive prompts)
  3. Check/start Qdrant vector database
  4. Build MCP server
  5. Install git hooks (pre-commit, post-merge, post-checkout)
  6. Configure Memory Guard hooks
  7. Generate CLAUDE.md documentation
  8. Run initial indexing

Multi-Project Support:
  The MCP server supports multiple projects simultaneously via dynamic
  collection routing. Each project should use a unique collection name.
  All MCP tools accept an optional 'collection' parameter to override
  the default collection, enabling cross-project queries.

  Example: Multiple projects open at once
    mcp__project_a__search_similar("query")           # Uses project_a collection
    mcp__project_b__search_similar("query")           # Uses project_b collection
    mcp__project_a__search_similar("query", collection="project_b")  # Query project_b from project_a

EOF
    exit 0
}

# Parse arguments
PROJECT_PATH=""
COLLECTION_NAME=""
RECREATE_COLLECTION=false

while getopts "p:c:rh" opt; do
    case $opt in
        p) PROJECT_PATH="$OPTARG" ;;
        c) COLLECTION_NAME="$OPTARG" ;;
        r) RECREATE_COLLECTION=true ;;
        h) usage ;;
        *) usage ;;
    esac
done

# Validate required arguments
if [ -z "$PROJECT_PATH" ]; then
    print_error "Project path is required"
    usage
fi

# Resolve absolute paths
PROJECT_PATH="$(cd "$PROJECT_PATH" 2>/dev/null && pwd)" || {
    print_error "Project path does not exist: $PROJECT_PATH"
    exit 1
}

# Default collection name to project folder name
if [ -z "$COLLECTION_NAME" ]; then
    COLLECTION_NAME="$(basename "$PROJECT_PATH")"
    print_info "Using default collection name: $COLLECTION_NAME"
fi

# Validate collection name (alphanumeric, hyphens, underscores only)
if ! [[ "$COLLECTION_NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    print_error "Collection name must contain only letters, numbers, hyphens, and underscores"
    exit 1
fi

print_header "Semantic Code Memory Setup"
echo "Project Path: $PROJECT_PATH"
echo "Collection Name: $COLLECTION_NAME"

# ============================================================================
# Step 1: Environment Verification
# ============================================================================
print_header "Step 1: Verifying Environment"

# Check if we're in the correct directory
if [ ! -f "$SCRIPT_DIR/claude_indexer/__init__.py" ]; then
    print_error "Must run from memory project root directory"
    exit 1
fi
print_success "Running from correct directory"

# Check for Python 3.12 specifically
print_info "Checking for Python 3.12..."
PYTHON_CMD=""

# Try different Python 3.12 commands
for cmd in python3.12 python312 python3; do
    if command -v $cmd &> /dev/null; then
        VERSION=$($cmd --version 2>&1 | awk '{print $2}')
        MAJOR=$(echo "$VERSION" | cut -d. -f1)
        MINOR=$(echo "$VERSION" | cut -d. -f2)

        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 12 ]; then
            PYTHON_CMD=$cmd
            print_success "Found Python $VERSION at $cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    print_error "Python 3.12+ is required but not found"
    print_info ""
    print_info "Please install Python 3.12:"
    print_info "  macOS:  brew install python@3.12"
    print_info "  Ubuntu: apt install python3.12 python3.12-venv"
    print_info "  Other:  Use your system's package manager"
    exit 1
fi

# Check/create virtual environment with Python 3.12
if [ ! -d "$VENV_PATH" ]; then
    print_info "Creating virtual environment with Python 3.12..."
    # Use the specific Python 3.12 command to create venv
    $PYTHON_CMD -m venv "$VENV_PATH"
    if [ $? -ne 0 ]; then
        print_error "Failed to create virtual environment"
        print_info "Please ensure python3.12-venv is installed"
        print_info "  Ubuntu: sudo apt install python3.12-venv"
        print_info "  macOS:  Should work if python@3.12 is installed via brew"
        exit 1
    fi
    print_success "Virtual environment created with Python 3.12"
else
    print_success "Virtual environment exists"
fi

# Activate virtual environment
source "$VENV_PATH/bin/activate"
print_success "Virtual environment activated"

# Check Python version inside venv
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
    print_error "Python 3.10+ required in venv (found $PYTHON_VERSION)"
    print_info "The venv was created with system Python which is too old"
    print_info "Please install Python 3.10+ and re-run this script"
    exit 1
fi
print_success "Python version in venv: $PYTHON_VERSION"

# Install/upgrade dependencies
print_info "Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r "$SCRIPT_DIR/requirements.txt"
print_success "Dependencies installed"

# Check Docker for Qdrant database
print_info "Checking for Docker..."
if ! command -v docker &> /dev/null; then
    print_error "Docker is required but not installed"
    print_info ""
    print_info "Please install Docker:"
    print_info "  macOS:  brew install --cask docker"
    print_info "  Ubuntu: apt install docker.io"
    print_info "  Other:  https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker daemon is running
if ! docker info &> /dev/null; then
    print_error "Docker is installed but not running"
    print_info "Please start Docker Desktop (macOS) or Docker daemon (Linux)"
    exit 1
fi

DOCKER_VERSION=$(docker --version | awk '{print $3}' | tr -d ',')
print_success "Docker version: $DOCKER_VERSION (running)"

# Check Node.js for MCP server
if ! command -v node &> /dev/null; then
    print_error "Node.js is required but not installed"
    print_info "Install Node.js from https://nodejs.org/"
    exit 1
fi
NODE_VERSION=$(node --version)
print_success "Node.js version: $NODE_VERSION"

# Check npm
if ! command -v npm &> /dev/null; then
    print_error "npm is required but not installed"
    exit 1
fi
print_success "npm available"

# ============================================================================
# Step 2: API Key Configuration
# ============================================================================
print_header "Step 2: Configuring API Keys"

# Load existing settings if available (bash 3.2 compatible - no associative arrays)
OPENAI_API_KEY=""
VOYAGE_API_KEY=""
QDRANT_URL="http://localhost:6333"
QDRANT_API_KEY=""

if [ -f "$SETTINGS_FILE" ]; then
    print_info "Loading existing settings from settings.txt"
    # Source the file to load variables
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
        # Remove leading/trailing whitespace
        key=$(echo "$key" | xargs)
        value=$(echo "$value" | xargs)
        # Set variables dynamically
        case "$key" in
            OPENAI_API_KEY) OPENAI_API_KEY="$value" ;;
            VOYAGE_API_KEY) VOYAGE_API_KEY="$value" ;;
            QDRANT_URL) QDRANT_URL="$value" ;;
            QDRANT_API_KEY) QDRANT_API_KEY="$value" ;;
        esac
    done < "$SETTINGS_FILE"
fi

# Function to prompt for API key
prompt_for_key() {
    local var_name="$1"
    local key_description="$2"
    local is_optional="$3"
    local current_value="${!var_name}"

    # Check if key already exists and is valid
    if [ -n "$current_value" ] && [[ ! "$current_value" =~ ^your_.*_here$ ]]; then
        print_success "$key_description already configured"
        return
    fi

    # Prompt for key
    local optional_text=""
    [ "$is_optional" = "true" ] && optional_text=" (optional, press Enter to skip)"

    echo -e -n "${YELLOW}Enter $key_description$optional_text:${NC} "
    read -r key_value

    if [ -z "$key_value" ] && [ "$is_optional" != "true" ]; then
        print_error "$key_description is required"
        exit 1
    fi

    if [ -n "$key_value" ]; then
        eval "$var_name=\"$key_value\""
        print_success "$key_description configured"
    else
        print_info "$key_description skipped"
    fi
}

# Prompt for required keys
prompt_for_key "OPENAI_API_KEY" "OpenAI API Key" "false"
prompt_for_key "VOYAGE_API_KEY" "Voyage AI API Key" "false"

# Prompt for Qdrant configuration
echo -e -n "${YELLOW}Qdrant URL [$QDRANT_URL]:${NC} "
read -r qdrant_url
[ -n "$qdrant_url" ] && QDRANT_URL="$qdrant_url"

prompt_for_key "QDRANT_API_KEY" "Qdrant API Key" "true"

# Save settings to file
print_info "Saving settings to settings.txt..."
cat > "$SETTINGS_FILE" << EOF
# API Configuration
OPENAI_API_KEY=$OPENAI_API_KEY
VOYAGE_API_KEY=$VOYAGE_API_KEY
QDRANT_URL=$QDRANT_URL
QDRANT_API_KEY=${QDRANT_API_KEY:-}

# Embedding Configuration
EMBEDDING_PROVIDER=voyage
EMBEDDING_MODEL=voyage-3.5-lite
OUTPUT_DIMENSION=512
EOF
print_success "Settings saved"

# ============================================================================
# Step 3: Qdrant Database Setup
# ============================================================================
print_header "Step 3: Checking Qdrant Database"

# Check if Qdrant is accessible
QDRANT_URL="${QDRANT_URL}"
if curl -s -f "$QDRANT_URL/collections" > /dev/null 2>&1; then
    print_success "Qdrant is running at $QDRANT_URL"
else
    print_warning "Qdrant is not accessible at $QDRANT_URL"

    # If localhost, offer to start via Docker
    if [[ "$QDRANT_URL" == *"localhost"* ]] || [[ "$QDRANT_URL" == *"127.0.0.1"* ]]; then
        echo -e -n "${YELLOW}Start Qdrant via Docker? [y/N]:${NC} "
        read -r start_qdrant

        if [[ "$start_qdrant" =~ ^[Yy]$ ]]; then
            if ! command -v docker &> /dev/null; then
                print_error "Docker is not installed"
                print_info "Install Docker from https://www.docker.com/"
                exit 1
            fi

            print_info "Starting Qdrant container..."
            docker run -d -p 6333:6333 -p 6334:6334 \
                -v "$SCRIPT_DIR/qdrant_storage:/qdrant/storage" \
                --name qdrant-memory \
                qdrant/qdrant

            # Wait for Qdrant to be ready
            print_info "Waiting for Qdrant to be ready..."
            for i in {1..30}; do
                if curl -s -f "$QDRANT_URL/collections" > /dev/null 2>&1; then
                    print_success "Qdrant is now running"
                    break
                fi
                sleep 1
            done

            if ! curl -s -f "$QDRANT_URL/collections" > /dev/null 2>&1; then
                print_error "Qdrant failed to start"
                exit 1
            fi
        else
            print_error "Qdrant is required. Please start Qdrant and run this script again."
            exit 1
        fi
    else
        print_error "Cannot reach Qdrant at $QDRANT_URL"
        print_info "Please ensure Qdrant is running and accessible"
        exit 1
    fi
fi

# ============================================================================
# Step 4: MCP Server Setup
# ============================================================================
print_header "Step 4: Building MCP Server"

# Check if MCP directory exists
if [ ! -d "$MCP_DIR" ]; then
    print_error "MCP server directory not found at $MCP_DIR"
    print_info "Clone the MCP server repository first"
    exit 1
fi

cd "$MCP_DIR"

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    print_info "Installing MCP server dependencies..."
    npm install
    print_success "Dependencies installed"
else
    print_success "MCP server dependencies exist"
fi

# Build MCP server
print_info "Building MCP server..."
npm run build > /dev/null 2>&1
print_success "MCP server built successfully"

# Create .env file
print_info "Creating MCP server .env file..."
cat > "$MCP_DIR/.env" << EOF
OPENAI_API_KEY=${OPENAI_API_KEY}
QDRANT_URL=${QDRANT_URL}
QDRANT_COLLECTION_NAME=$COLLECTION_NAME
QDRANT_API_KEY=${QDRANT_API_KEY:-}
VOYAGE_API_KEY=${VOYAGE_API_KEY}
EMBEDDING_PROVIDER=voyage
EMBEDDING_MODEL=voyage-3.5-lite
EOF
print_success "MCP server .env configured"

cd "$SCRIPT_DIR"

# ============================================================================
# Step 5: Git Hooks Installation
# ============================================================================
print_header "Step 5: Installing Git Hooks"

# Check if project is a git repository
if [ ! -d "$PROJECT_PATH/.git" ]; then
    print_warning "Project is not a git repository, skipping git hooks"
else
    HOOKS_DIR="$PROJECT_PATH/.git/hooks"

    # Create pre-commit hook
    print_info "Creating pre-commit hook..."
    cat > "$HOOKS_DIR/pre-commit" << EOF
#!/bin/bash
# Semantic Code Memory - Pre-commit Hook
# Automatically index changes before commit
# Collection: $COLLECTION_NAME

echo "🔄 Running code indexing before commit..."

# Index changed files (uses global claude-indexer wrapper)
claude-indexer index -p "\$(pwd)" -c "$COLLECTION_NAME" 2>&1 | grep -E "(✓|✗|Error)" || true

# Check if indexing succeeded
if [ \$? -eq 0 ]; then
    echo "✅ Indexing complete"
else
    echo "⚠️  Indexing failed - proceeding anyway"
fi

# Always allow commit to proceed
exit 0
EOF
    chmod +x "$HOOKS_DIR/pre-commit"
    print_success "Pre-commit hook installed"

    # Create post-merge hook
    print_info "Creating post-merge hook..."
    cat > "$HOOKS_DIR/post-merge" << EOF
#!/bin/bash
# Semantic Code Memory - Post-merge Hook
# Automatically index changes after merge/pull
# Collection: $COLLECTION_NAME

echo "🔄 Running code indexing after merge/pull..."

# Index all changes (uses global claude-indexer wrapper)
claude-indexer index -p "\$(pwd)" -c "$COLLECTION_NAME" 2>&1 | grep -E "(✓|✗|Error)" || true

# Check if indexing succeeded
if [ \$? -eq 0 ]; then
    echo "✅ Indexing complete"
else
    echo "⚠️  Indexing failed - proceeding anyway"
fi

# Always allow operation to proceed
exit 0
EOF
    chmod +x "$HOOKS_DIR/post-merge"
    print_success "Post-merge hook installed"

    # Create post-checkout hook
    print_info "Creating post-checkout hook..."
    cat > "$HOOKS_DIR/post-checkout" << EOF
#!/bin/bash
# Semantic Code Memory - Post-checkout Hook
# Automatically index changes after branch checkout
# Collection: $COLLECTION_NAME

# Get hook parameters
prev_head=\$1
new_head=\$2
branch_checkout=\$3

# Only run on branch checkouts (not file checkouts)
if [ "\$branch_checkout" = "1" ]; then
    echo "🔄 Running code indexing after branch checkout..."

    # Index all changes (uses global claude-indexer wrapper)
    claude-indexer index -p "\$(pwd)" -c "$COLLECTION_NAME" 2>&1 | grep -E "(✓|✗|Error)" || true

    # Check if indexing succeeded
    if [ \$? -eq 0 ]; then
        echo "✅ Indexing complete"
    else
        echo "⚠️  Indexing failed - proceeding anyway"
    fi
fi

# Always allow operation to proceed
exit 0
EOF
    chmod +x "$HOOKS_DIR/post-checkout"
    print_success "Post-checkout hook installed"
fi

# ============================================================================
# Step 6: MCP Server Configuration
# ============================================================================
print_header "Step 6: Configuring MCP Server"

# SECURITY FIRST: Add .mcp.json to .gitignore immediately (contains API keys)
print_info "Securing API keys by adding .mcp.json to .gitignore..."
GITIGNORE_PATH="$PROJECT_PATH/.gitignore"

if [ ! -f "$GITIGNORE_PATH" ]; then
    # Create .gitignore if it doesn't exist
    echo ".mcp.json" > "$GITIGNORE_PATH"
    print_success "Created .gitignore with .mcp.json"
else
    # Add .mcp.json if not already present
    if ! grep -q "^\.mcp\.json$" "$GITIGNORE_PATH"; then
        echo "" >> "$GITIGNORE_PATH"
        echo ".mcp.json" >> "$GITIGNORE_PATH"
        print_success "Added .mcp.json to .gitignore"
    else
        print_success ".mcp.json already in .gitignore"
    fi
fi

# Verify .gitignore contains .mcp.json before proceeding
if ! grep -q "^\.mcp\.json$" "$GITIGNORE_PATH"; then
    print_error "Failed to add .mcp.json to .gitignore - aborting for security"
    exit 1
fi

# Create .mcp.json with hardcoded values (git-ignored, fully automated)
print_info "Creating .mcp.json with API keys (git-ignored)..."
cat > "$PROJECT_PATH/.mcp.json" << EOF
{
  "mcpServers": {
    "${COLLECTION_NAME}-memory": {
      "type": "stdio",
      "command": "node",
      "args": [
        "$MCP_DIR/dist/index.js"
      ],
      "env": {
        "OPENAI_API_KEY": "$OPENAI_API_KEY",
        "QDRANT_URL": "$QDRANT_URL",
        "QDRANT_COLLECTION_NAME": "$COLLECTION_NAME",
        "QDRANT_API_KEY": "${QDRANT_API_KEY:-}",
        "VOYAGE_API_KEY": "$VOYAGE_API_KEY",
        "EMBEDDING_PROVIDER": "voyage",
        "EMBEDDING_MODEL": "voyage-3.5-lite"
      }
    }
  }
}
EOF
print_success "Created .mcp.json (works immediately, git-ignored)"

# Create .mcp.json.example template with env vars (safe to commit)
print_info "Creating .mcp.json.example template (committable)..."
cat > "$PROJECT_PATH/.mcp.json.example" << 'EOF'
{
  "mcpServers": {
    "COLLECTION_NAME-memory": {
      "type": "stdio",
      "command": "node",
      "args": [
        "${CLAUDE_MEMORY_PATH}/mcp-qdrant-memory/dist/index.js"
      ],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "QDRANT_URL": "${QDRANT_URL:-http://localhost:6333}",
        "QDRANT_COLLECTION_NAME": "COLLECTION_NAME",
        "QDRANT_API_KEY": "${QDRANT_API_KEY:-}",
        "VOYAGE_API_KEY": "${VOYAGE_API_KEY}",
        "EMBEDDING_PROVIDER": "voyage",
        "EMBEDDING_MODEL": "voyage-3.5-lite"
      }
    }
  }
}
EOF
print_success "Created .mcp.json.example template"

print_success "MCP server configured"
print_info "Server name: ${COLLECTION_NAME}-memory"
print_info "Config location: $PROJECT_PATH/.mcp.json (git-ignored)"
print_info "Team template: $PROJECT_PATH/.mcp.json.example (committable)"
print_warning "⚠️  SECURITY: .mcp.json contains API keys and is git-ignored"
print_warning "Restart Claude Code to load the new MCP server"

# ============================================================================
# Step 7: Generate CLAUDE.md Documentation
# ============================================================================
print_header "Step 7: Generating CLAUDE.md Documentation"

# Check if template exists
if [ ! -f "$TEMPLATE_FILE" ]; then
    print_error "Template file not found: $TEMPLATE_FILE"
    exit 1
fi

# Get project name from path
PROJECT_NAME="$(basename "$PROJECT_PATH")"

# Read template
CLAUDE_MD_CONTENT=$(cat "$TEMPLATE_FILE")

# Substitute variables (stats will be updated after indexing)
CLAUDE_MD_CONTENT="${CLAUDE_MD_CONTENT//\{\{PROJECT_NAME\}\}/$PROJECT_NAME}"
CLAUDE_MD_CONTENT="${CLAUDE_MD_CONTENT//\{\{COLLECTION_NAME\}\}/$COLLECTION_NAME}"
CLAUDE_MD_CONTENT="${CLAUDE_MD_CONTENT//\{\{PROJECT_PATH\}\}/$PROJECT_PATH}"
CLAUDE_MD_CONTENT="${CLAUDE_MD_CONTENT//\{\{GENERATION_DATE\}\}/$(date '+%Y-%m-%d %H:%M:%S')}"
CLAUDE_MD_CONTENT="${CLAUDE_MD_CONTENT//\{\{VECTOR_COUNT\}\}/[pending indexing]}"
CLAUDE_MD_CONTENT="${CLAUDE_MD_CONTENT//\{\{FILE_COUNT\}\}/[pending indexing]}"

# Write CLAUDE.md
CLAUDE_MD_PATH="$PROJECT_PATH/CLAUDE.md"
if [ -f "$CLAUDE_MD_PATH" ]; then
    # Backup existing CLAUDE.md
    BACKUP_PATH="${CLAUDE_MD_PATH}.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$CLAUDE_MD_PATH" "$BACKUP_PATH"
    print_warning "Existing CLAUDE.md backed up to $(basename "$BACKUP_PATH")"

    echo -e -n "${YELLOW}Append memory section to existing CLAUDE.md? [y/N]:${NC} "
    read -r append_choice

    if [[ "$append_choice" =~ ^[Yy]$ ]]; then
        echo -e "\n\n# ============================================================================" >> "$CLAUDE_MD_PATH"
        echo -e "# Semantic Code Memory System" >> "$CLAUDE_MD_PATH"
        echo -e "# ============================================================================\n" >> "$CLAUDE_MD_PATH"
        echo "$CLAUDE_MD_CONTENT" >> "$CLAUDE_MD_PATH"
        print_success "Memory section appended to CLAUDE.md"
    else
        print_info "Skipping CLAUDE.md update (backup available)"
    fi
else
    echo "$CLAUDE_MD_CONTENT" > "$CLAUDE_MD_PATH"
    print_success "CLAUDE.md created"
fi

# Create .claudeignore if it doesn't exist
CLAUDEIGNORE_PATH="$PROJECT_PATH/.claudeignore"
CLAUDEIGNORE_TEMPLATE="$SCRIPT_DIR/templates/.claudeignore.template"

if [ ! -f "$CLAUDEIGNORE_PATH" ]; then
    if [ -f "$CLAUDEIGNORE_TEMPLATE" ]; then
        print_info "Creating .claudeignore for custom exclusions..."
        cp "$CLAUDEIGNORE_TEMPLATE" "$CLAUDEIGNORE_PATH"
        print_success ".claudeignore created"
        print_info "Edit .claudeignore to add project-specific exclusions"
    else
        print_warning ".claudeignore template not found, skipping"
    fi
else
    print_success ".claudeignore already exists"
fi

# ============================================================================
# Step 7.5: Collection Health Check & Recovery
# ============================================================================
print_header "Step 7.5: Collection Health Check"

# Check for --recreate flag
if [ "$RECREATE_COLLECTION" = true ]; then
    print_warning "Force recreate requested - deleting existing collection..."
    $VENV_PATH/bin/python -c "
from qdrant_client import QdrantClient
try:
    client = QdrantClient('$QDRANT_URL', api_key='$QDRANT_API_KEY' if '$QDRANT_API_KEY' else None)
    if '$COLLECTION_NAME' in [c.name for c in client.get_collections().collections]:
        client.delete_collection('$COLLECTION_NAME')
        print('✓ Collection deleted successfully')
except Exception as e:
    print(f'⚠ Warning: Could not delete collection: {e}')
"
fi

# Health check for existing collection
HEALTH_STATUS=$($VENV_PATH/bin/python -c "
import sys
from qdrant_client import QdrantClient
from claude_indexer.storage.qdrant import QdrantStore
from claude_indexer.config.config_loader import ConfigLoader

try:
    client = QdrantClient('$QDRANT_URL', api_key='$QDRANT_API_KEY' if '$QDRANT_API_KEY' else None)
    collections = [c.name for c in client.get_collections().collections]

    if '$COLLECTION_NAME' not in collections:
        print('MISSING')
        sys.exit(0)

    # Try a test operation - insert a dummy point
    try:
        from qdrant_client.models import PointStruct
        test_point = PointStruct(
            id=999999999,
            vector={'default': [0.0] * 1024},
            payload={'test': True}
        )
        client.upsert(collection_name='$COLLECTION_NAME', points=[test_point])
        # Delete test point
        client.delete(collection_name='$COLLECTION_NAME', points_selector=[999999999])
        print('HEALTHY')
    except Exception as e:
        if 'segment creator' in str(e).lower() or 'wal' in str(e).lower():
            print('CORRUPTED')
        else:
            print('UNHEALTHY')

except Exception as e:
    print(f'ERROR: {e}')
    sys.exit(1)
" 2>&1)

case "$HEALTH_STATUS" in
    CORRUPTED)
        print_error "Collection $COLLECTION_NAME is corrupted (WAL errors detected)"
        echo -e -n "${YELLOW}Delete and recreate collection? [y/N]:${NC} "
        read -r recreate_choice

        if [[ "$recreate_choice" =~ ^[Yy]$ ]]; then
            print_info "Deleting corrupted collection..."
            $VENV_PATH/bin/python -c "
from qdrant_client import QdrantClient
try:
    client = QdrantClient('$QDRANT_URL', api_key='$QDRANT_API_KEY' if '$QDRANT_API_KEY' else None)
    client.delete_collection('$COLLECTION_NAME')
    print('✓ Collection deleted')
except Exception as e:
    print(f'❌ Failed to delete: {e}')
    exit(1)
"
            print_success "Collection deleted - will be recreated during indexing"
        else
            print_error "Cannot proceed with corrupted collection"
            print_info "Run with -r flag to force recreation: $0 -p '$PROJECT_PATH' -c '$COLLECTION_NAME' -r"
            exit 1
        fi
        ;;
    UNHEALTHY)
        print_warning "Collection $COLLECTION_NAME may have issues"
        echo -e -n "${YELLOW}Continue anyway? [y/N]:${NC} "
        read -r continue_choice
        if [[ ! "$continue_choice" =~ ^[Yy]$ ]]; then
            exit 1
        fi
        ;;
    HEALTHY)
        print_success "Collection $COLLECTION_NAME is healthy"
        ;;
    MISSING)
        print_info "Collection $COLLECTION_NAME will be created during indexing"
        ;;
    ERROR:*)
        print_error "$HEALTH_STATUS"
        exit 1
        ;;
    *)
        print_warning "Unknown health status: $HEALTH_STATUS"
        ;;
esac

# ============================================================================
# Step 8: Initial Indexing
# ============================================================================
print_header "Step 8: Running Initial Indexing"

print_info "This may take several minutes for large projects..."
print_info "Indexing $PROJECT_PATH..."

# Run indexing with verbose output
INDEXER_CMD_FULL="$VENV_PATH/bin/python -m claude_indexer.cli_full"
$INDEXER_CMD_FULL index -p "$PROJECT_PATH" -c "$COLLECTION_NAME" --verbose

if [ $? -eq 0 ]; then
    print_success "Initial indexing complete"

    # Try to get indexing statistics
    print_info "Gathering statistics..."
    STATS_OUTPUT=$($VENV_PATH/bin/python "$SCRIPT_DIR/utils/qdrant_stats.py" -c "$COLLECTION_NAME" 2>/dev/null)

    if [ -n "$STATS_OUTPUT" ]; then
        # Extract statistics using grep and awk
        VECTOR_COUNT=$(echo "$STATS_OUTPUT" | grep "Total vectors" | awk '{print $3}' | tr -d ',')
        FILE_COUNT=$(echo "$STATS_OUTPUT" | grep "Unique files" | awk '{print $3}' | tr -d ',')

        if [ -n "$VECTOR_COUNT" ] && [ -n "$FILE_COUNT" ]; then
            # Update CLAUDE.md with actual statistics
            if [ -f "$CLAUDE_MD_PATH" ]; then
                sed -i.tmp "s/\[pending indexing\] vectors covering \[pending indexing\] files/$VECTOR_COUNT vectors covering $FILE_COUNT files/g" "$CLAUDE_MD_PATH"
                sed -i.tmp "s/{{VECTOR_COUNT}}/$VECTOR_COUNT/g" "$CLAUDE_MD_PATH"
                sed -i.tmp "s/{{FILE_COUNT}}/$FILE_COUNT/g" "$CLAUDE_MD_PATH"
                rm -f "${CLAUDE_MD_PATH}.tmp"
                print_success "CLAUDE.md updated with statistics"
            fi

            print_info "📊 Statistics:"
            print_info "   Total vectors: $VECTOR_COUNT"
            print_info "   Files indexed: $FILE_COUNT"
        fi
    fi
else
    print_error "Indexing failed"
    print_info "Check logs for details"
    exit 1
fi

# ============================================================================
# Step 9: Global Wrapper Installation (Optional)
# ============================================================================
print_header "Step 9: Global Wrapper Installation"

if [ ! -f "/usr/local/bin/claude-indexer" ]; then
    echo -e -n "${YELLOW}Install global claude-indexer command? [y/N]:${NC} "
    read -r install_wrapper

    if [[ "$install_wrapper" =~ ^[Yy]$ ]]; then
        print_info "Installing global wrapper..."
        sudo "$SCRIPT_DIR/install.sh"
        print_success "Global wrapper installed"
        print_info "You can now use 'claude-indexer' from anywhere"
    else
        print_info "Skipping global wrapper installation"
        print_info "Run ./install.sh later to install"
    fi
else
    print_success "Global wrapper already installed"
fi

# ============================================================================
# Step 10: Install Slash Commands
# ============================================================================
print_header "Step 10: Installing Slash Commands"

COMMANDS_SRC="$SCRIPT_DIR/.claude/commands"
COMMANDS_DEST="$PROJECT_PATH/.claude/commands"

if [ -d "$COMMANDS_SRC" ]; then
    mkdir -p "$COMMANDS_DEST"

    # Copy all slash command files
    for cmd_file in "$COMMANDS_SRC"/*.md; do
        if [ -f "$cmd_file" ]; then
            cp "$cmd_file" "$COMMANDS_DEST/"
            cmd_name=$(basename "$cmd_file" .md)
            print_success "Installed /$cmd_name command"
        fi
    done

    print_success "Slash commands installed to $COMMANDS_DEST"
else
    print_info "No slash commands to install (directory not found)"
fi

# ============================================================================
# Setup Complete!
# ============================================================================
print_header "✨ Setup Complete!"

echo -e "${GREEN}Your semantic code memory system is now configured!${NC}\n"

echo "📝 Summary:"
echo "  • Project: $PROJECT_PATH"
echo "  • Collection: $COLLECTION_NAME"
echo "  • MCP Server: ${COLLECTION_NAME}-memory"
echo "  • Git Hooks: ✓ Installed (pre-commit, post-merge, post-checkout)"
echo "  • Memory Guard: ✓ Configured (UserPromptSubmit, PreToolUse)"
echo "  • Slash Commands: ✓ /refactor (SOLID, DRY, orphan detection)"
echo "  • Documentation: ✓ CLAUDE.md created/updated"
echo ""

echo "🚀 Quick Start:"
echo "  # Search memory (use this in your IDE/editor)"
echo "  mcp__${COLLECTION_NAME}_memory__search_similar(\"feature name\", limit=20)"
echo ""
echo "  # Update index manually"
echo "  claude-indexer index -p \"$PROJECT_PATH\" -c \"$COLLECTION_NAME\""
echo ""
echo "  # View statistics"
echo "  python utils/qdrant_stats.py -c \"$COLLECTION_NAME\""
echo ""

echo "📚 Documentation:"
echo "  • Project instructions: $PROJECT_PATH/CLAUDE.md"
echo "  • MCP configuration: $PROJECT_PATH/.claude/settings.json"
echo "  • System README: $SCRIPT_DIR/README.md"
echo ""

print_success "All done! Restart your IDE/editor to load the new configuration."
