"""Unit tests for UI consistency data models."""

from claude_indexer.ui.models import (
    Evidence,
    EvidenceType,
    Finding,
    LayoutBox,
    RuntimeElementFingerprint,
    Severity,
    StaticComponentFingerprint,
    StyleFingerprint,
    SymbolKind,
    SymbolRef,
    UIAnalysisResult,
    Visibility,
)


class TestSymbolRef:
    """Tests for SymbolRef dataclass."""

    def test_create_symbol_ref(self):
        """Test basic SymbolRef creation."""
        ref = SymbolRef(
            file_path="/src/Button.tsx",
            start_line=10,
            end_line=50,
            kind=SymbolKind.COMPONENT,
            name="Button",
        )

        assert ref.file_path == "/src/Button.tsx"
        assert ref.start_line == 10
        assert ref.end_line == 50
        assert ref.kind == SymbolKind.COMPONENT
        assert ref.name == "Button"
        assert ref.visibility == Visibility.LOCAL  # default

    def test_symbol_ref_to_dict(self):
        """Test SymbolRef serialization."""
        ref = SymbolRef(
            file_path="/src/Button.tsx",
            start_line=10,
            end_line=50,
            kind=SymbolKind.COMPONENT,
            visibility=Visibility.EXPORTED,
            name="Button",
        )

        data = ref.to_dict()

        assert data["file_path"] == "/src/Button.tsx"
        assert data["start_line"] == 10
        assert data["end_line"] == 50
        assert data["kind"] == "component"
        assert data["visibility"] == "exported"
        assert data["name"] == "Button"

    def test_symbol_ref_from_dict(self):
        """Test SymbolRef deserialization."""
        data = {
            "file_path": "/src/Card.tsx",
            "start_line": 1,
            "end_line": 100,
            "kind": "css",
            "visibility": "public",
            "name": "Card",
        }

        ref = SymbolRef.from_dict(data)

        assert ref.file_path == "/src/Card.tsx"
        assert ref.kind == SymbolKind.CSS
        assert ref.visibility == Visibility.PUBLIC
        assert ref.name == "Card"

    def test_symbol_ref_str(self):
        """Test SymbolRef string representation."""
        ref = SymbolRef(
            file_path="/src/Button.tsx",
            start_line=10,
            end_line=50,
            kind=SymbolKind.COMPONENT,
            name="Button",
        )

        assert str(ref) == "/src/Button.tsx:10 (Button)"

    def test_symbol_ref_without_name(self):
        """Test SymbolRef string without name."""
        ref = SymbolRef(
            file_path="/src/styles.css",
            start_line=5,
            end_line=10,
            kind=SymbolKind.CSS,
        )

        assert str(ref) == "/src/styles.css:5"


class TestEvidence:
    """Tests for Evidence dataclass."""

    def test_create_evidence(self):
        """Test basic Evidence creation."""
        evidence = Evidence(
            evidence_type=EvidenceType.STATIC,
            description="Hardcoded color found",
            data={"color": "#ff0000"},
        )

        assert evidence.evidence_type == EvidenceType.STATIC
        assert evidence.description == "Hardcoded color found"
        assert evidence.data["color"] == "#ff0000"

    def test_evidence_with_source_ref(self):
        """Test Evidence with source reference."""
        ref = SymbolRef(
            file_path="/src/Button.tsx",
            start_line=15,
            end_line=15,
            kind=SymbolKind.STYLE_OBJECT,
        )
        evidence = Evidence(
            evidence_type=EvidenceType.STATIC,
            description="Inline style object",
            source_ref=ref,
        )

        assert evidence.source_ref is not None
        assert evidence.source_ref.file_path == "/src/Button.tsx"

    def test_evidence_round_trip(self):
        """Test Evidence serialization round-trip."""
        ref = SymbolRef(
            file_path="/src/Button.tsx",
            start_line=15,
            end_line=15,
            kind=SymbolKind.STYLE_OBJECT,
        )
        evidence = Evidence(
            evidence_type=EvidenceType.SEMANTIC,
            description="Similar component found",
            data={"similarity": 0.92},
            source_ref=ref,
            similarity_score=0.92,
        )

        data = evidence.to_dict()
        restored = Evidence.from_dict(data)

        assert restored.evidence_type == EvidenceType.SEMANTIC
        assert restored.similarity_score == 0.92
        assert restored.source_ref is not None


