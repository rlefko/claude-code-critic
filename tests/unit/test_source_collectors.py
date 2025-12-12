"""Unit tests for source collectors and framework adapters."""

from pathlib import Path

import pytest

from claude_indexer.ui.collectors.adapters.css import CSSAdapter
from claude_indexer.ui.collectors.adapters.generic import GenericAdapter
from claude_indexer.ui.collectors.adapters.react import ReactAdapter
from claude_indexer.ui.collectors.adapters.svelte import SvelteAdapter
from claude_indexer.ui.collectors.adapters.vue import VueAdapter
from claude_indexer.ui.collectors.base import (
    ExtractedComponent,
    ExtractedStyle,
    ExtractionResult,
)
from claude_indexer.ui.collectors.source import SourceCollector
from claude_indexer.ui.models import SymbolKind, SymbolRef


class TestExtractedComponent:
    """Tests for ExtractedComponent dataclass."""

    def test_create_extracted_component(self):
        """Test basic ExtractedComponent creation."""
        source_ref = SymbolRef(
            file_path="src/Button.tsx",
            start_line=10,
            end_line=50,
            kind=SymbolKind.COMPONENT,
        )
        comp = ExtractedComponent(
            name="Button",
            source_ref=source_ref,
            tag_name="Button",
            props={"onClick": "function"},
            children_structure="div span",
            style_refs=["btn", "btn-primary"],
            framework="react",
        )

        assert comp.name == "Button"
        assert comp.framework == "react"
        assert "btn" in comp.style_refs

    def test_serialization_roundtrip(self):
        """Test to_dict and from_dict produce equivalent objects."""
        source_ref = SymbolRef(
            file_path="test.tsx",
            start_line=1,
            end_line=10,
            kind=SymbolKind.COMPONENT,
        )
        comp = ExtractedComponent(
            name="Test",
            source_ref=source_ref,
            tag_name="Test",
            framework="react",
        )

        data = comp.to_dict()
        restored = ExtractedComponent.from_dict(data)

        assert restored.name == comp.name
        assert restored.framework == comp.framework


class TestExtractedStyle:
    """Tests for ExtractedStyle dataclass."""

    def test_create_css_style(self):
        """Test creating CSS rule style."""
        source_ref = SymbolRef(
            file_path="styles.css",
            start_line=5,
            end_line=10,
            kind=SymbolKind.CSS,
        )
        style = ExtractedStyle(
            source_ref=source_ref,
            selector=".btn",
            declarations={"color": "red", "padding": "10px"},
            is_inline=False,
            class_names=["btn"],
        )

        assert style.selector == ".btn"
        assert style.declarations["color"] == "red"
        assert not style.is_inline

    def test_create_inline_style(self):
        """Test creating inline style."""
        source_ref = SymbolRef(
            file_path="Button.tsx",
            start_line=15,
            end_line=15,
            kind=SymbolKind.STYLE_OBJECT,
        )
        style = ExtractedStyle(
            source_ref=source_ref,
            declarations={"color": "blue"},
            is_inline=True,
        )

        assert style.is_inline
        assert style.declarations["color"] == "blue"


class TestExtractionResult:
    """Tests for ExtractionResult dataclass."""

    def test_has_errors(self):
        """Test has_errors property."""
        result_with_errors = ExtractionResult(errors=["Error 1"])
        result_no_errors = ExtractionResult()

        assert result_with_errors.has_errors
        assert not result_no_errors.has_errors

    def test_is_empty(self):
        """Test is_empty property."""
        empty = ExtractionResult()
        with_components = ExtractionResult(
            components=[
                ExtractedComponent(
                    name="Test",
                    source_ref=SymbolRef("t.tsx", 1, 1, SymbolKind.COMPONENT),
                    tag_name="Test",
                )
            ]
        )

        assert empty.is_empty
        assert not with_components.is_empty

    def test_merge_results(self):
        """Test merging two extraction results."""
        result1 = ExtractionResult(
            components=[
                ExtractedComponent(
                    name="A",
                    source_ref=SymbolRef("a.tsx", 1, 1, SymbolKind.COMPONENT),
                    tag_name="A",
                )
            ],
            errors=["Error 1"],
        )
        result2 = ExtractionResult(
            components=[
                ExtractedComponent(
                    name="B",
                    source_ref=SymbolRef("b.tsx", 1, 1, SymbolKind.COMPONENT),
                    tag_name="B",
                )
            ],
            errors=["Error 2"],
        )

        merged = result1.merge(result2)

        assert len(merged.components) == 2
        assert len(merged.errors) == 2


