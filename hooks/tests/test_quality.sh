#!/bin/bash
# ============================================================================
# Quality Check Tests
# ============================================================================

echo "--- Quality Checks ---"

# === TODO without ticket ===

assert_exit_and_output "Detects TODO without ticket" 1 "TODO.*ticket" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"# TODO: fix this later"}}'

assert_exit "Allows TODO with ticket" 0 \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"# TODO ABC-123: fix this later"}}'

# === Unexplained suppressions ===

assert_exit_and_output "Detects bare noqa" 1 "suppression" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"x = 1 # noqa"}}'

assert_exit "Allows noqa with code" 0 \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"x = 1 # noqa: E501"}}'

assert_exit "Allows type: ignore with bracket" 0 \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"x = 1 # type: ignore[attr-defined]"}}'

# === Swallowed exceptions ===

assert_exit_and_output "Detects swallowed Python exception" 1 "exception" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"try:\n    foo()\nexcept:\n    pass"}}'

assert_exit_and_output "Detects swallowed JS exception" 1 "exception" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.js","content":"try { foo() } catch (e) { }"}}'

assert_exit "Allows exception with logging" 0 \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"try:\n    foo()\nexcept Exception as e:\n    logger.error(e)"}}'

# === Missing timeouts ===

assert_exit_and_output "Detects requests without timeout" 1 "timeout" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"response = requests.get(url)"}}'

assert_exit "Allows requests with timeout" 0 \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"response = requests.get(url, timeout=30)"}}'

# === Documentation (advisory) ===

assert_exit_and_output "Warns about Python function without docstring" 1 "docstring" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"def foo():\n    return 1"}}'

assert_exit "Allows function with docstring" 0 \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"def foo():\n    \"\"\"Does foo.\"\"\"\n    return 1"}}'

# === FIXME markers ===

assert_exit_and_output "Detects FIXME marker" 1 "FIXME" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"# FIXME: this calculation is wrong"}}'

assert_exit_and_output "Detects JS FIXME marker" 1 "FIXME" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.js","content":"// FIXME: memory leak here"}}'

# === HACK markers ===

assert_exit_and_output "Detects HACK marker" 1 "HACK" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"# HACK: workaround for API bug"}}'

assert_exit_and_output "Detects JS HACK marker" 1 "HACK" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.js","content":"// HACK: temporary fix"}}'

# === DEPRECATED markers ===

assert_exit_and_output "Detects @deprecated decorator" 1 "DEPRECATED" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"@deprecated\ndef old_function(): pass"}}'

assert_exit_and_output "Detects @Deprecated annotation" 1 "DEPRECATED" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.java","content":"@Deprecated\npublic void oldMethod() {}"}}'

# === Debug statements ===

assert_exit_and_output "Detects Python print statement" 1 "Debug statement" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"def foo():\n    print(x)\n    return x"}}'

assert_exit_and_output "Detects Python breakpoint" 1 "Debug statement" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"def foo():\n    breakpoint()\n    return x"}}'

assert_exit_and_output "Detects console.log" 1 "Debug statement" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.js","content":"function foo() {\n    console.log(x);\n    return x;\n}"}}'

assert_exit "Allows logger.info" 0 \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"def foo():\n    \"\"\"Does foo.\"\"\"\n    logger.info(x)\n    return x"}}'

# === Bare except clause ===

assert_exit_and_output "Detects bare except clause" 1 "Bare except" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"try:\n    foo()\nexcept:\n    logger.error(\"failed\")"}}'

assert_exit "Allows except Exception" 0 \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"def foo():\n    \"\"\"Does foo.\"\"\"\n    try:\n        bar()\n    except Exception as e:\n        logger.error(e)"}}'

assert_exit "Allows except with specific type" 0 \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"def foo():\n    \"\"\"Does foo.\"\"\"\n    try:\n        bar()\n    except ValueError:\n        logger.warning(\"value error\")"}}'

# === Mutable default arguments ===

assert_exit_and_output "Detects mutable default list" 1 "Mutable default" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"def foo(items=[]):\n    \"\"\"Does foo.\"\"\"\n    items.append(1)\n    return items"}}'

assert_exit_and_output "Detects mutable default dict" 1 "Mutable default" \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"def bar(config={}):\n    \"\"\"Does bar.\"\"\"\n    config[\"key\"] = \"value\"\n    return config"}}'

assert_exit "Allows None default with initialization" 0 \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"def foo(items=None):\n    \"\"\"Does foo.\"\"\"\n    items = items or []\n    return items"}}'

# === Clean code passes ===

assert_exit "Clean Python code passes" 0 \
    '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"def greet(name: str) -> str:\n    \"\"\"Greet someone.\"\"\"\n    return f\"Hello, {name}\""}}'

assert_exit "Clean JS code passes" 0 \
    '{"tool_name":"Write","tool_input":{"file_path":"test.js","content":"function greet(name) {\n    return \"Hello, \" + name;\n}"}}'