class TestStyleFingerprint:
    """Tests for StyleFingerprint dataclass."""

    def test_create_style_fingerprint(self):
        """Test basic StyleFingerprint creation."""
        fp = StyleFingerprint(
            declaration_set={"color": "#333", "padding": "8px"},
            exact_hash="abc123",
            near_hash="def456",
        )

        assert fp.declaration_set["color"] == "#333"
        assert fp.exact_hash == "abc123"
        assert fp.near_hash == "def456"
        assert fp.tokens_used == []
        assert fp.source_refs == []

    def test_style_fingerprint_with_tokens(self):
        """Test StyleFingerprint with token usage."""
        fp = StyleFingerprint(
            declaration_set={"color": "var(--primary)"},
            exact_hash="abc123",
            near_hash="def456",
            tokens_used=["primary", "spacing-4"],
        )

        assert "primary" in fp.tokens_used
        assert "spacing-4" in fp.tokens_used

    def test_style_fingerprint_round_trip(self):
        """Test StyleFingerprint serialization round-trip."""
        ref = SymbolRef(
            file_path="/src/styles.css",
            start_line=10,
            end_line=15,
            kind=SymbolKind.CSS,
        )
        fp = StyleFingerprint(
            declaration_set={"color": "#333", "padding": "8px"},
            exact_hash="abc123",
            near_hash="def456",
            tokens_used=["primary"],
            source_refs=[ref],
        )

        data = fp.to_dict()
        restored = StyleFingerprint.from_dict(data)

        assert restored.declaration_set == fp.declaration_set
        assert restored.exact_hash == fp.exact_hash
        assert len(restored.source_refs) == 1


class TestStaticComponentFingerprint:
    """Tests for StaticComponentFingerprint dataclass."""

    def test_create_component_fingerprint(self):
        """Test basic StaticComponentFingerprint creation."""
        fp = StaticComponentFingerprint(
            structure_hash="hash123",
            style_refs=["btn", "btn-primary"],
        )

        assert fp.structure_hash == "hash123"
        assert "btn" in fp.style_refs
        assert fp.prop_shape_sketch is None

    def test_component_fingerprint_with_props(self):
        """Test StaticComponentFingerprint with prop shape."""
        fp = StaticComponentFingerprint(
            structure_hash="hash123",
            style_refs=["btn"],
            prop_shape_sketch={"onClick": "function", "disabled": "boolean"},
        )

        assert fp.prop_shape_sketch is not None
        assert fp.prop_shape_sketch["onClick"] == "function"

    def test_component_fingerprint_round_trip(self):
        """Test StaticComponentFingerprint serialization round-trip."""
        ref = SymbolRef(
            file_path="/src/Button.tsx",
            start_line=1,
            end_line=50,
            kind=SymbolKind.COMPONENT,
            name="Button",
        )
        fp = StaticComponentFingerprint(
            structure_hash="hash123",
            style_refs=["btn", "btn-primary"],
            prop_shape_sketch={"onClick": "function"},
            embedding_id="emb-123",
            source_ref=ref,
        )

        data = fp.to_dict()
        restored = StaticComponentFingerprint.from_dict(data)

        assert restored.structure_hash == "hash123"
        assert restored.embedding_id == "emb-123"
        assert restored.source_ref is not None