class TestCSSAdapter:
    """Tests for CSS adapter."""

    @pytest.fixture
    def adapter(self) -> CSSAdapter:
        """Create a CSS adapter."""
        return CSSAdapter()

    def test_supported_extensions(self, adapter: CSSAdapter):
        """Test supported extensions."""
        assert ".css" in adapter.supported_extensions
        assert ".scss" in adapter.supported_extensions
        assert ".less" in adapter.supported_extensions

    def test_can_handle_css(self, adapter: CSSAdapter):
        """Test can_handle for CSS files."""
        assert adapter.can_handle(Path("styles.css"))
        assert adapter.can_handle(Path("styles.scss"))
        assert not adapter.can_handle(Path("component.tsx"))

    def test_extract_components_empty(self, adapter: CSSAdapter):
        """Test that CSS files have no components."""
        content = ".btn { color: red; }"
        components = adapter.extract_components(Path("test.css"), content)

        assert len(components) == 0

    def test_extract_style_usage(self, adapter: CSSAdapter):
        """Test extracting CSS rules."""
        content = """
        .btn { color: red; padding: 10px; }
        .container { display: flex; }
        """
        styles = adapter.extract_style_usage(Path("test.css"), content)

        assert len(styles) == 2
        assert any(s.selector == ".btn" for s in styles)
        assert any(s.selector == ".container" for s in styles)

    def test_extract_css_variables(self, adapter: CSSAdapter):
        """Test extracting CSS custom properties."""
        content = """
        :root {
            --primary-color: #3b82f6;
            --spacing-md: 16px;
        }
        """
        variables = adapter.extract_css_variables(Path("vars.css"), content)

        assert "--primary-color" in variables
        assert "--spacing-md" in variables

    def test_parse_declarations(self, adapter: CSSAdapter):
        """Test declaration parsing."""
        decls = adapter._parse_declarations("color: red; padding: 10px")

        assert decls["color"] == "red"
        assert decls["padding"] == "10px"


class TestReactAdapter:
    """Tests for React adapter."""

    @pytest.fixture
    def adapter(self) -> ReactAdapter:
        """Create a React adapter."""
        return ReactAdapter()

    def test_supported_extensions(self, adapter: ReactAdapter):
        """Test supported extensions."""
        assert ".tsx" in adapter.supported_extensions
        assert ".jsx" in adapter.supported_extensions

    def test_can_handle_tsx(self, adapter: ReactAdapter):
        """Test can_handle for TSX files."""
        assert adapter.can_handle(Path("Button.tsx"))
        assert adapter.can_handle(Path("Card.jsx"))
        assert not adapter.can_handle(Path("styles.css"))

    def test_extract_function_component(self, adapter: ReactAdapter):
        """Test extracting function component."""
        content = """
        export function Button({ onClick }) {
            return <button onClick={onClick}>Click</button>;
        }
        """
        components = adapter.extract_components(Path("Button.tsx"), content)

        assert len(components) >= 1
        assert any(c.name == "Button" for c in components)

    def test_extract_arrow_function_component(self, adapter: ReactAdapter):
        """Test extracting arrow function component."""
        content = """
        export const Card = () => {
            return <div className="card">Content</div>;
        };
        """
        components = adapter.extract_components(Path("Card.tsx"), content)

        assert any(c.name == "Card" for c in components)

    def test_extract_classname_usage(self, adapter: ReactAdapter):
        """Test extracting className attributes."""
        content = """
        function Button() {
            return <button className="btn btn-primary">Click</button>;
        }
        """
        styles = adapter.extract_style_usage(Path("Button.tsx"), content)

        assert len(styles) >= 1
        class_names = []
        for s in styles:
            class_names.extend(s.class_names)
        assert "btn" in class_names
        assert "btn-primary" in class_names

    def test_extract_inline_style(self, adapter: ReactAdapter):
        """Test extracting inline styles."""
        content = """
        function Box() {
            return <div style={{ color: 'red', padding: '10px' }}>Content</div>;
        }
        """
        styles = adapter.extract_style_usage(Path("Box.tsx"), content)

        inline_styles = [s for s in styles if s.is_inline]
        assert len(inline_styles) >= 1


