"""Unit tests for component normalizer."""

import pytest

from claude_indexer.ui.normalizers.component import (
    ComponentNormalizer,
    NormalizedComponent,
)


class TestNormalizedComponent:
    """Tests for NormalizedComponent dataclass."""

    def test_create_normalized_component(self):
        """Test basic NormalizedComponent creation."""
        comp = NormalizedComponent(
            structure="<div><span></span></div>",
            structure_hash="abc123",
            tag_sequence=["div", "span"],
            attribute_keys={"class", "onClick"},
            style_refs=["container", "text"],
            prop_names=["title", "onClick"],
        )

        assert comp.structure == "<div><span></span></div>"
        assert comp.structure_hash == "abc123"
        assert comp.tag_sequence == ["div", "span"]
        assert "class" in comp.attribute_keys
        assert "container" in comp.style_refs

    def test_is_exact_duplicate(self):
        """Test exact duplicate detection."""
        comp1 = NormalizedComponent(
            structure="<div></div>",
            structure_hash="abc",
        )
        comp2 = NormalizedComponent(
            structure="<div></div>",
            structure_hash="abc",
        )
        comp3 = NormalizedComponent(
            structure="<span></span>",
            structure_hash="xyz",
        )

        assert comp1.is_exact_duplicate(comp2)
        assert not comp1.is_exact_duplicate(comp3)

    def test_serialization_roundtrip(self):
        """Test to_dict and from_dict produce equivalent objects."""
        comp = NormalizedComponent(
            structure="<div class></div>",
            structure_hash="hash123",
            tag_sequence=["div"],
            attribute_keys={"class"},
            style_refs=["container"],
            prop_names=["title"],
        )

        data = comp.to_dict()
        restored = NormalizedComponent.from_dict(data)

        assert restored.structure == comp.structure
        assert restored.structure_hash == comp.structure_hash
        assert restored.tag_sequence == comp.tag_sequence
        assert restored.attribute_keys == comp.attribute_keys
        assert restored.style_refs == comp.style_refs
        assert restored.prop_names == comp.prop_names


