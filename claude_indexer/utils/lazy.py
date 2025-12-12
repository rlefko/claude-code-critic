"""Lazy loading utilities for expensive operations.

This module provides thread-safe lazy initialization decorators and
descriptors for deferring expensive component initialization until
first access.

Example usage:
    class Parser:
        @lazy_property
        def grammar(self) -> Grammar:
            return load_grammar()  # Only called once, cached

    @lazy_init()
    def get_embedder() -> Embedder:
        return create_embedder()  # Cached across calls
"""

import functools
import time
from threading import Lock
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


class LazyProperty(Generic[T]):
    """Descriptor for lazy property initialization with thread-safety.

    This descriptor delays the initialization of a property until first access.
    The value is computed once and cached for subsequent accesses.

    Thread-safe: Uses double-checked locking pattern to ensure the
    property is only initialized once even in concurrent scenarios.

    Usage:
        class MyClass:
            @lazy_property
            def expensive_component(self) -> ExpensiveComponent:
                return ExpensiveComponent()

    Attributes:
        func: The wrapped function that computes the property value.
        attr_name: The name of the cached attribute on the instance.
        lock: Threading lock for thread-safe initialization.
    """

    def __init__(self, func: Callable[[Any], T]):
        """Initialize the lazy property descriptor.

        Args:
            func: Function to call to compute the property value.
        """
        self.func = func
        self.attr_name = f"_lazy_{func.__name__}"
        self.lock = Lock()
        functools.update_wrapper(self, func)

    def __get__(self, obj: Any, objtype: type | None = None) -> T:
        """Get the property value, initializing if needed.

        Args:
            obj: The instance the property is accessed on.
            objtype: The type of the instance.

        Returns:
            The cached or newly computed property value.
        """
        if obj is None:
            return self  # type: ignore

        # Fast path: check if already initialized (no lock needed)
        cached = getattr(obj, self.attr_name, None)
        if cached is not None:
            return cached

        # Slow path: thread-safe initialization
        with self.lock:
            # Double-check after acquiring lock
            cached = getattr(obj, self.attr_name, None)
            if cached is not None:
                return cached

            value = self.func(obj)
            setattr(obj, self.attr_name, value)
            return value

    def __set__(self, obj: Any, value: T) -> None:
        """Set the property value directly.

        Args:
            obj: The instance to set the value on.
            value: The value to set.
        """
        setattr(obj, self.attr_name, value)

    def __delete__(self, obj: Any) -> None:
        """Delete the cached property value.

        Args:
            obj: The instance to delete the value from.
        """
        if hasattr(obj, self.attr_name):
            delattr(obj, self.attr_name)


def lazy_property(func: Callable[[Any], T]) -> LazyProperty[T]:
    """Decorator for lazy property initialization.

    Thread-safe lazy initialization of expensive properties.
    The property is only computed once and cached.

    Example:
        class Parser:
            @lazy_property
            def grammar(self) -> Grammar:
                return load_grammar()  # Only called once

    Args:
        func: The function to decorate.

    Returns:
        A LazyProperty descriptor wrapping the function.
    """
    return LazyProperty(func)


def lazy_init(
    init_callback: Callable[[str, float], None] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for lazy function initialization with timing callback.

    Caches the result of the decorated function. Subsequent calls with
    the same arguments return the cached value. Optionally reports
    initialization timing via callback.

    Args:
        init_callback: Optional callback(name, duration_ms) called after
                      first initialization. Useful for logging or metrics.

    Returns:
        Decorator function.

    Example:
        @lazy_init(init_callback=lambda n, d: print(f"{n} init: {d}ms"))
        def get_embedder() -> Embedder:
            return create_embedder()  # Expensive, cached

        embedder1 = get_embedder()  # Calls create_embedder()
        embedder2 = get_embedder()  # Returns cached value
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        cache: dict[str, T] = {}
        lock = Lock()

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Create cache key from arguments
            key = f"{args}:{sorted(kwargs.items())}"

            # Fast path: check cache without lock
            if key in cache:
                return cache[key]

            # Slow path: thread-safe initialization
            with lock:
                # Double-check after acquiring lock
                if key in cache:
                    return cache[key]

                start = time.perf_counter()
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start) * 1000

                cache[key] = result

                if init_callback:
                    init_callback(func.__name__, duration_ms)

                return result

        def clear_cache() -> None:
            """Clear all cached values."""
            with lock:
                cache.clear()

        wrapper.clear_cache = clear_cache  # type: ignore
        return wrapper

    return decorator


class LazyModule:
    """Lazy module loader for deferring expensive imports.

    Delays importing a module until first attribute access.
    Useful for optional dependencies or slow-to-import modules.

    Example:
        # Instead of: import pandas as pd
        pd = LazyModule("pandas")

        # pandas only imported when first used
        df = pd.DataFrame(...)

    Attributes:
        module_name: The name of the module to lazily import.
    """

    def __init__(self, module_name: str):
        """Initialize the lazy module loader.

        Args:
            module_name: The name of the module to import.
        """
        self._module_name = module_name
        self._module: Any = None
        self._lock = Lock()

    def _load(self) -> Any:
        """Load the module if not already loaded.

        Returns:
            The imported module.
        """
        if self._module is None:
            with self._lock:
                if self._module is None:
                    import importlib
                    self._module = importlib.import_module(self._module_name)
        return self._module

    def __getattr__(self, name: str) -> Any:
        """Get an attribute from the lazily loaded module.

        Args:
            name: The attribute name to access.

        Returns:
            The attribute from the module.
        """
        return getattr(self._load(), name)

    def __repr__(self) -> str:
        """Return a string representation."""
        loaded = self._module is not None
        return f"<LazyModule '{self._module_name}' loaded={loaded}>"


__all__ = ["lazy_property", "lazy_init", "LazyProperty", "LazyModule"]