class TestVueAdapter:
    """Tests for Vue adapter."""

    @pytest.fixture
    def adapter(self) -> VueAdapter:
        """Create a Vue adapter."""
        return VueAdapter()

    def test_supported_extensions(self, adapter: VueAdapter):
        """Test supported extensions."""
        assert ".vue" in adapter.supported_extensions

    def test_can_handle_vue(self, adapter: VueAdapter):
        """Test can_handle for Vue files."""
        assert adapter.can_handle(Path("Button.vue"))
        assert not adapter.can_handle(Path("Button.tsx"))

    def test_extract_vue_component(self, adapter: VueAdapter):
        """Test extracting Vue component."""
        content = """
        <template>
            <div class="container">Hello</div>
        </template>
        <script>
        export default {
            name: 'MyComponent'
        }
        </script>
        """
        components = adapter.extract_components(Path("MyComponent.vue"), content)

        assert len(components) == 1
        assert components[0].name == "MyComponent"
        assert components[0].framework == "vue"

    def test_extract_vue_styles(self, adapter: VueAdapter):
        """Test extracting Vue styles."""
        content = """
        <template>
            <div class="container active">Content</div>
        </template>
        <style>
        .container { display: flex; }
        </style>
        """
        styles = adapter.extract_style_usage(Path("Test.vue"), content)

        # Should find class usage from template and rule from style
        class_names = []
        for s in styles:
            class_names.extend(s.class_names)
        assert "container" in class_names


class TestSvelteAdapter:
    """Tests for Svelte adapter."""

    @pytest.fixture
    def adapter(self) -> SvelteAdapter:
        """Create a Svelte adapter."""
        return SvelteAdapter()

    def test_supported_extensions(self, adapter: SvelteAdapter):
        """Test supported extensions."""
        assert ".svelte" in adapter.supported_extensions

    def test_extract_svelte_component(self, adapter: SvelteAdapter):
        """Test extracting Svelte component."""
        content = """
        <script>
            export let title;
        </script>
        <div class="container">{title}</div>
        """
        components = adapter.extract_components(Path("Card.svelte"), content)

        assert len(components) == 1
        assert components[0].name == "Card"
        assert components[0].framework == "svelte"
        assert "title" in components[0].props

    def test_extract_svelte_class_directive(self, adapter: SvelteAdapter):
        """Test extracting Svelte class directives."""
        content = """
        <div class:active={isActive}>Content</div>
        """
        styles = adapter.extract_style_usage(Path("Test.svelte"), content)

        class_names = []
        for s in styles:
            class_names.extend(s.class_names)
        assert "active" in class_names


class TestGenericAdapter:
    """Tests for Generic fallback adapter."""

    @pytest.fixture
    def adapter(self) -> GenericAdapter:
        """Create a Generic adapter."""
        return GenericAdapter()

    def test_can_handle_any_file(self, adapter: GenericAdapter):
        """Test that generic adapter handles any file."""
        assert adapter.can_handle(Path("anything.xyz"))
        assert adapter.can_handle(Path("file.html"))

    def test_extract_html_classes(self, adapter: GenericAdapter):
        """Test extracting classes from HTML."""
        content = """
        <div class="container flex">
            <span class="text-bold">Text</span>
        </div>
        """
        styles = adapter.extract_style_usage(Path("page.html"), content)

        class_names = []
        for s in styles:
            class_names.extend(s.class_names)
        assert "container" in class_names
        assert "flex" in class_names
        assert "text-bold" in class_names

    def test_extract_inline_styles(self, adapter: GenericAdapter):
        """Test extracting inline styles from HTML."""
        content = """
        <div style="color: red; padding: 10px;">Content</div>
        """
        styles = adapter.extract_style_usage(Path("page.html"), content)

        inline = [s for s in styles if s.is_inline]
        assert len(inline) >= 1
        assert inline[0].declarations.get("color") == "red"


