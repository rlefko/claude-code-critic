#!/bin/bash
# ============================================================================
# Security Check Tests
# ============================================================================

echo "--- Security Checks ---"

# === Hardcoded Secrets ===

assert_exit_and_output "Detects hardcoded password" 1 "SECURITY.*secret" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"password = \"supersecret123\""}}'

assert_exit_and_output "Detects hardcoded API key" 1 "SECURITY.*secret" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"api_key = \"sk-abc123xyz\""}}'

assert_exit "Allows env var reference" 0 \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"password = os.environ.get(\"PASSWORD\")"}}'

# === SQL Injection (CRITICAL - blocks) ===

assert_exit_and_output "Detects Python f-string SQL" 2 "SQL injection" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"query = f\"SELECT * FROM users WHERE id={user_id}\""}}'

assert_exit_and_output "Detects JS template SQL" 2 "SQL injection" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.js","content":"const query = `SELECT * FROM users WHERE id=${userId}`"}}'

assert_exit_and_output "Detects string concat SQL" 2 "SQL injection" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"query = \"SELECT * FROM users WHERE id=\" + user_id"}}'

assert_exit "Allows parameterized query" 0 \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"cursor.execute(\"SELECT * FROM users WHERE id=?\", (user_id,))"}}'

# === XSS Patterns ===

assert_exit_and_output "Detects innerHTML" 1 "innerHTML" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.js","content":"element.innerHTML = userInput"}}'

assert_exit_and_output "Detects dangerouslySetInnerHTML" 1 "innerHTML" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.jsx","content":"<div dangerouslySetInnerHTML={{__html: content}} />"}}'

# === Command Injection ===

assert_exit_and_output "Detects eval with variable" 1 "injection" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"eval(user_input)"}}'

assert_exit_and_output "Detects os.system with f-string" 1 "command" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"os.system(f\"rm {filename}\")"}}'

# === Path Traversal ===

assert_exit_and_output "Detects path traversal" 1 "traversal" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"path = \"../../etc/passwd\""}}'

# === Insecure Deserialization ===

assert_exit_and_output "Detects pickle.load" 1 "pickle" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"data = pickle.load(file)"}}'

assert_exit_and_output "Detects yaml.load" 1 "yaml" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"config = yaml.load(f)"}}'

assert_exit "Allows yaml.safe_load" 0 \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"config = yaml.safe_load(f)"}}'

# === Weak Crypto ===

assert_exit_and_output "Detects MD5 for password" 1 "hash" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"hash = md5(password)"}}'

assert_exit_and_output "Detects hashlib.md5" 1 "MD5" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"h = hashlib.md5(data)"}}'

# === Sensitive Files ===

assert_exit "Blocks .env modification" 2 \
    '{"tool_name":"Write","tool_input":{"file_path":"/app/.env","content":"SECRET=abc"}}'

assert_exit "Blocks credentials file" 2 \
    '{"tool_name":"Write","tool_input":{"file_path":"/app/credentials.json","content":"{}"}}'

# === Git Safety ===

assert_exit "Blocks force push" 2 \
    '{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"}}'

assert_exit "Blocks hard reset" 2 \
    '{"tool_name":"Bash","tool_input":{"command":"git reset --hard HEAD~5"}}'

assert_exit "Blocks destructive rm" 2 \
    '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}'

assert_exit "Allows safe git commands" 0 \
    '{"tool_name":"Bash","tool_input":{"command":"git status"}}'
