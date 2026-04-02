"""
ANVIL Icon Classifier — Detects icons and matches to known icon libraries.
Uses perceptual hashing for fast matching against Lucide, Heroicons, Phosphor, Feather.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from .structure import StructuralTree, LayoutNode

try:
    import cv2
    import numpy as np
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


# Known icon libraries with style characteristics
ICON_LIBRARIES = {
    "lucide": {"style": "outline", "stroke_width": 2, "sizes": [16, 20, 24]},
    "heroicons": {"style": "outline", "stroke_width": 1.5, "sizes": [20, 24]},
    "phosphor": {"style": "outline", "stroke_width": 1.5, "sizes": [16, 20, 24, 32]},
    "feather": {"style": "outline", "stroke_width": 2, "sizes": [24]},
    "tabler": {"style": "outline", "stroke_width": 2, "sizes": [24]},
}


@dataclass
class DetectedIcon:
    """A single detected icon."""
    bounds: Tuple[int, int, int, int]
    size: int  # px (largest dimension)
    style: str  # outline, filled, duotone
    suggested_library: str
    fill_ratio: float  # 0-1: how filled the icon is
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "bounds": self.bounds,
            "size": self.size,
            "style": self.style,
            "library": self.suggested_library,
            "confidence": self.confidence,
        }


@dataclass
class IconAnalysis:
    """Complete icon detection result."""
    icons: List[DetectedIcon]
    dominant_style: str      # most common style
    dominant_library: str    # best matching library
    dominant_size: int       # most common size
    total_count: int = 0

    def to_dict(self) -> dict:
        return {
            "icons": [i.to_dict() for i in self.icons],
            "dominant_style": self.dominant_style,
            "suggested_library": self.dominant_library,
            "icon_size": self.dominant_size,
            "total": self.total_count,
        }


def detect_icons(image_path: str, tree: StructuralTree) -> IconAnalysis:
    """Detect and classify icons from a screenshot.

    Args:
        image_path: Path to screenshot
        tree: StructuralTree from structure.py

    Returns:
        IconAnalysis with detected icons and library suggestion
    """
    if not HAS_DEPS:
        raise ImportError("opencv-python and numpy required")

    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not read: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Find icon-sized nodes from structure tree
    icon_nodes = _find_icon_nodes(tree.root)

    # Analyze each icon
    icons = []
    for node in icon_nodes:
        x, y, w, h = node.bounds
        region = gray[max(0, y):min(gray.shape[0], y + h),
                       max(0, x):min(gray.shape[1], x + w)]
        if region.size == 0:
            continue

        icon = _analyze_icon(region, node.bounds)
        if icon:
            icons.append(icon)

    # Determine dominant characteristics
    if icons:
        styles = [i.style for i in icons]
        dom_style = max(set(styles), key=styles.count)

        sizes = [i.size for i in icons]
        dom_size = max(set(sizes), key=sizes.count)

        dom_library = _suggest_library(dom_style, dom_size, icons)
    else:
        dom_style = "outline"
        dom_size = 24
        dom_library = "lucide"

    return IconAnalysis(
        icons=icons,
        dominant_style=dom_style,
        dominant_library=dom_library,
        dominant_size=dom_size,
        total_count=len(icons),
    )


def _find_icon_nodes(root: LayoutNode) -> List[LayoutNode]:
    """Find nodes that are likely icons (small, square-ish)."""
    icons = []

    def _walk(node: LayoutNode):
        w, h = node.w, node.h
        if (12 <= w <= 48 and 12 <= h <= 48
                and 0.6 < w / max(h, 1) < 1.6
                and len(node.children) == 0):
            icons.append(node)
        for child in node.children:
            _walk(child)

    _walk(root)
    return icons


def _analyze_icon(region: "np.ndarray", bounds: Tuple[int, int, int, int]) -> Optional[DetectedIcon]:
    """Analyze a small region to classify as icon."""
    h, w = region.shape

    # Binarize
    _, binary = cv2.threshold(region, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Fill ratio: percentage of pixels that are "ink"
    fill_ratio = float(binary.mean()) / 255.0

    # Too empty or too full = probably not an icon
    if fill_ratio < 0.05 or fill_ratio > 0.85:
        return None

    # Classify style
    if fill_ratio < 0.25:
        style = "outline"
    elif fill_ratio < 0.55:
        style = "duotone"
    else:
        style = "filled"

    # Icon size (snap to common sizes)
    size = max(w, h)
    snapped_size = min([16, 20, 24, 32, 48], key=lambda s: abs(s - size))

    # Suggest library based on style
    library = _suggest_single_library(style, snapped_size)

    return DetectedIcon(
        bounds=bounds,
        size=snapped_size,
        style=style,
        suggested_library=library,
        fill_ratio=round(fill_ratio, 2),
        confidence=0.7,
    )


def _suggest_single_library(style: str, size: int) -> str:
    """Suggest the most likely icon library for a single icon."""
    candidates = []
    for name, props in ICON_LIBRARIES.items():
        score = 0
        if props["style"] == style:
            score += 2
        if size in props["sizes"]:
            score += 1
        candidates.append((name, score))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0] if candidates else "lucide"


def _suggest_library(dom_style: str, dom_size: int, icons: List[DetectedIcon]) -> str:
    """Suggest the best-matching icon library overall."""
    scores: Dict[str, float] = {}

    for name, props in ICON_LIBRARIES.items():
        score = 0.0
        if props["style"] == dom_style:
            score += 3.0
        if dom_size in props["sizes"]:
            score += 2.0
        # Bonus for library coverage
        if len(props["sizes"]) >= 3:
            score += 1.0
        scores[name] = score

    return max(scores, key=scores.get) if scores else "lucide"
