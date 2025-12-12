"""Tests for lazy loading utilities."""

import threading
import time

import pytest

from claude_indexer.utils.lazy import (
    LazyModule,
    LazyProperty,
    lazy_init,
    lazy_property,
)


class TestLazyProperty:
    """Tests for lazy_property decorator."""

    def test_basic_lazy_loading(self):
        """Test basic lazy property initialization."""
        call_count = [0]

        class TestClass:
            @lazy_property
            def expensive(self) -> str:
                call_count[0] += 1
                return "computed"

        obj = TestClass()

        # Not computed yet
        assert call_count[0] == 0

        # First access computes value
        result = obj.expensive
        assert result == "computed"
        assert call_count[0] == 1

        # Second access returns cached value
        result2 = obj.expensive
        assert result2 == "computed"
        assert call_count[0] == 1  # Still 1

    def test_per_instance_caching(self):
        """Test that each instance has its own cached value."""
        class TestClass:
            def __init__(self, value):
                self._value = value

            @lazy_property
            def computed(self) -> str:
                return f"value_{self._value}"

        obj1 = TestClass(1)
        obj2 = TestClass(2)

        assert obj1.computed == "value_1"
        assert obj2.computed == "value_2"

    def test_set_property(self):
        """Test setting lazy property directly."""
        class TestClass:
            @lazy_property
            def value(self) -> str:
                return "original"

        obj = TestClass()
        obj.value = "modified"

        assert obj.value == "modified"

    def test_delete_property(self):
        """Test deleting lazy property resets cache."""
        call_count = [0]

        class TestClass:
            @lazy_property
            def value(self) -> int:
                call_count[0] += 1
                return call_count[0]

        obj = TestClass()

        assert obj.value == 1
        assert call_count[0] == 1

        del obj.value

        # Re-computing after delete
        assert obj.value == 2
        assert call_count[0] == 2

    def test_thread_safety(self):
        """Test thread-safe lazy initialization."""
        call_count = [0]
        call_lock = threading.Lock()

        class TestClass:
            @lazy_property
            def expensive(self) -> str:
                with call_lock:
                    call_count[0] += 1
                time.sleep(0.01)  # Simulate slow init
                return "result"

        obj = TestClass()
        results = []
        errors = []

        def access():
            try:
                results.append(obj.expensive)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=access) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should only compute once despite concurrent access
        assert call_count[0] == 1
        assert len(errors) == 0
        assert all(r == "result" for r in results)


class TestLazyInit:
    """Tests for lazy_init decorator."""

    def test_basic_caching(self):
        """Test basic function result caching."""
        call_count = [0]

        @lazy_init()
        def get_resource() -> str:
            call_count[0] += 1
            return "resource"

        # First call computes
        result1 = get_resource()
        assert result1 == "resource"
        assert call_count[0] == 1

        # Second call returns cached
        result2 = get_resource()
        assert result2 == "resource"
        assert call_count[0] == 1

    def test_argument_based_caching(self):
        """Test caching based on arguments."""
        call_count = [0]

        @lazy_init()
        def compute(x: int) -> int:
            call_count[0] += 1
            return x * 2

        assert compute(1) == 2
        assert compute(2) == 4
        assert call_count[0] == 2

        # Cached calls
        assert compute(1) == 2
        assert compute(2) == 4
        assert call_count[0] == 2

    def test_callback(self):
        """Test init callback."""
        callback_calls = []

        def callback(name: str, duration_ms: float):
            callback_calls.append((name, duration_ms))

        @lazy_init(init_callback=callback)
        def slow_init() -> str:
            time.sleep(0.01)
            return "done"

        result = slow_init()
        assert result == "done"
        assert len(callback_calls) == 1
        assert callback_calls[0][0] == "slow_init"
        assert callback_calls[0][1] >= 10  # At least 10ms

        # Second call should not trigger callback
        slow_init()
        assert len(callback_calls) == 1

    def test_clear_cache(self):
        """Test cache clearing."""
        call_count = [0]

        @lazy_init()
        def get_value() -> int:
            call_count[0] += 1
            return call_count[0]

        assert get_value() == 1
        assert get_value() == 1  # Cached

        get_value.clear_cache()

        assert get_value() == 2  # Recomputed
        assert call_count[0] == 2

    def test_thread_safety(self):
        """Test thread-safe lazy init."""
        call_count = [0]
        call_lock = threading.Lock()

        @lazy_init()
        def get_singleton() -> str:
            with call_lock:
                call_count[0] += 1
            time.sleep(0.01)
            return "singleton"

        results = []

        def access():
            results.append(get_singleton())

        threads = [threading.Thread(target=access) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert call_count[0] == 1
        assert all(r == "singleton" for r in results)


class TestLazyModule:
    """Tests for LazyModule class."""

    def test_basic_lazy_import(self):
        """Test lazy module import."""
        # json is in stdlib, should always work
        lazy_json = LazyModule("json")

        # Not loaded yet
        assert lazy_json._module is None

        # Access triggers load
        result = lazy_json.dumps({"test": 1})
        assert result == '{"test": 1}'

        # Now loaded
        assert lazy_json._module is not None

    def test_repr(self):
        """Test repr before and after loading."""
        lazy_json = LazyModule("json")

        assert "loaded=False" in repr(lazy_json)

        lazy_json.dumps({})

        assert "loaded=True" in repr(lazy_json)

    def test_attribute_access(self):
        """Test accessing module attributes."""
        lazy_json = LazyModule("json")

        # Access attribute
        encoder = lazy_json.JSONEncoder
        assert encoder is not None

    def test_thread_safety(self):
        """Test thread-safe module loading."""
        lazy_modules = [LazyModule("json") for _ in range(5)]
        load_counts = [0]
        errors = []

        def use_module(lazy_mod):
            try:
                lazy_mod.dumps({})
            except Exception as e:
                errors.append(e)

        threads = []
        for mod in lazy_modules:
            for _ in range(3):
                t = threading.Thread(target=use_module, args=(mod,))
                threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