class TestLayoutBox:
    """Tests for LayoutBox dataclass."""

    def test_create_layout_box(self):
        """Test basic LayoutBox creation."""
        box = LayoutBox(x=10, y=20, width=100, height=50)

        assert box.x == 10
        assert box.y == 20
        assert box.width == 100
        assert box.height == 50
        assert box.padding == {}
        assert box.margin == {}

    def test_layout_box_with_spacing(self):
        """Test LayoutBox with padding and margin."""
        box = LayoutBox(
            x=0,
            y=0,
            width=200,
            height=100,
            padding={"top": 8, "right": 16, "bottom": 8, "left": 16},
            margin={"top": 0, "right": 0, "bottom": 16, "left": 0},
        )

        assert box.padding["top"] == 8
        assert box.margin["bottom"] == 16

    def test_layout_box_round_trip(self):
        """Test LayoutBox serialization round-trip."""
        box = LayoutBox(
            x=10,
            y=20,
            width=100,
            height=50,
            padding={"top": 8},
        )

        data = box.to_dict()
        restored = LayoutBox.from_dict(data)

        assert restored.x == box.x
        assert restored.padding["top"] == 8


class TestRuntimeElementFingerprint:
    """Tests for RuntimeElementFingerprint dataclass."""

    def test_create_runtime_fingerprint(self):
        """Test basic RuntimeElementFingerprint creation."""
        fp = RuntimeElementFingerprint(
            page_id="storybook:button-primary",
            selector='[data-testid="submit-btn"]',
            role="button",
        )

        assert fp.page_id == "storybook:button-primary"
        assert fp.selector == '[data-testid="submit-btn"]'
        assert fp.role == "button"

    def test_runtime_fingerprint_with_styles(self):
        """Test RuntimeElementFingerprint with computed styles."""
        fp = RuntimeElementFingerprint(
            page_id="page:checkout",
            selector=".submit-button",
            role="button",
            computed_style_subset={
                "font-size": "16px",
                "padding": "8px 16px",
                "border-radius": "4px",
            },
        )

        assert fp.computed_style_subset["font-size"] == "16px"
        assert fp.computed_style_subset["border-radius"] == "4px"

    def test_runtime_fingerprint_round_trip(self):
        """Test RuntimeElementFingerprint serialization round-trip."""
        box = LayoutBox(x=100, y=200, width=80, height=40)
        fp = RuntimeElementFingerprint(
            page_id="page:home",
            selector=".hero-btn",
            role="button",
            computed_style_subset={"color": "#fff"},
            layout_box=box,
            screenshot_hash="phash123",
            source_map_hint="HeroButton",
        )

        data = fp.to_dict()
        restored = RuntimeElementFingerprint.from_dict(data)

        assert restored.page_id == "page:home"
        assert restored.screenshot_hash == "phash123"
        assert restored.layout_box is not None
        assert restored.layout_box.width == 80


class TestFinding:
    """Tests for Finding dataclass."""

    def test_create_finding(self):
        """Test basic Finding creation."""
        finding = Finding(
            rule_id="COLOR.NON_TOKEN",
            severity=Severity.FAIL,
            confidence=0.95,
            summary="Hardcoded color #ff0000 should use design token",
        )

        assert finding.rule_id == "COLOR.NON_TOKEN"
        assert finding.severity == Severity.FAIL
        assert finding.confidence == 0.95
        assert finding.is_new is True

    def test_finding_with_evidence(self):
        """Test Finding with multiple evidence types."""
        static_evidence = Evidence(
            evidence_type=EvidenceType.STATIC,
            description="Found in source",
        )
        semantic_evidence = Evidence(
            evidence_type=EvidenceType.SEMANTIC,
            description="Similar to existing token",
        )

        finding = Finding(
            rule_id="COLOR.NON_TOKEN",
            severity=Severity.WARN,
            confidence=0.85,
            summary="Hardcoded color found",
            evidence=[static_evidence, semantic_evidence],
        )

        assert len(finding.evidence) == 2
        assert finding.has_multi_evidence() is True

    def test_finding_single_evidence(self):
        """Test Finding with single evidence."""
        evidence = Evidence(
            evidence_type=EvidenceType.STATIC,
            description="Found in source",
        )

        finding = Finding(
            rule_id="COLOR.NON_TOKEN",
            severity=Severity.INFO,
            confidence=0.5,
            summary="Potential issue",
            evidence=[evidence],
        )

        assert finding.has_multi_evidence() is False

    def test_finding_round_trip(self):
        """Test Finding serialization round-trip."""
        ref = SymbolRef(
            file_path="/src/Button.tsx",
            start_line=15,
            end_line=15,
            kind=SymbolKind.STYLE_OBJECT,
        )
        finding = Finding(
            rule_id="COMPONENT.DUPLICATE_CLUSTER",
            severity=Severity.WARN,
            confidence=0.88,
            summary="Component similar to existing Button",
            remediation_hints=["Consider reusing Button component"],
            source_ref=ref,
            is_new=True,
        )

        data = finding.to_dict()
        restored = Finding.from_dict(data)

        assert restored.rule_id == "COMPONENT.DUPLICATE_CLUSTER"
        assert restored.severity == Severity.WARN
        assert len(restored.remediation_hints) == 1
        assert restored.source_ref is not None


