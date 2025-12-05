---
description: Diagnose security vulnerabilities (secrets, injection, validation)
argument-hint: [count] [module-focus]
---

# Security Debt Analysis

You are analyzing this codebase for **security vulnerabilities**. Find the top $1 issues (default: 3 if not specified).

**Module focus**: $2 (if specified, only analyze code related to this module/area)

**This command is part of the tech debt diagnosis suite:**
| Command | Focus | Level |
|---------|-------|-------|
| /refactor | SOLID, DRY, orphaned code | Function/class |
| /resecure | Secrets, injection, validation | Security |
| /reresilience | Error handling, retries | Resilience |

**Priority order**: Hardcoded secrets > Injection vulnerabilities > Auth gaps > Missing validation > Weak crypto > Data exposure

---

## Security Constitution (Core Principles)

1. **Never hardcode secrets** - use environment variables or secrets managers
2. **Never trust user input** - validate and sanitize everything
3. **Defense in depth** - multiple layers of security
4. **Principle of least privilege** - minimal access, minimal exposure

---

## Severity Classification

### CRITICAL - Immediate remediation required
- Hardcoded credentials, API keys, tokens
- SQL injection vulnerabilities
- Command injection vulnerabilities
- Authentication bypass

### HIGH - Fix within 24 hours
- XSS vulnerabilities
- Missing authentication on sensitive endpoints
- Weak cryptographic algorithms
- Known vulnerable dependencies

### MEDIUM - Fix within 1 week
- Missing input validation
- Excessive data exposure in responses
- Missing rate limiting
- Insufficient logging

### LOW - Fix when convenient
- Missing security headers
- Verbose error messages
- Minor information disclosure

---

## Analysis Protocol

Execute this multi-phase analysis using the memory MCP tools available to you.

### Phase 0: Module Focus (if specified)

If a module focus was provided (e.g., "auth", "api", "payments"):

1. **Discover related entities**: Use `search_similar("$2", limit=50)` to find all code related to the module
2. **Map the module boundary**: Use `read_graph(entity="<top_match>", mode="relationships")` for key entities
3. **Scope limitation**: ALL subsequent analysis phases only consider entities discovered here

**If no module focus**: Analyze the entire codebase.

---

### Phase 1: Secrets Detection

1. Search for hardcoded credentials:
   - `search_similar("password api_key secret token", entityTypes=["function", "class"])`
   - Look for string literals with credential-like patterns
2. Check configuration files for exposed secrets
3. Look for patterns:
   - `password = "..."` / `api_key = "..."`
   - Base64-encoded strings that decode to credentials
   - Private keys embedded in code

---

### Phase 2: Injection Vulnerability Detection

1. **SQL Injection**: Search for string concatenation in queries:
   - `search_similar("SELECT INSERT UPDATE DELETE FROM WHERE", entityTypes=["function"])`
   - Look for f-strings or .format() in SQL
   - Flag: `f"SELECT * FROM users WHERE id = {user_id}"`

2. **Command Injection**: Search for shell execution:
   - `search_similar("subprocess os.system exec shell", entityTypes=["function"])`
   - Look for user input in command strings

3. **XSS**: Search for unescaped output:
   - `search_similar("innerHTML dangerouslySetInnerHTML", entityTypes=["function"])`
   - Look for user data rendered without sanitization

---

### Phase 3: Authentication/Authorization Gaps

1. Find API endpoints and check for auth:
   - `search_similar("route endpoint api handler", entityTypes=["function"])`
2. For each endpoint, verify:
   - Authentication decorator/middleware present
   - Authorization check for sensitive operations
3. Flag endpoints without protection

---

### Phase 4: Input Validation Gaps

1. Find functions accepting external input:
   - `search_similar("request.json request.body params query", entityTypes=["function"])`
2. Check for validation before use:
   - Type checking
   - Range/length validation
   - Format validation
3. Flag direct use of unvalidated input

---

### Phase 5: Cryptographic Weaknesses

1. Search for weak algorithms:
   - `search_similar("md5 sha1 des encrypt hash", entityTypes=["function"])`
2. Flag usage of:
   - MD5/SHA1 for security purposes
   - DES/3DES encryption
   - ECB mode for AES
   - Weak random number generation

---

### Phase 6: Sensitive Data Exposure

1. Search for logging of sensitive data:
   - `search_similar("log print debug password email ssn", entityTypes=["function"])`
2. Check API responses for excessive data:
   - Returning password hashes
   - Exposing internal IDs
   - Leaking PII unnecessarily