class TestSourceCollector:
    """Tests for SourceCollector."""

    @pytest.fixture
    def collector(self) -> SourceCollector:
        """Create a source collector."""
        return SourceCollector()

    def test_get_adapter_tsx(self, collector: SourceCollector):
        """Test getting adapter for TSX files."""
        adapter = collector.get_adapter(Path("Button.tsx"))

        assert adapter is not None
        assert isinstance(adapter, ReactAdapter)

    def test_get_adapter_css(self, collector: SourceCollector):
        """Test getting adapter for CSS files."""
        adapter = collector.get_adapter(Path("styles.css"))

        assert adapter is not None
        assert isinstance(adapter, CSSAdapter)

    def test_get_adapter_vue(self, collector: SourceCollector):
        """Test getting adapter for Vue files."""
        adapter = collector.get_adapter(Path("App.vue"))

        assert adapter is not None
        assert isinstance(adapter, VueAdapter)

    def test_get_adapter_svelte(self, collector: SourceCollector):
        """Test getting adapter for Svelte files."""
        adapter = collector.get_adapter(Path("App.svelte"))

        assert adapter is not None
        assert isinstance(adapter, SvelteAdapter)

    def test_get_adapter_fallback(self, collector: SourceCollector):
        """Test fallback to generic adapter."""
        adapter = collector.get_adapter(Path("unknown.xyz"))

        assert adapter is not None
        assert isinstance(adapter, GenericAdapter)

    def test_list_adapters(self, collector: SourceCollector):
        """Test listing registered adapters."""
        adapters = collector.list_adapters()

        assert len(adapters) >= 5  # React, Vue, Svelte, CSS, Generic
        names = [a["name"] for a in adapters]
        assert "ReactAdapter" in names
        assert "VueAdapter" in names
        assert "CSSAdapter" in names

    def test_get_supported_extensions(self, collector: SourceCollector):
        """Test getting all supported extensions."""
        extensions = collector.get_supported_extensions()

        assert ".tsx" in extensions
        assert ".jsx" in extensions
        assert ".vue" in extensions
        assert ".svelte" in extensions
        assert ".css" in extensions
        assert ".scss" in extensions

    def test_extract_from_tsx(self, collector: SourceCollector):
        """Test extraction from TSX file."""
        content = """
        export function Button({ onClick }) {
            return <button className="btn" onClick={onClick}>Click</button>;
        }
        """
        result = collector.extract(Path("Button.tsx"), content)

        assert not result.has_errors
        assert len(result.components) >= 1 or len(result.styles) >= 1

    def test_extract_from_css(self, collector: SourceCollector):
        """Test extraction from CSS file."""
        content = """
        .btn { color: red; }
        .container { display: flex; }
        """
        result = collector.extract(Path("styles.css"), content)

        assert not result.has_errors
        assert len(result.styles) == 2
        assert len(result.components) == 0

    def test_register_custom_adapter(self, collector: SourceCollector):
        """Test registering a custom adapter."""

        class CustomAdapter(GenericAdapter):
            @property
            def name(self):
                return "CustomAdapter"

        collector.register(CustomAdapter())
        adapters = collector.list_adapters()

        names = [a["name"] for a in adapters]
        assert "CustomAdapter" in names

    def test_unregister_adapter(self, collector: SourceCollector):
        """Test unregistering an adapter."""
        initial_count = len(collector.list_adapters())

        result = collector.unregister("GenericAdapter")

        assert result is True
        assert len(collector.list_adapters()) == initial_count - 1
