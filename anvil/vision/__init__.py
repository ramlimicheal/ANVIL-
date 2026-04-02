"""ANVIL Vision — Pixel-level visual fidelity verification."""


def __getattr__(name):
    """Lazy-import to avoid crashing when opencv/scipy are not installed."""
    if name == "VisualComparator":
        from .compare import VisualComparator
        return VisualComparator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
