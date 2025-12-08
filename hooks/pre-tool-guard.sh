#!/bin/bash
# ============================================================================
# Memory Guard v4.0 - Unified Intelligent Guard System
# ============================================================================
#
# A professional-grade security and quality hook for Claude Code.
# Combines fast pattern matching with intelligent AI-powered analysis.
#
# Architecture:
#   Bash Guard (fast patterns) → Python Guard (MCP memory + AI)
#
# Features:
#   - 18 pattern-based checks with severity levels
#   - Intelligent analysis via MCP memory tools
#   - Dependency impact, duplicate detection, test coverage
#   - Actionable fix suggestions
#   - Event logging for data-driven improvement
#
# Exit codes:
#   0 = Allow (proceed with tool execution)
#   1 = Warn (non-blocking, message shown to user)
#   2 = Block (operation rejected with error message)
#
# Design principles:
#   - NEVER block legitimate work; when in doubt, allow
#   - Fast pattern checks (~50ms) + intelligent analysis (when needed)
#   - Graceful degradation on errors
#   - Modular, testable, extensible
# ============================================================================

# === CONFIGURATION ===
readonly GUARD_VERSION="4.0"
readonly MAX_CONTENT_SIZE=1000000  # 1MB
readonly LOG_DIR="${HOME}/.claude-code-memory"
readonly LOG_FILE="${LOG_DIR}/guard.log"
readonly CONFIG_FILE="${LOG_DIR}/guard.conf"
readonly PROJECT_CONFIG=".guard.conf"

# Severity levels
readonly SEV_CRITICAL=3  # Block operation
readonly SEV_HIGH=2      # Warn prominently
readonly SEV_MEDIUM=1    # Warn
readonly SEV_LOW=0       # Info only

# Default settings (can be overridden by config)
MIN_SEVERITY=${MIN_SEVERITY:-0}
DISABLE_CHECKS="${DISABLE_CHECKS:-}"
ENABLE_LOGGING="${ENABLE_LOGGING:-true}"

# === STABILITY: Global error trap ===
trap 'exit 0' ERR

# === LOAD CONFIGURATION ===
load_config() {
    # Load global config
    [[ -f "$CONFIG_FILE" ]] && source "$CONFIG_FILE"
    # Load project config (overrides global)
    [[ -f "$PROJECT_CONFIG" ]] && source "$PROJECT_CONFIG"
}

# === LOGGING ===
log_event() {
    [[ "$ENABLE_LOGGING" != "true" ]] && return
    local level="$1" check="$2" file="$3"
    mkdir -p "$LOG_DIR"
    echo "$(date -Iseconds) $level $check ${file:-unknown}" >> "$LOG_FILE"
}

# === FRAMEWORK ===
declare -a BLOCKS=()
declare -a WARNINGS=()

is_check_disabled() {
    local check="$1"
    [[ "$DISABLE_CHECKS" == *"$check"* ]]
}

add_issue() {
    local severity="$1"
    local check_name="$2"
    local message="$3"
    local file="${4:-}"

    # Skip if below minimum severity
    [[ $severity -lt $MIN_SEVERITY ]] && return

    # Skip if check is disabled
    is_check_disabled "$check_name" && return

    # Format severity prefix
    local prefix=""
    case $severity in
        $SEV_CRITICAL) prefix="[CRITICAL]"; log_event "BLOCK" "$check_name" "$file" ;;
        $SEV_HIGH)     prefix="[HIGH]"; log_event "WARN" "$check_name" "$file" ;;
        $SEV_MEDIUM)   prefix=""; log_event "WARN" "$check_name" "$file" ;;
        $SEV_LOW)      prefix="[info]"; log_event "INFO" "$check_name" "$file" ;;
    esac

    if [[ $severity -eq $SEV_CRITICAL ]]; then
        BLOCKS+=("$prefix $message")
    else
        WARNINGS+=("$prefix $message")
    fi
}

# === SECURITY CHECKS ===

check_sensitive_files() {
    local file="$1"
    case "$file" in
        */.env|*/.env.*|*/credentials*|*/secrets*|*/.ssh/*|*/id_rsa*)
            echo "Blocked: Cannot modify sensitive file: $file" >&2
            log_event "BLOCK" "sensitive_file" "$file"
            return 1
            ;;
    esac
    return 0
}

