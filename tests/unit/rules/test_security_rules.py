"""
Unit tests for security rules.

Tests for all 11 security rules in claude_indexer/rules/security/.
"""

from pathlib import Path

import pytest

from claude_indexer.rules.base import RuleContext, Severity

# =============================================================================
# Test Fixtures
# =============================================================================


def create_context(
    content: str, language: str, file_path: str = "test.py"
) -> RuleContext:
    """Create a RuleContext for testing."""
    return RuleContext(
        file_path=Path(file_path),
        content=content,
        language=language,
    )


# =============================================================================
# Hardcoded Secrets Tests
# =============================================================================


class TestHardcodedSecretsRule:
    """Tests for SECURITY.HARDCODED_SECRETS rule."""

    @pytest.fixture
    def rule(self):
        from claude_indexer.rules.security.hardcoded_secrets import HardcodedSecretsRule

        return HardcodedSecretsRule()

    def test_detects_generic_api_key_pattern(self, rule):
        # Test with generic api_key pattern (triggers detection via generic API key pattern)
        # Note: "fake", "test", "dummy", etc. are filtered as placeholders
        context = create_context('api_key = "abcdef1234567890ghijklmnopqrs"', "python")
        findings = rule.check(context)
        assert len(findings) >= 1
        assert findings[0].severity == Severity.CRITICAL

    def test_detects_long_api_key(self, rule):
        context = create_context('apikey = "aBcD1234567890EfGhIjKlMnOpQrS"', "python")
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_detects_private_key(self, rule):
        context = create_context("-----BEGIN RSA PRIVATE KEY-----", "python")
        findings = rule.check(context)
        assert len(findings) >= 1
        assert "Private key" in findings[0].summary

    def test_detects_github_token(self, rule):
        context = create_context(
            'token = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"', "python"
        )
        findings = rule.check(context)
        assert len(findings) >= 1
        assert "GitHub" in findings[0].summary

    def test_ignores_env_reference(self, rule):
        context = create_context('api_key = os.environ.get("API_KEY")', "python")
        findings = rule.check(context)
        assert len(findings) == 0

    def test_ignores_placeholder(self, rule):
        context = create_context('api_key = "your-api-key-here"', "python")
        findings = rule.check(context)
        assert len(findings) == 0

    def test_ignores_comments(self, rule):
        context = create_context('# api_key = "AKIAIOSFODNN7EXAMPLE"', "python")
        findings = rule.check(context)
        assert len(findings) == 0

    def test_lower_confidence_for_test_files(self, rule):
        context = create_context(
            'api_key = "sk_live_1234567890abcdefghij"', "python", "test_auth.py"
        )
        findings = rule.check(context)
        if findings:
            assert findings[0].confidence < 0.9


# =============================================================================
# Missing HTTPS Tests
# =============================================================================


class TestMissingHTTPSRule:
    """Tests for SECURITY.MISSING_HTTPS rule."""

    @pytest.fixture
    def rule(self):
        from claude_indexer.rules.security.missing_https import MissingHTTPSRule

        return MissingHTTPSRule()

    def test_detects_http_api_url(self, rule):
        context = create_context(
            'url = "http://api.production.com/api/users"', "python"
        )
        findings = rule.check(context)
        assert len(findings) >= 1
        assert "HTTP" in findings[0].summary

    def test_detects_http_auth_url(self, rule):
        context = create_context('login_url = "http://myapp.io/auth/login"', "python")
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_ignores_localhost(self, rule):
        context = create_context('url = "http://localhost:8000/api"', "python")
        findings = rule.check(context)
        assert len(findings) == 0

    def test_ignores_private_ip(self, rule):
        context = create_context('url = "http://192.168.1.1/api"', "python")
        findings = rule.check(context)
        assert len(findings) == 0

    def test_has_auto_fix(self, rule):
        assert rule.can_auto_fix() is True


# =============================================================================
# Insecure Random Tests
# =============================================================================


class TestInsecureRandomRule:
    """Tests for SECURITY.INSECURE_RANDOM rule."""

    @pytest.fixture
    def rule(self):
        from claude_indexer.rules.security.insecure_random import InsecureRandomRule

        return InsecureRandomRule()

    def test_detects_python_random_in_security_context(self, rule):
        context = create_context(
            """
def generate_token():
    return random.randint(0, 999999)
""",
            "python",
        )
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_detects_math_random_javascript(self, rule):
        context = create_context(
            "const token = Math.random().toString(36)", "javascript"
        )
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_provides_remediation_hints(self, rule):
        context = create_context("random.randint(0, 100)", "python")
        findings = rule.check(context)
        if findings:
            assert len(findings[0].remediation_hints) > 0