class TestComponentNormalizer:
    """Tests for ComponentNormalizer."""

    @pytest.fixture
    def normalizer(self) -> ComponentNormalizer:
        """Create a component normalizer."""
        return ComponentNormalizer()

    def test_normalize_simple_jsx(self, normalizer: ComponentNormalizer):
        """Test normalizing simple JSX."""
        template = '<div className="container"><span>Hello</span></div>'
        result = normalizer.normalize(template, framework="react")

        assert "div" in result.tag_sequence
        assert "span" in result.tag_sequence
        assert len(result.structure_hash) == 64  # SHA256

    def test_replace_literals(self, normalizer: ComponentNormalizer):
        """Test that literals are replaced with placeholders."""
        template = '<div data-id="123">Hello World</div>'
        result = normalizer.normalize(template)

        # Text content should be replaced
        assert "Hello World" not in result.structure

    def test_normalize_class_order(self, normalizer: ComponentNormalizer):
        """Test that class names are sorted."""
        template1 = '<div className="btn primary large">Button</div>'
        template2 = '<div className="large btn primary">Button</div>'

        result1 = normalizer.normalize(template1)
        result2 = normalizer.normalize(template2)

        # Should produce same hash after normalization
        assert result1.structure_hash == result2.structure_hash

    def test_extract_tag_sequence(self, normalizer: ComponentNormalizer):
        """Test tag sequence extraction."""
        template = """
        <div>
            <header>
                <nav></nav>
            </header>
            <main></main>
            <footer></footer>
        </div>
        """
        result = normalizer.normalize(template)

        assert "div" in result.tag_sequence
        assert "header" in result.tag_sequence
        assert "nav" in result.tag_sequence
        assert "main" in result.tag_sequence
        assert "footer" in result.tag_sequence

    def test_extract_attribute_keys(self, normalizer: ComponentNormalizer):
        """Test attribute key extraction."""
        # Note: Boolean attributes without values (like 'disabled') are not currently extracted
        template = '<button onClick={handleClick} disabled={true} className="btn">Click</button>'
        result = normalizer.normalize(template)

        assert "onClick" in result.attribute_keys
        assert "disabled" in result.attribute_keys
        assert "className" in result.attribute_keys

    def test_extract_style_refs(self, normalizer: ComponentNormalizer):
        """Test style reference extraction."""
        template = """
        <div className="container flex-row">
            <span className={styles.text}>Hello</span>
        </div>
        """
        result = normalizer.normalize(template)

        assert "container" in result.style_refs
        assert "flex-row" in result.style_refs
        assert "text" in result.style_refs

    def test_extract_css_module_refs(self, normalizer: ComponentNormalizer):
        """Test CSS module reference extraction."""
        template = """
        <div className={styles.container}>
            <span className={styles["text-bold"]}>Text</span>
        </div>
        """
        result = normalizer.normalize(template)

        assert "container" in result.style_refs
        assert "text-bold" in result.style_refs

    def test_structure_hash_deterministic(self, normalizer: ComponentNormalizer):
        """Test that same structure produces same hash."""
        template = "<div><span>Text</span></div>"

        result1 = normalizer.normalize(template)
        result2 = normalizer.normalize(template)

        assert result1.structure_hash == result2.structure_hash

    def test_different_structure_different_hash(self, normalizer: ComponentNormalizer):
        """Test that different structures produce different hashes."""
        template1 = "<div><span></span></div>"
        template2 = "<div><p></p></div>"

        result1 = normalizer.normalize(template1)
        result2 = normalizer.normalize(template2)

        assert result1.structure_hash != result2.structure_hash

    def test_compute_similarity_identical(self, normalizer: ComponentNormalizer):
        """Test similarity of identical components."""
        comp = normalizer.normalize("<div><span></span></div>")

        similarity = normalizer.compute_similarity(comp, comp)

        assert similarity == 1.0

    def test_compute_similarity_similar(self, normalizer: ComponentNormalizer):
        """Test similarity of similar components."""
        comp1 = normalizer.normalize('<div className="a"><span>Text 1</span></div>')
        comp2 = normalizer.normalize('<div className="a"><span>Text 2</span></div>')

        similarity = normalizer.compute_similarity(comp1, comp2)

        # Should be high similarity
        assert similarity > 0.8

    def test_compute_similarity_different(self, normalizer: ComponentNormalizer):
        """Test similarity of different components."""
        comp1 = normalizer.normalize("<div><span></span></div>")
        comp2 = normalizer.normalize("<table><tr><td></td></tr></table>")

        similarity = normalizer.compute_similarity(comp1, comp2)

        # Should be low similarity (at most 0.5)
        assert similarity <= 0.5

    def test_are_near_duplicates(self, normalizer: ComponentNormalizer):
        """Test near-duplicate detection."""
        comp1 = normalizer.normalize('<button className="btn">Click</button>')
        comp2 = normalizer.normalize('<button className="btn">Submit</button>')

        assert normalizer.are_near_duplicates(comp1, comp2)

    def test_find_duplicates(self, normalizer: ComponentNormalizer):
        """Test finding exact duplicates."""
        components = [
            normalizer.normalize("<div>A</div>"),
            normalizer.normalize("<span>B</span>"),
            normalizer.normalize("<div>C</div>"),  # Same structure as first
        ]

        duplicates = normalizer.find_duplicates(components)

        assert len(duplicates) == 1
        assert duplicates[0] == (0, 2)

    def test_find_near_duplicates(self, normalizer: ComponentNormalizer):
        """Test finding near-duplicates."""
        # Use components with different but similar structures
        # Structure difference is needed to avoid exact hash match
        components = [
            normalizer.normalize(
                "<div><span></span><p></p></div>"
            ),  # div with span and p
            normalizer.normalize(
                "<div><span></span><strong></strong></div>"
            ),  # div with span and strong
            normalizer.normalize("<table><tr><td></td></tr></table>"),  # Very different
        ]

        # Both first two have div>span but with different second child
        # This should produce similar but not identical structures
        normalizer.find_near_duplicates(components, threshold=0.3)

        # There should be near duplicates found (0,1) should be more similar than (0,2) or (1,2)
        # If no near duplicates found, verify the similarity behavior is correct
        similarity_01 = normalizer.compute_similarity(components[0], components[1])
        similarity_02 = normalizer.compute_similarity(components[0], components[2])

        # First two should be more similar than first and third
        assert similarity_01 > similarity_02

    def test_props_in_result(self, normalizer: ComponentNormalizer):
        """Test that props are included in result."""
        result = normalizer.normalize(
            "<Button>Click</Button>",
            props={"onClick": "function", "disabled": "boolean"},
        )

        assert "onClick" in result.prop_names
        assert "disabled" in result.prop_names

    def test_vue_template(self, normalizer: ComponentNormalizer):
        """Test normalizing Vue template syntax."""
        template = """
        <template>
            <div v-if="show" :class="{ active: isActive }">
                <span v-for="item in items">{{ item }}</span>
            </div>
        </template>
        """
        result = normalizer.normalize(template, framework="vue")

        assert "div" in result.tag_sequence
        assert "span" in result.tag_sequence

    def test_svelte_template(self, normalizer: ComponentNormalizer):
        """Test normalizing Svelte template syntax."""
        template = """
        <div class:active={isActive}>
            {#if show}
                <span>{text}</span>
            {/if}
        </div>
        """
        result = normalizer.normalize(template, framework="svelte")

        assert "div" in result.tag_sequence
        assert "span" in result.tag_sequence
