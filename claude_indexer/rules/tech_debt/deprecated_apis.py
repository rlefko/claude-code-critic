"""
Deprecated APIs detection rule.

Detects usage of deprecated functions, methods, and APIs
that should be replaced with modern alternatives.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    from ..base import Finding


class DeprecatedAPIsRule(BaseRule):
    """Detect usage of deprecated APIs."""

    # Deprecated APIs by language: (pattern, replacement, api_name)
    DEPRECATED_APIS = {
        "python": [
            # Python stdlib deprecations
            (
                r"\basyncio\.coroutine\b",
                "Use 'async def' syntax instead",
                "asyncio.coroutine",
            ),
            # Import-style deprecated collections (from collections import X)
            (
                r"from\s+collections\s+import\s+(?:.*,\s*)?(Callable|Mapping|MutableMapping|Sequence|Iterable|Iterator|Set|MutableSet)\b",
                "Use 'from collections.abc import X' instead",
                "collections direct import",
            ),
            (
                r"\bcollections\.Callable\b",
                "Use collections.abc.Callable instead",
                "collections.Callable",
            ),
            (
                r"\bcollections\.Mapping\b",
                "Use collections.abc.Mapping instead",
                "collections.Mapping",
            ),
            (
                r"\bcollections\.MutableMapping\b",
                "Use collections.abc.MutableMapping instead",
                "collections.MutableMapping",
            ),
            (
                r"\bcollections\.Sequence\b",
                "Use collections.abc.Sequence instead",
                "collections.Sequence",
            ),
            (
                r"\bcollections\.Iterable\b",
                "Use collections.abc.Iterable instead",
                "collections.Iterable",
            ),
            (
                r"\bcollections\.Iterator\b",
                "Use collections.abc.Iterator instead",
                "collections.Iterator",
            ),
            (
                r"\boptparse\b",
                "Use argparse module instead",
                "optparse",
            ),
            (
                r"\bimp\b\.(?!ort)",  # imp module, not import
                "Use importlib module instead",
                "imp module",
            ),
            (
                r"\.encode\(['\"]hex['\"]\)",
                "Use bytes.hex() method instead",
                "str.encode('hex')",
            ),
            (
                r"\.decode\(['\"]hex['\"]\)",
                "Use bytes.fromhex() instead",
                "str.decode('hex')",
            ),
            (
                r"\bparser\.readfp\b",
                "Use parser.read_file() instead",
                "ConfigParser.readfp()",
            ),
            (
                r"\bgetchildren\s*\(\s*\)",
                "Use list(elem) instead",
                "Element.getchildren()",
            ),
            (
                r"\bgetiterator\s*\(\s*\)",
                "Use Element.iter() instead",
                "Element.getiterator()",
            ),
            (
                r"@asyncio\.coroutine",
                "Use 'async def' syntax instead",
                "@asyncio.coroutine decorator",
            ),
            (
                r"\byield from asyncio\.sleep",
                "Use 'await asyncio.sleep()' instead",
                "yield from in coroutines",
            ),
            (
                r"\bloop\.create_task\b",
                "Use asyncio.create_task() instead (Python 3.7+)",
                "loop.create_task()",
            ),
            (
                r"\bloop\.run_until_complete\b",
                "Use asyncio.run() instead (Python 3.7+)",
                "loop.run_until_complete()",
            ),
            (
                r"\bplatform\.linux_distribution\b",
                "Use distro package instead",
                "platform.linux_distribution()",
            ),
            (
                r"\bplatform\.dist\b",
                "Use distro package instead",
                "platform.dist()",
            ),
            (
                r"\bssl\.PROTOCOL_SSLv2\b",
                "Use ssl.PROTOCOL_TLS_CLIENT instead",
                "ssl.PROTOCOL_SSLv2",
            ),
            (
                r"\bssl\.PROTOCOL_SSLv3\b",
                "Use ssl.PROTOCOL_TLS_CLIENT instead",
                "ssl.PROTOCOL_SSLv3",
            ),
            (
                r"\bssl\.PROTOCOL_TLSv1\b",
                "Use ssl.PROTOCOL_TLS_CLIENT instead",
                "ssl.PROTOCOL_TLSv1",
            ),
        ],
        "javascript": [
            # JavaScript/Node.js deprecations
            (
                r"\.substr\s*\(",
                "Use .substring() or .slice() instead",
                "String.substr()",
            ),
            (
                r"\bdocument\.write\s*\(",
                "Use DOM manipulation methods instead",
                "document.write()",
            ),
            (
                r"\bescape\s*\(",
                "Use encodeURIComponent() instead",
                "escape()",
            ),
            (
                r"\bunescape\s*\(",
                "Use decodeURIComponent() instead",
                "unescape()",
            ),
            (
                r"\.fontcolor\s*\(",
                "Use CSS styling instead",
                "String.fontcolor()",
            ),
            (
                r"\.fontsize\s*\(",
                "Use CSS styling instead",
                "String.fontsize()",
            ),
            (
                r"\.big\s*\(",
                "Use CSS styling instead",
                "String.big()",
            ),
            (
                r"\.blink\s*\(",
                "Use CSS animations instead",
                "String.blink()",
            ),
            (
                r"\.bold\s*\(",
                "Use CSS styling instead",
                "String.bold()",
            ),
            (
                r"\.italics\s*\(",
                "Use CSS styling instead",
                "String.italics()",
            ),
            (
                r"\.strike\s*\(",
                "Use CSS styling instead",
                "String.strike()",
            ),
            (
                r"\.anchor\s*\(",
                "Use createElement('a') instead",
                "String.anchor()",
            ),
            (
                r"\bnew Buffer\s*\(",
                "Use Buffer.from() or Buffer.alloc() instead",
                "new Buffer()",
            ),
            (
                r"\b__proto__\b",
                "Use Object.getPrototypeOf() instead",
                "__proto__",
            ),
            (
                r"\barguments\.callee\b",
                "Use named function expressions instead",
                "arguments.callee",
            ),
            (
                r"\brequire\s*\(\s*['\"]fs['\"]\s*\)\.exists\b",
                "Use fs.existsSync() or fs.access() instead",
                "fs.exists()",
            ),
        ],
        "typescript": [
            # TypeScript deprecations (includes JS ones)
            (
                r"\.substr\s*\(",
                "Use .substring() or .slice() instead",
                "String.substr()",
            ),
            (
                r"\bdocument\.write\s*\(",
                "Use DOM manipulation methods instead",
                "document.write()",
            ),
            (
                r"\bescape\s*\(",
                "Use encodeURIComponent() instead",
                "escape()",
            ),
            (
                r"\bunescape\s*\(",
                "Use decodeURIComponent() instead",
                "unescape()",
            ),
            (
                r"\bnew Buffer\s*\(",
                "Use Buffer.from() or Buffer.alloc() instead",
                "new Buffer()",
            ),
            (
                r"\b__proto__\b",
                "Use Object.getPrototypeOf() instead",
                "__proto__",
            ),
            (
                r"\barguments\.callee\b",
                "Use named function expressions instead",
                "arguments.callee",
            ),
            # TypeScript-specific
            (
                r"\b<(\w+)>\s*\w+",  # Old-style type assertions
                "Use 'value as Type' syntax instead",
                "<Type> assertion",
            ),
        ],
    }

    @property
    def rule_id(self) -> str:
        return "TECH_DEBT.DEPRECATED_APIS"

    @property
    def name(self) -> str:
        return "Deprecated API Detection"

    @property
    def category(self) -> str:
        return "tech_debt"

    @property
    def default_severity(self) -> Severity:
        return Severity.MEDIUM

    @property
    def triggers(self) -> list[Trigger]:
        return [Trigger.ON_WRITE, Trigger.ON_STOP, Trigger.ON_COMMIT]

    @property
    def supported_languages(self) -> list[str] | None:
        return ["python", "javascript", "typescript"]

    @property
    def description(self) -> str:
        return (
            "Detects usage of deprecated APIs, functions, and methods. "
            "Using deprecated APIs can lead to compatibility issues and "
            "should be replaced with modern alternatives."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def check(self, context: RuleContext) -> list["Finding"]:
        """Check for deprecated API usage.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for deprecated API usage
        """
        findings = []
        language = context.language

        # Get deprecation patterns for this language
        patterns = self.DEPRECATED_APIS.get(language, [])
        if not patterns:
            return findings

        lines = context.lines

        for line_num, line in enumerate(lines, start=1):
            # Skip if line not in diff
            if not context.is_line_in_diff(line_num):
                continue

            # Skip comments
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            # Check each deprecated pattern
            for pattern, replacement, api_name in patterns:
                if re.search(pattern, line):
                    findings.append(
                        self._create_finding(
                            summary=f"Deprecated API: {api_name}",
                            file_path=str(context.file_path),
                            line_number=line_num,
                            evidence=[
                                Evidence(
                                    description=f"Usage of deprecated '{api_name}'",
                                    line_number=line_num,
                                    code_snippet=line.strip(),
                                    data={
                                        "api_name": api_name,
                                        "replacement": replacement,
                                        "language": language,
                                    },
                                )
                            ],
                            remediation_hints=[
                                replacement,
                                f"'{api_name}' is deprecated and may be removed in future versions",
                                "Update to the recommended alternative for better compatibility",
                            ],
                            confidence=0.9,
                        )
                    )
                    break  # Only report first match per line

        return findings