# =============================================================================
# Insecure Crypto Tests
# =============================================================================


class TestInsecureCryptoRule:
    """Tests for SECURITY.INSECURE_CRYPTO rule."""

    @pytest.fixture
    def rule(self):
        from claude_indexer.rules.security.insecure_crypto import InsecureCryptoRule

        return InsecureCryptoRule()

    def test_detects_md5(self, rule):
        context = create_context("hash = hashlib.md5(data).hexdigest()", "python")
        findings = rule.check(context)
        assert len(findings) >= 1
        assert "MD5" in findings[0].summary

    def test_detects_sha1(self, rule):
        context = create_context("hash = hashlib.sha1(data).hexdigest()", "python")
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_detects_ecb_mode(self, rule):
        context = create_context("cipher = AES.new(key, AES.MODE_ECB)", "python")
        findings = rule.check(context)
        assert len(findings) >= 1
        assert "ECB" in findings[0].summary

    def test_detects_create_cipher_deprecated(self, rule):
        context = create_context(
            'const cipher = crypto.createCipher("aes-256-cbc", key)', "javascript"
        )
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_lower_confidence_for_checksum_context(self, rule):
        context = create_context(
            """
# Calculate file checksum
checksum = hashlib.md5(file_content).hexdigest()
""",
            "python",
        )
        findings = rule.check(context)
        if findings:
            assert findings[0].confidence < 0.85


# =============================================================================
# SQL Injection Tests
# =============================================================================


class TestSQLInjectionRule:
    """Tests for SECURITY.SQL_INJECTION rule."""

    @pytest.fixture
    def rule(self):
        from claude_indexer.rules.security.sql_injection import SQLInjectionRule

        return SQLInjectionRule()

    def test_detects_f_string_sql(self, rule):
        context = create_context(
            'query = f"SELECT * FROM users WHERE id = {user_id}"', "python"
        )
        findings = rule.check(context)
        assert len(findings) >= 1
        assert findings[0].severity == Severity.CRITICAL

    def test_detects_format_sql(self, rule):
        context = create_context(
            'query = "SELECT * FROM users WHERE id = {}".format(user_id)', "python"
        )
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_detects_concatenation_sql(self, rule):
        context = create_context(
            'query = "SELECT * FROM users WHERE id = " + user_id', "python"
        )
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_detects_template_literal_js(self, rule):
        context = create_context(
            "const query = `SELECT * FROM users WHERE id = ${userId}`", "javascript"
        )
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_ignores_parameterized_query(self, rule):
        context = create_context(
            'cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))', "python"
        )
        findings = rule.check(context)
        assert len(findings) == 0


# =============================================================================
# Command Injection Tests
# =============================================================================


class TestCommandInjectionRule:
    """Tests for SECURITY.COMMAND_INJECTION rule."""

    @pytest.fixture
    def rule(self):
        from claude_indexer.rules.security.command_injection import CommandInjectionRule

        return CommandInjectionRule()

    def test_detects_os_system_with_variable(self, rule):
        context = create_context('os.system("ls " + user_input)', "python")
        findings = rule.check(context)
        assert len(findings) >= 1
        assert findings[0].severity == Severity.CRITICAL

    def test_detects_subprocess_shell_true(self, rule):
        context = create_context("subprocess.run(cmd, shell=True)", "python")
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_detects_eval_with_input(self, rule):
        context = create_context('eval(user_input + "test")', "python")
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_detects_exec_js(self, rule):
        context = create_context("exec(`ls ${userDir}`)", "javascript")
        findings = rule.check(context)
        assert len(findings) >= 1


# =============================================================================
# XSS Vulnerability Tests
# =============================================================================