class TestUIAnalysisResult:
    """Tests for UIAnalysisResult dataclass."""

    def test_create_analysis_result(self):
        """Test basic UIAnalysisResult creation."""
        result = UIAnalysisResult(
            files_analyzed=["/src/Button.tsx", "/src/Card.tsx"],
            analysis_time_ms=150.5,
            tier=0,
        )

        assert len(result.files_analyzed) == 2
        assert result.analysis_time_ms == 150.5
        assert result.tier == 0
        assert result.findings == []

    def test_analysis_result_counts(self):
        """Test UIAnalysisResult severity counts."""
        findings = [
            Finding(
                rule_id="COLOR.NON_TOKEN",
                severity=Severity.FAIL,
                confidence=0.9,
                summary="Fail 1",
            ),
            Finding(
                rule_id="COLOR.NON_TOKEN",
                severity=Severity.FAIL,
                confidence=0.9,
                summary="Fail 2",
            ),
            Finding(
                rule_id="SPACING.OFF_SCALE",
                severity=Severity.WARN,
                confidence=0.8,
                summary="Warn 1",
            ),
            Finding(
                rule_id="STYLE.NEAR_DUPLICATE",
                severity=Severity.INFO,
                confidence=0.7,
                summary="Info 1",
            ),
        ]

        result = UIAnalysisResult(findings=findings)

        assert result.fail_count == 2
        assert result.warn_count == 1
        assert result.info_count == 1
        assert result.should_block() is True

    def test_analysis_result_no_block(self):
        """Test UIAnalysisResult that shouldn't block."""
        findings = [
            Finding(
                rule_id="SPACING.OFF_SCALE",
                severity=Severity.WARN,
                confidence=0.8,
                summary="Warning only",
            ),
        ]

        result = UIAnalysisResult(findings=findings)

        assert result.fail_count == 0
        assert result.should_block() is False

    def test_analysis_result_round_trip(self):
        """Test UIAnalysisResult serialization round-trip."""
        findings = [
            Finding(
                rule_id="COLOR.NON_TOKEN",
                severity=Severity.WARN,
                confidence=0.85,
                summary="Test finding",
            ),
        ]
        baseline = [
            Finding(
                rule_id="LEGACY.ISSUE",
                severity=Severity.INFO,
                confidence=0.5,
                summary="Baseline issue",
                is_new=False,
            ),
        ]

        result = UIAnalysisResult(
            findings=findings,
            baseline_findings=baseline,
            files_analyzed=["/src/test.tsx"],
            analysis_time_ms=200.0,
            tier=1,
        )

        data = result.to_dict()
        restored = UIAnalysisResult.from_dict(data)

        assert len(restored.findings) == 1
        assert len(restored.baseline_findings) == 1
        assert restored.tier == 1