check_hardcoded_secrets() {
    local content="$1" file="$2"
    if grep -qiE "(password|api_key|secret|token|private_key)\s*[:=]\s*[\"'][^\"']+[\"']" <<< "$content"; then
        add_issue $SEV_HIGH "hardcoded_secret" \
"[SECURITY] Hardcoded secret detected
  Fix: Use environment variables instead
  Before: password = \"secret123\"
  After:  password = os.environ.get(\"PASSWORD\")" "$file"
    fi
}

check_sql_injection() {
    local content="$1" file="$2"
    local found=0

    # Python f-strings, JS template literals, string concatenation, .format()
    if grep -qE 'f[\"'"'"'](SELECT|INSERT|UPDATE|DELETE)[^\"'"'"']*\{' <<< "$content"; then
        found=1
    elif grep -qE '`(SELECT|INSERT|UPDATE|DELETE).*\$\{' <<< "$content"; then
        found=1
    elif grep -qE '"(SELECT|INSERT|UPDATE|DELETE)[^"]*"\s*\+' <<< "$content"; then
        found=1
    elif grep -qE '\.(format|substitute)\s*\(.*\).*(SELECT|INSERT|UPDATE|DELETE)|(SELECT|INSERT|UPDATE|DELETE).*\.(format|substitute)\s*\(' <<< "$content"; then
        found=1
    fi

    [[ $found -eq 1 ]] && add_issue $SEV_CRITICAL "sql_injection" \
"[SECURITY] SQL injection vulnerability
  Fix: Use parameterized queries
  Before: query = f\"SELECT * FROM users WHERE id={user_id}\"
  After:  cursor.execute(\"SELECT * FROM users WHERE id=?\", (user_id,))" "$file"
}

check_xss_patterns() {
    local content="$1" file="$2"
    if grep -qE '(innerHTML|dangerouslySetInnerHTML|v-html)' <<< "$content"; then
        add_issue $SEV_HIGH "xss" \
"[SECURITY] XSS risk: innerHTML/dangerouslySetInnerHTML
  Fix: Sanitize input or use textContent
  Before: element.innerHTML = userInput
  After:  element.textContent = userInput" "$file"
    fi
}

check_command_injection() {
    local content="$1" file="$2"

    # Python eval() with any argument (risky with user input)
    if grep -qE 'eval\s*\([^)]+\)' <<< "$content"; then
        add_issue $SEV_HIGH "command_injection" \
"[SECURITY] eval() detected - high injection risk
  Fix: Use ast.literal_eval() for data or avoid eval entirely
  Before: result = eval(user_input)
  After:  result = ast.literal_eval(user_input)  # for data only" "$file"
    fi

    # os.system/subprocess with string interpolation
    if grep -qE '(os\.system|subprocess\.(call|run|Popen))\s*\(.*[f\"'"'"']' <<< "$content"; then
        add_issue $SEV_HIGH "command_injection" \
"[SECURITY] Shell command with string formatting
  Fix: Use list arguments instead of string
  Before: subprocess.run(f\"cmd {arg}\")
  After:  subprocess.run([\"cmd\", arg])" "$file"
    fi
}

check_path_traversal() {
    local content="$1" file="$2"
    if grep -qE '\.\./\.\.' <<< "$content"; then
        add_issue $SEV_MEDIUM "path_traversal" \
"[SECURITY] Path traversal pattern (../..)
  Fix: Validate and sanitize file paths
  Before: path = user_input
  After:  path = os.path.abspath(user_input); assert path.startswith(BASE_DIR)" "$file"
    fi
}

check_insecure_deserialize() {
    local content="$1" file="$2"

    if grep -qE 'pickle\.(load|loads)\s*\(' <<< "$content"; then
        add_issue $SEV_HIGH "insecure_deserialize" \
"[SECURITY] pickle.load() - unsafe with untrusted data
  Fix: Use JSON or implement RestrictedUnpickler
  Before: data = pickle.load(file)
  After:  data = json.load(file)" "$file"
    fi

    if grep -qE 'yaml\.load\s*\(' <<< "$content"; then
        if ! grep -qE 'yaml\.safe_load' <<< "$content"; then
            add_issue $SEV_HIGH "insecure_deserialize" \
"[SECURITY] yaml.load() without safe_load
  Fix: Use yaml.safe_load()
  Before: config = yaml.load(f)
  After:  config = yaml.safe_load(f)" "$file"
        fi
    fi
}

check_weak_crypto() {
    local content="$1" file="$2"

    if grep -qiE '(md5|sha1)\s*\(.*password' <<< "$content"; then
        add_issue $SEV_HIGH "weak_crypto" \
"[SECURITY] Weak hash for password (MD5/SHA1)
  Fix: Use bcrypt, scrypt, or argon2
  Before: hash = md5(password)
  After:  hash = bcrypt.hashpw(password, bcrypt.gensalt())" "$file"
    elif grep -qiE 'hashlib\.(md5|sha1)\s*\(' <<< "$content"; then
        add_issue $SEV_MEDIUM "weak_crypto" \
"[SECURITY] MD5/SHA1 detected
  Note: OK for checksums, not for security
  Consider: SHA256+ for security-sensitive hashing" "$file"
    fi
}

# === QUALITY CHECKS ===

check_todo_without_ticket() {
    local content="$1" file="$2"
    while IFS= read -r line; do
        if [[ -n "$line" ]] && ! grep -qE '[A-Z]+-[0-9]+' <<< "$line"; then
            local truncated="${line:0:50}"
            add_issue $SEV_LOW "todo_without_ticket" \
"[QUALITY] TODO without ticket reference
  Line: $truncated
  Fix: Add ticket reference (e.g., ABC-123)" "$file"
            break
        fi
    done < <(grep -E '#\s*TODO|//\s*TODO' <<< "$content")
}

check_unexplained_suppressions() {
    local content="$1" file="$2"
    while IFS= read -r line; do
        if [[ -n "$line" ]]; then
            if ! grep -qE '(noqa|type:\s*ignore|@ts-ignore|eslint-disable|pylint:\s*disable)(\s*[:\[].+|.{3,})' <<< "$line"; then
                local truncated="${line:0:50}"
                add_issue $SEV_LOW "unexplained_suppression" \
"[QUALITY] Lint suppression without explanation
  Line: $truncated
  Fix: Add code or comment (e.g., # noqa: E501)" "$file"
                break
            fi
        fi
    done < <(grep -E '# noqa|# type: ignore|// @ts-ignore|// eslint-disable|# pylint: disable' <<< "$content")
}

check_fixme_markers() {
    local content="$1" file="$2"
    if grep -qE '#\s*FIXME|//\s*FIXME' <<< "$content"; then
        local line
        line=$(grep -E '#\s*FIXME|//\s*FIXME' <<< "$content" | head -1)
        local truncated="${line:0:50}"
        add_issue $SEV_HIGH "fixme_marker" \
"[QUALITY] FIXME marker - known bug requiring fix
  Line: $truncated
  Action: Fix the bug or create a ticket" "$file"
    fi
}

check_hack_markers() {
    local content="$1" file="$2"
    if grep -qE '#\s*HACK|//\s*HACK' <<< "$content"; then
        local line
        line=$(grep -E '#\s*HACK|//\s*HACK' <<< "$content" | head -1)
        local truncated="${line:0:50}"
        add_issue $SEV_MEDIUM "hack_marker" \
"[QUALITY] HACK marker - fragile workaround
  Line: $truncated
  Action: Implement proper solution or document why hack is necessary" "$file"
    fi
}

check_deprecated_markers() {
    local content="$1" file="$2"
    if grep -qE '@deprecated|@Deprecated|#\s*DEPRECATED|//\s*DEPRECATED' <<< "$content"; then
        add_issue $SEV_MEDIUM "deprecated_marker" \
"[QUALITY] DEPRECATED code detected
  Action: Migrate to replacement or remove if unused" "$file"
    fi
}

check_debug_statements() {
    local content="$1" file="$2"

    # Python: print() and breakpoint()
    if grep -qE '^\s*print\s*\(|^\s*breakpoint\s*\(\)' <<< "$content"; then
        add_issue $SEV_LOW "debug_statement" \
"[QUALITY] Debug statement (print/breakpoint)
  Action: Remove before commit or use logging module" "$file"
        return
    fi

    # JavaScript: console.log/debug/warn/error
    if grep -qE '^\s*console\.(log|debug|warn|error|info)\s*\(' <<< "$content"; then
        add_issue $SEV_LOW "debug_statement" \
"[QUALITY] Debug statement (console.log)
  Action: Remove before commit or use proper logging" "$file"
    fi
}

# === RESILIENCE CHECKS ===

check_swallowed_exceptions() {
    local content="$1" file="$2"
    local collapsed
    collapsed=$(tr '\n' ' ' <<< "$content")
    if grep -qE 'except[^:]*:\s*pass|catch\s*\([^)]*\)\s*\{\s*\}' <<< "$collapsed"; then
        add_issue $SEV_MEDIUM "swallowed_exception" \
"[RESILIENCE] Swallowed exception
  Fix: Log or handle the error
  Before: except: pass
  After:  except Exception as e: logger.error(e)" "$file"
    fi
}

check_missing_timeouts() {
    local content="$1" file="$2"
    while IFS= read -r line; do
        if [[ -n "$line" ]] && ! grep -qE 'timeout\s*=' <<< "$line"; then
            local truncated="${line:0:40}"
            add_issue $SEV_MEDIUM "missing_timeout" \
"[RESILIENCE] HTTP call without timeout
  Line: $truncated...
  Fix: Add timeout parameter
  After: requests.get(url, timeout=30)" "$file"
            break
        fi
    done < <(grep -E 'requests\.(get|post|put|delete|patch)\(' <<< "$content")
}

# === DOCUMENTATION CHECKS ===

check_python_docstrings() {
    local content="$1" file="$2"
    if grep -qE '^def [a-z]' <<< "$content"; then
        if ! grep -qE '("""|'"'"''"'"''"'"')' <<< "$content"; then
            add_issue $SEV_LOW "missing_docstring" \
"[DOCS] Python function without docstring
  Fix: Add docstring for public functions
  def foo():
      \"\"\"Brief description.\"\"\"" "$file"
        fi
    fi
}

check_jsdoc_comments() {
    local content="$1" file="$2"
    if grep -qE '^export\s+(async\s+)?(function|const|default)' <<< "$content"; then
        if ! grep -qE '/\*\*' <<< "$content"; then
            add_issue $SEV_LOW "missing_jsdoc" \
"[DOCS] Exported function without JSDoc
  Fix: Add JSDoc for public API
  /** @param {string} name */
  export function greet(name) {" "$file"
        fi
    fi
}

# === GIT SAFETY CHECKS ===

check_dangerous_git_ops() {
    local command="$1"
    if grep -qE 'git\s+(push\s+.*--force|reset\s+--hard|clean\s+-fd)' <<< "$command"; then
        echo "Blocked: Dangerous git operation. Use with caution." >&2
        log_event "BLOCK" "dangerous_git" "bash"
        return 1
    fi
    return 0
}

check_destructive_rm() {
    local command="$1"
    if grep -qE 'rm\s+-rf\s+(/|~|\.\./|"\$)' <<< "$command"; then
        echo "Blocked: Potentially destructive rm -rf command." >&2
        log_event "BLOCK" "destructive_rm" "bash"
        return 1
    fi
    return 0
}

check_git_commit_reminder() {
    local command="$1"
    if grep -qE 'git\s+(commit|add)' <<< "$command"; then
        add_issue $SEV_LOW "git_commit" \
"[SECURITY] Verify no secrets in staged files before commit" ""
    fi
}

# === LANGUAGE-AWARE ROUTING ===

run_file_checks() {
    local file="$1"
    local content="$2"

    [[ -z "$content" ]] && return 0
    [[ ${#content} -gt $MAX_CONTENT_SIZE ]] && return 0

    # Skip binary content
    if grep -qP '[\x00-\x08]' <<< "$content" 2>/dev/null; then
        return 0
    fi

    # === Universal Security Checks ===
    check_hardcoded_secrets "$content" "$file"
    check_sql_injection "$content" "$file"
    check_xss_patterns "$content" "$file"
    check_command_injection "$content" "$file"
    check_path_traversal "$content" "$file"
    check_insecure_deserialize "$content" "$file"
    check_weak_crypto "$content" "$file"

    # === Language-Specific Checks ===
    case "$file" in
        *.py)
            check_python_docstrings "$content" "$file"
            check_swallowed_exceptions "$content" "$file"
            check_missing_timeouts "$content" "$file"
            ;;
        *.js|*.ts|*.jsx|*.tsx)
            check_jsdoc_comments "$content" "$file"
            check_swallowed_exceptions "$content" "$file"
            ;;
    esac

    # === Universal Quality Checks ===
    check_todo_without_ticket "$content" "$file"
    check_unexplained_suppressions "$content" "$file"
    check_fixme_markers "$content" "$file"
    check_hack_markers "$content" "$file"
    check_deprecated_markers "$content" "$file"
    check_debug_statements "$content" "$file"
}

run_bash_checks() {
    local command="$1"

    check_dangerous_git_ops "$command" || return 1
    check_destructive_rm "$command" || return 1
    check_git_commit_reminder "$command"

    return 0
}

# === INTELLIGENT GUARD INTEGRATION ===

# Python guard for intelligent analysis
call_python_guard() {
    local input="$1"
    local script_dir="$(dirname "$0")"
    local python_guard="$script_dir/../utils/memory_guard.py"

    # Check if Python guard exists
    [[ ! -f "$python_guard" ]] && return 0

    # Check if intelligent analysis is enabled
    [[ "$DISABLE_INTELLIGENT" == "true" ]] && return 0

    # Call Python guard with timeout (max 60s for Tier 3 analysis)
    local python_result
    python_result=$(timeout 60s python3 "$python_guard" <<< "$input" 2>&1) || return 0

    # Parse Python result (JSON format)
    if [[ -n "$python_result" ]]; then
        local decision reason
        decision=$(jq -r '.decision // empty' <<< "$python_result" 2>/dev/null)
        reason=$(jq -r '.reason // empty' <<< "$python_result" 2>/dev/null)

        if [[ "$decision" == "block" ]]; then
            BLOCKS+=("[INTELLIGENT] $reason")
        elif [[ -n "$reason" && "$reason" != "null" ]]; then
            # Add non-blocking intelligent analysis results
            WARNINGS+=("[INTELLIGENT] $reason")
        fi
    fi

    return 0
}

# === OUTPUT ===

output_results() {
    # Critical issues block
    if [[ ${#BLOCKS[@]} -gt 0 ]]; then
        for msg in "${BLOCKS[@]}"; do
            echo -e "$msg" >&2
        done
        exit 2
    fi

    # Warnings don't block
    if [[ ${#WARNINGS[@]} -gt 0 ]]; then
        for msg in "${WARNINGS[@]}"; do
            echo -e "$msg" >&2
        done
        exit 1
    fi

    exit 0
}

# === MAIN ===

main() {
    # Load configuration
    load_config

    # Read input
    local input
    input=$(cat)

    # Dependency check
    if ! command -v jq &>/dev/null; then
        exit 0
    fi

    # Input validation
    [[ -z "$input" ]] && exit 0

    # Parse tool info
    local tool_name file_path content command
    tool_name=$(jq -r '.tool_name // empty' <<< "$input") || exit 0

    case "$tool_name" in
        Write|Edit)
            file_path=$(jq -r '.tool_input.file_path // empty' <<< "$input")
            content=$(jq -r '.tool_input.content // .tool_input.new_string // empty' <<< "$input")

            check_sensitive_files "$file_path" || exit 2
            run_file_checks "$file_path" "$content"

            # Run intelligent analysis for code changes (non-blocking pattern checks passed)
            call_python_guard "$input"
            ;;

        Bash)
            command=$(jq -r '.tool_input.command // empty' <<< "$input")
            run_bash_checks "$command" || exit 2
            ;;
    esac

    output_results
}

main