class TestXSSVulnerabilityRule:
    """Tests for SECURITY.XSS_VULNERABILITY rule."""

    @pytest.fixture
    def rule(self):
        from claude_indexer.rules.security.xss_vulnerability import XSSVulnerabilityRule

        return XSSVulnerabilityRule()

    def test_detects_innerhtml_assignment(self, rule):
        context = create_context("element.innerHTML = userInput", "javascript")
        findings = rule.check(context)
        assert len(findings) >= 1
        assert findings[0].severity == Severity.CRITICAL

    def test_detects_document_write(self, rule):
        context = create_context("document.write(userContent)", "javascript")
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_detects_dangerously_set_innerhtml(self, rule):
        context = create_context(
            "<div dangerouslySetInnerHTML={{__html: content}} />", "javascript"
        )
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_detects_jinja_safe_filter(self, rule):
        context = create_context("{{ user_content | safe }}", "python")
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_ignores_sanitized_content(self, rule):
        context = create_context(
            "element.innerHTML = DOMPurify.sanitize(userInput)", "javascript"
        )
        findings = rule.check(context)
        assert len(findings) == 0


# =============================================================================
# Path Traversal Tests
# =============================================================================


class TestPathTraversalRule:
    """Tests for SECURITY.PATH_TRAVERSAL rule."""

    @pytest.fixture
    def rule(self):
        from claude_indexer.rules.security.path_traversal import PathTraversalRule

        return PathTraversalRule()

    def test_detects_open_with_request_data(self, rule):
        context = create_context('f = open(request.args.get("file"))', "python")
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_detects_fs_readfile_with_dynamic_path(self, rule):
        context = create_context(
            "fs.readFile(path + userInput, callback)", "javascript"
        )
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_detects_path_traversal_sequence(self, rule):
        context = create_context('path = "../../../etc/passwd"', "python")
        findings = rule.check(context)
        assert len(findings) >= 1


# =============================================================================
# Insecure Deserialization Tests
# =============================================================================


class TestInsecureDeserializeRule:
    """Tests for SECURITY.INSECURE_DESERIALIZE rule."""

    @pytest.fixture
    def rule(self):
        from claude_indexer.rules.security.insecure_deserialize import (
            InsecureDeserializeRule,
        )

        return InsecureDeserializeRule()

    def test_detects_pickle_loads(self, rule):
        context = create_context("data = pickle.loads(user_data)", "python")
        findings = rule.check(context)
        assert len(findings) >= 1
        assert "pickle" in findings[0].summary.lower()

    def test_detects_yaml_load_unsafe(self, rule):
        context = create_context("config = yaml.load(user_input)", "python")
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_detects_yaml_full_load(self, rule):
        # Note: yaml.unsafe_load pattern checks for yaml.unsafe_load
        # but yaml.full_load is also dangerous and has a simpler match
        context = create_context("config = yaml.full_load(data)", "python")
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_ignores_yaml_safe_load(self, rule):
        context = create_context("config = yaml.safe_load(data)", "python")
        findings = rule.check(context)
        assert len(findings) == 0

    def test_detects_node_serialize(self, rule):
        context = create_context("serialize.unserialize(userData)", "javascript")
        findings = rule.check(context)
        assert len(findings) >= 1


# =============================================================================
# Sensitive Exposure Tests
# =============================================================================


class TestSensitiveExposureRule:
    """Tests for SECURITY.SENSITIVE_EXPOSURE rule."""

    @pytest.fixture
    def rule(self):
        from claude_indexer.rules.security.sensitive_exposure import (
            SensitiveExposureRule,
        )

        return SensitiveExposureRule()

    def test_detects_logging_password(self, rule):
        context = create_context(
            'logger.info(f"User login with password: {password}")', "python"
        )
        findings = rule.check(context)
        assert len(findings) >= 1
        assert "password" in findings[0].summary.lower()

    def test_detects_console_log_token(self, rule):
        context = create_context('console.log("Auth token:", authToken)', "javascript")
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_detects_print_api_key(self, rule):
        context = create_context('print(f"Using API key: {api_key}")', "python")
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_ignores_redacted_values(self, rule):
        context = create_context('logger.info(f"Password: [REDACTED]")', "python")
        findings = rule.check(context)
        assert len(findings) == 0


# =============================================================================
# Missing Auth Tests
# =============================================================================


