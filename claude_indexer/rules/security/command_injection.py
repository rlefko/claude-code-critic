"""
Command injection detection rule.

Detects potential command injection vulnerabilities from executing
shell commands with user-controlled input.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, Finding, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    pass


class CommandInjectionRule(BaseRule):
    """Detect command injection vulnerabilities."""

    # Language-specific patterns for command injection
    # Format: (pattern, description, confidence)
    PATTERNS = {
        "python": [
            # os.system with variables
            (
                r'os\.system\s*\([^)]*[\+\{\%]',
                "os.system() with dynamic input",
                0.95,
            ),
            # os.system alone (warning)
            (
                r'os\.system\s*\(',
                "os.system() usage (consider subprocess with shell=False)",
                0.60,
            ),
            # subprocess with shell=True and dynamic input
            (
                r'subprocess\.(call|run|Popen)\s*\([^)]*shell\s*=\s*True[^)]*[\+\{\%]',
                "subprocess with shell=True and dynamic input",
                0.95,
            ),
            # subprocess with shell=True (warning)
            (
                r'subprocess\.(call|run|Popen)\s*\([^)]*shell\s*=\s*True',
                "subprocess with shell=True (security risk)",
                0.70,
            ),
            # os.popen
            (
                r'os\.popen\s*\(',
                "os.popen() is vulnerable to injection",
                0.85,
            ),
            # eval with user input
            (
                r'\beval\s*\([^)]*[\+\{\%]',
                "eval() with dynamic input",
                0.95,
            ),
            # exec with user input
            (
                r'\bexec\s*\([^)]*[\+\{\%]',
                "exec() with dynamic input",
                0.95,
            ),
            # compile + exec pattern
            (
                r'compile\s*\([^)]+\).*exec',
                "compile() followed by exec()",
                0.80,
            ),
            # commands module (legacy)
            (
                r'commands\.(getoutput|getstatusoutput)\s*\(',
                "commands module is deprecated and unsafe",
                0.90,
            ),
            # subprocess.getoutput/getstatusoutput
            (
                r'subprocess\.(getoutput|getstatusoutput)\s*\(',
                "subprocess.getoutput() uses shell (security risk)",
                0.80,
            ),
        ],
        "javascript": [
            # child_process.exec with concatenation
            (
                r'(child_process\.)?exec\s*\([^)]*[\+\`]',
                "exec() with dynamic input",
                0.95,
            ),
            # execSync with dynamic input
            (
                r'execSync\s*\([^)]*[\+\`]',
                "execSync() with dynamic input",
                0.95,
            ),
            # spawn with shell option
            (
                r'spawn\s*\([^)]*shell\s*:\s*true',
                "spawn with shell option enabled",
                0.85,
            ),
            # eval with dynamic input
            (
                r'\beval\s*\([^)]*[\+\`]',
                "eval() with dynamic input",
                0.95,
            ),
            # Function constructor
            (
                r'new\s+Function\s*\([^)]*[\+\`]',
                "Function constructor with dynamic input",
                0.90,
            ),
            # vm.runInContext with dynamic code
            (
                r'vm\.(runInContext|runInNewContext|runInThisContext)\s*\([^)]*[\+\`]',
                "vm module with dynamic code",
                0.90,
            ),
        ],
        "typescript": [
            # Same as JavaScript
            (
                r'(child_process\.)?exec\s*\([^)]*[\+\`]',
                "exec() with dynamic input",
                0.95,
            ),
            (
                r'execSync\s*\([^)]*[\+\`]',
                "execSync() with dynamic input",
                0.95,
            ),
            (
                r'\beval\s*\([^)]*[\+\`]',
                "eval() with dynamic input",
                0.95,
            ),
            (
                r'new\s+Function\s*\([^)]*[\+\`]',
                "Function constructor with dynamic input",
                0.90,
            ),
        ],
        "java": [
            # Runtime.exec with concatenation
            (
                r'Runtime\.getRuntime\(\)\.exec\s*\([^)]*\+',
                "Runtime.exec() with string concatenation",
                0.95,
            ),
            # ProcessBuilder with dynamic input
            (
                r'new\s+ProcessBuilder\s*\([^)]*\+',
                "ProcessBuilder with dynamic input",
                0.85,
            ),
            # ScriptEngine eval
            (
                r'ScriptEngine.*\.eval\s*\([^)]*\+',
                "ScriptEngine.eval() with dynamic input",
                0.90,
            ),
        ],
        "php": [
            # system/exec/passthru with variable
            (
                r'\b(system|exec|passthru|shell_exec)\s*\([^)]*\$',
                "Shell function with variable input",
                0.95,
            ),
            # Backticks with variable
            (
                r'`[^`]*\$\w+',
                "Backtick execution with variable",
                0.95,
            ),
            # popen with variable
            (
                r'popen\s*\([^)]*\$',
                "popen() with variable input",
                0.90,
            ),
            # proc_open with variable
            (
                r'proc_open\s*\([^)]*\$',
                "proc_open() with variable input",
                0.90,
            ),
            # eval with variable
            (
                r'\beval\s*\([^)]*\$',
                "eval() with variable input",
                0.95,
            ),
        ],
        "go": [
            # exec.Command with variable
            (
                r'exec\.Command\s*\([^)]*\+',
                "exec.Command with string concatenation",
                0.85,
            ),
            # os/exec with fmt.Sprintf
            (
                r'exec\.Command\s*\(\s*fmt\.Sprintf',
                "exec.Command with fmt.Sprintf()",
                0.90,
            ),
        ],
        "ruby": [
            # system/exec with interpolation
            (
                r'\b(system|exec|`)[^`]*#\{',
                "Shell execution with string interpolation",
                0.95,
            ),
            # Open3 with interpolation
            (
                r'Open3\.\w+\s*\([^)]*#\{',
                "Open3 with string interpolation",
                0.90,
            ),
            # %x with interpolation
            (
                r'%x\[[^\]]*#\{|%x\{[^}]*#\{',
                "%x execution with interpolation",
                0.95,
            ),
            # Kernel.system
            (
                r'Kernel\.system\s*\([^)]*#\{',
                "Kernel.system with interpolation",
                0.95,
            ),
        ],
    }

    @property
    def rule_id(self) -> str:
        return "SECURITY.COMMAND_INJECTION"

    @property
    def name(self) -> str:
        return "Command Injection Detection"

    @property
    def category(self) -> str:
        return "security"

    @property
    def default_severity(self) -> Severity:
        return Severity.CRITICAL

    @property
    def triggers(self) -> list[Trigger]:
        return [Trigger.ON_WRITE, Trigger.ON_STOP, Trigger.ON_COMMIT]

    @property
    def supported_languages(self) -> list[str] | None:
        return list(self.PATTERNS.keys())

    @property
    def description(self) -> str:
        return (
            "Detects potential command injection vulnerabilities from shell "
            "command execution with user-controlled or dynamic input."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def _has_input_validation(self, surrounding_lines: list[str]) -> bool:
        """Check if there appears to be input validation nearby."""
        validation_patterns = [
            r'shlex\.quote',
            r'escapeshellarg',
            r'escapeshellcmd',
            r'allowlist|whitelist',
            r'validate.*input',
            r'sanitize',
            r'\.match\s*\(',
            r'\.test\s*\(',
            r'regex|regexp',
        ]
        text = " ".join(surrounding_lines)
        for pattern in validation_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def check(self, context: RuleContext) -> list[Finding]:
        """Check for command injection vulnerabilities.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for detected command injection risks
        """
        findings = []
        language = context.language

        # Get patterns for this language
        patterns = self.PATTERNS.get(language, [])
        if not patterns:
            return findings

        file_path_str = str(context.file_path)

        # Check if this is a test file
        is_test_file = any(
            marker in file_path_str.lower()
            for marker in ["test_", "_test", "tests/", "spec/", "mock/", "fixture"]
        )

        lines = context.lines

        for line_num, line in enumerate(lines, start=1):
            # Skip if line not in diff
            if not context.is_line_in_diff(line_num):
                continue

            # Skip comment lines
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            # Skip lines with nosec markers
            if "nosec" in line.lower() or "noqa" in line.lower():
                continue

            for pattern, description, base_confidence in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # Get surrounding lines for context
                    start = max(0, line_num - 5)
                    end = min(len(lines), line_num + 3)
                    surrounding = lines[start:end]

                    # Lower confidence if validation seems present
                    if self._has_input_validation(surrounding):
                        confidence = base_confidence * 0.6
                    elif is_test_file:
                        confidence = base_confidence * 0.5
                    else:
                        confidence = base_confidence

                    findings.append(
                        self._create_finding(
                            summary=f"Potential command injection: {description}",
                            file_path=file_path_str,
                            line_number=line_num,
                            evidence=[
                                Evidence(
                                    description=description,
                                    line_number=line_num,
                                    code_snippet=line.strip(),
                                    data={
                                        "language": language,
                                        "is_test_file": is_test_file,
                                    },
                                )
                            ],
                            remediation_hints=self._get_remediation_hints(language),
                            confidence=confidence,
                        )
                    )
                    break  # Only report first match per line

        return findings

    def _get_remediation_hints(self, language: str) -> list[str]:
        """Get language-specific remediation hints."""
        hints = {
            "python": [
                "Use subprocess with a list of arguments: subprocess.run(['cmd', arg1, arg2])",
                "Avoid shell=True; pass arguments as a list instead",
                "Use shlex.quote() if shell execution is unavoidable",
            ],
            "javascript": [
                "Use child_process.spawn() with arguments array instead of exec()",
                "Example: spawn('cmd', [arg1, arg2]) instead of exec(`cmd ${arg}`)",
                "Validate and sanitize all user inputs before use",
            ],
            "typescript": [
                "Use child_process.spawn() with arguments array instead of exec()",
                "Leverage TypeScript types to validate command arguments",
                "Use execa library for safer command execution",
            ],
            "java": [
                "Use ProcessBuilder with array arguments instead of single command string",
                "Example: new ProcessBuilder('cmd', arg1, arg2).start()",
                "Implement strict input validation with allowlists",
            ],
            "php": [
                "Use escapeshellarg() and escapeshellcmd() for input sanitization",
                "Prefer specific functions over shell execution when possible",
                "Use allowlist validation for expected command arguments",
            ],
            "go": [
                "Use exec.Command with separate arguments: exec.Command('cmd', arg1, arg2)",
                "Never pass user input directly to shell commands",
                "Validate inputs against expected patterns",
            ],
            "ruby": [
                "Use array form of system(): system('cmd', arg1, arg2)",
                "Use Shellwords.escape() for shell argument escaping",
                "Prefer Open3.capture3 with array arguments",
            ],
        }
        return hints.get(language, [
            "Pass command arguments as an array, not a concatenated string",
            "Use language-specific escaping functions for shell arguments",
            "Implement strict input validation using allowlists",
        ])