---

## Issue Categories

Report findings using these categories:

### [SECRET] - Hardcoded Secrets
```
[SECRET] Hardcoded credential detected
Location: config/database.py:12
Pattern: password = "admin123"
Risk: CRITICAL - credential exposure
Suggestion: Use environment variable or secrets manager
```

### [INJECT] - Injection Vulnerabilities
```
[INJECT] Potential SQL injection
Location: users/repository.py:45
Code: f"SELECT * FROM users WHERE id = {user_id}"
Risk: HIGH - arbitrary SQL execution
Suggestion: Use parameterized queries: cursor.execute("...WHERE id = ?", (user_id,))
```

### [XSS] - Cross-Site Scripting
```
[XSS] Unescaped user input in HTML
Location: templates/profile.html:23
Code: innerHTML = user.bio / dangerouslySetInnerHTML
Risk: HIGH - script injection
Suggestion: Sanitize input or use safe rendering methods
```

### [AUTH] - Authentication/Authorization Gaps
```
[AUTH] Endpoint missing authentication check
Location: api/admin.py:89 - DELETE /users/{id}
Problem: No @require_auth or permission check
Risk: HIGH - unauthorized access
Suggestion: Add authentication decorator and role check
```

### [VALIDATE] - Missing Input Validation
```
[VALIDATE] User input not validated
Location: api/orders.py:34
Input: request.json["quantity"] used directly
Risk: MEDIUM - type confusion, overflow, negative values
Suggestion: Validate type, range, and format before use
```

### [CRYPTO] - Weak Cryptography
```
[CRYPTO] Weak/outdated cryptographic algorithm
Location: auth/tokens.py:23
Algorithm: MD5 / SHA1 / DES
Risk: MEDIUM - cryptographic weakness
Suggestion: Use SHA-256+, bcrypt for passwords, AES-256 for encryption
```

### [DEPEND] - Vulnerable Dependencies
```
[DEPEND] Known vulnerability in dependency
Package: requests==2.25.0
CVE: CVE-2023-XXXXX (HIGH severity)
Risk: HIGH - remote code execution
Suggestion: Upgrade to requests>=2.31.0
```

### [EXPOSE] - Sensitive Data Exposure
```
[EXPOSE] Sensitive data in logs/responses
Location: auth/service.py:67
Data: logger.info(f"User {user.email} logged in with {password}")
Risk: HIGH - credential leakage
Suggestion: Never log passwords, tokens, or PII
```

---

## Output Format

Present your findings as:

```
## Security Analysis

**Scope**: [Entire codebase | Focus: $2]
**Files analyzed**: N
**Critical issues**: X
**High severity**: Y
**Medium severity**: Z

---

**Security Issues Found:**

1. **[CRITICAL]** [SECRET] Hardcoded API key
   - Location: config/stripe.py:12
   - Pattern: `STRIPE_KEY = "sk_live_..."`
   - Risk: Production credentials in source code
   - Suggestion: Move to environment variable

2. **[HIGH]** [INJECT] SQL injection vulnerability
   - Location: users/search.py:45
   - Code: `f"SELECT * FROM users WHERE name LIKE '%{query}%'"`
   - Risk: Arbitrary SQL execution
   - Suggestion: Use parameterized query

3. **[MEDIUM]** [VALIDATE] Missing input validation
   - Location: api/orders.py:34
   - Input: `quantity` used without type/range check
   - Risk: Invalid data, potential overflow
   - Suggestion: Add validation schema

---

Which issues would you like me to address? Enter numbers (e.g., '1,3') or 'all':
```

---

## User Delegation

After presenting findings, ask the user which issues to address.

Based on their selection, take the appropriate action:

| Issue Type | Action |
|------------|--------|
| **[SECRET]** | Replace with environment variable, add to .env.example |
| **[INJECT]** | Refactor to use parameterized queries/safe APIs |
| **[XSS]** | Add input sanitization or use safe rendering |
| **[AUTH]** | Add authentication decorator and permission checks |
| **[VALIDATE]** | Add validation schema using project's validation library |
| **[CRYPTO]** | Replace with secure algorithm, migrate existing data |
| **[DEPEND]** | Update dependency, test for breaking changes |
| **[EXPOSE]** | Remove sensitive data from logs/responses |

For each selected issue:
1. **Analyze the code** to understand the security context
2. **Generate secure replacement** following security best practices
3. **Show the proposed fix** with security explanation
4. **Wait for user confirmation** before making changes

Wait for user input before making any changes.