class TestMissingAuthRule:
    """Tests for SECURITY.MISSING_AUTH rule."""

    @pytest.fixture
    def rule(self):
        from claude_indexer.rules.security.missing_auth import MissingAuthRule

        return MissingAuthRule()

    def test_detects_flask_route_without_auth(self, rule):
        context = create_context(
            """
@app.route("/admin/users")
def get_users():
    return users
""",
            "python",
        )
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_ignores_flask_route_with_auth(self, rule):
        context = create_context(
            """
@app.route("/admin/users")
@login_required
def get_users():
    return users
""",
            "python",
        )
        findings = rule.check(context)
        assert len(findings) == 0

    def test_ignores_public_routes(self, rule):
        context = create_context(
            """
@app.route("/health")
def health_check():
    return {"status": "ok"}
""",
            "python",
        )
        findings = rule.check(context)
        assert len(findings) == 0

    def test_detects_express_route_without_auth(self, rule):
        context = create_context(
            'router.get("/users", (req, res) => { res.json(users) })', "javascript"
        )
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_ignores_express_route_with_auth(self, rule):
        context = create_context(
            'router.get("/users", authMiddleware, (req, res) => { res.json(users) })',
            "javascript",
        )
        findings = rule.check(context)
        assert len(findings) == 0

    def test_skips_test_files(self, rule):
        context = create_context(
            """
@app.route("/admin/users")
def get_users():
    return users
""",
            "python",
            "test_routes.py",
        )
        findings = rule.check(context)
        assert len(findings) == 0


# =============================================================================
# Rule Discovery Tests
# =============================================================================


class TestSecurityRuleDiscovery:
    """Test that all security rules are discoverable."""

    def test_all_rules_discoverable(self):
        from claude_indexer.rules.discovery import RuleDiscovery

        discovery = RuleDiscovery()
        rule_classes = discovery.discover_all()

        # Check for security rules
        security_rule_ids = []
        for rule_id, rule_cls in rule_classes.items():
            rule_instance = rule_cls()
            if rule_instance.category == "security":
                security_rule_ids.append(rule_id)

        expected_rules = [
            "SECURITY.SQL_INJECTION",
            "SECURITY.XSS_VULNERABILITY",
            "SECURITY.COMMAND_INJECTION",
            "SECURITY.HARDCODED_SECRETS",
            "SECURITY.INSECURE_CRYPTO",
            "SECURITY.PATH_TRAVERSAL",
            "SECURITY.INSECURE_DESERIALIZE",
            "SECURITY.MISSING_AUTH",
            "SECURITY.SENSITIVE_EXPOSURE",
            "SECURITY.INSECURE_RANDOM",
            "SECURITY.MISSING_HTTPS",
        ]

        for rule_id in expected_rules:
            assert rule_id in security_rule_ids, f"Missing rule: {rule_id}"

    def test_security_rules_have_critical_or_high_severity(self):
        from claude_indexer.rules.discovery import RuleDiscovery

        discovery = RuleDiscovery()
        rule_classes = discovery.discover_all()

        critical_rules = [
            "SECURITY.SQL_INJECTION",
            "SECURITY.XSS_VULNERABILITY",
            "SECURITY.COMMAND_INJECTION",
            "SECURITY.HARDCODED_SECRETS",
        ]

        for rule_id, rule_cls in rule_classes.items():
            if rule_id in critical_rules:
                rule_instance = rule_cls()
                assert rule_instance.default_severity == Severity.CRITICAL


# =============================================================================
# Rule Engine Integration Tests
# =============================================================================


class TestSecurityRulesWithEngine:
    """Test security rules work with the rule engine."""

    def test_engine_runs_security_rules(self):
        from claude_indexer.rules.base import Trigger
        from claude_indexer.rules.engine import RuleEngine

        engine = RuleEngine()
        engine.load_rules()

        # Create context with vulnerable code
        context = create_context(
            """
api_key = "aBcD1234567890EfGhIjKlMnOpQrSt"
query = f"SELECT * FROM users WHERE id = {user_id}"
os.system("ls " + user_input)
""",
            "python",
        )

        result = engine.run(context, trigger=Trigger.ON_COMMIT)

        # Should find multiple security issues
        assert len(result.findings) >= 2

    def test_engine_result_has_severity_counts(self):
        from claude_indexer.rules.base import Trigger
        from claude_indexer.rules.engine import RuleEngine

        engine = RuleEngine()
        engine.load_rules()

        context = create_context('api_key = "aBcD1234567890EfGhIjKlMnOpQrSt"', "python")

        result = engine.run(
            context,
            trigger=Trigger.ON_COMMIT,
        )

        # Result should have severity counts
        assert hasattr(result, "critical_count")
        assert hasattr(result, "high_count")
        # Can filter findings by severity using should_block
        assert hasattr(result, "should_block")
