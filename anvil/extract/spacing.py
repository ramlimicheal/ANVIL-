"""
ANVIL Spacing Extractor — Derives spacing grid from structural layout.
Measures gaps between components, finds base unit via histogram peak analysis.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from .structure import StructuralTree, LayoutNode


@dataclass
class ExtractedSpacing:
    """Complete extracted spacing system."""
    base: int                    # base unit in px (e.g., 4)
    scale: List[int]             # spacing scale (e.g., [4,8,12,16,24,32,48,64,96])
    horizontal_gaps: List[int]   # raw horizontal gap measurements
    vertical_gaps: List[int]     # raw vertical gap measurements
    padding_values: List[int]    # detected internal padding values
    dominant_gaps: List[int]     # most common gap values (histogram peaks)

    def to_dict(self) -> dict:
        return {
            "spacing_base": f"{self.base}px",
            "scale": self.scale,
            "scale_css": [f"{v}px" for v in self.scale],
            "dominant_gaps": self.dominant_gaps,
        }


def extract_spacing(tree: StructuralTree) -> ExtractedSpacing:
    """Extract spacing system from a structural tree.

    Args:
        tree: StructuralTree from structure.py

    Returns:
        ExtractedSpacing with base unit and scale
    """
    h_gaps = []
    v_gaps = []
    paddings = []

    _collect_gaps(tree.root, h_gaps, v_gaps, paddings)

    # Find dominant gap values via histogram
    all_gaps = [g for g in h_gaps + v_gaps if 1 < g < 200]
    dominant = _find_dominant_values(all_gaps)

    # Detect base unit
    base = _detect_base(dominant)

    # Generate scale from base
    scale = _generate_scale(base)

    return ExtractedSpacing(
        base=base,
        scale=scale,
        horizontal_gaps=h_gaps,
        vertical_gaps=v_gaps,
        padding_values=paddings,
        dominant_gaps=dominant,
    )


def _collect_gaps(
    node: LayoutNode,
    h_gaps: List[int],
    v_gaps: List[int],
    paddings: List[int],
):
    """Recursively collect gap and padding measurements from the tree."""
    if not node.children:
        return

    kids = node.children

    # Sort by position for gap measurement
    h_sorted = sorted(kids, key=lambda n: n.x)
    v_sorted = sorted(kids, key=lambda n: n.y)

    # Horizontal gaps between siblings
    for i in range(len(h_sorted) - 1):
        a = h_sorted[i]
        b = h_sorted[i + 1]
        # Only measure gap if they're roughly on the same row
        if abs(a.y - b.y) < max(a.h, b.h) * 0.5:
            gap = b.x - (a.x + a.w)
            if 0 < gap < 200:
                h_gaps.append(gap)

    # Vertical gaps between siblings
    for i in range(len(v_sorted) - 1):
        a = v_sorted[i]
        b = v_sorted[i + 1]
        # Only measure gap if they're roughly in the same column
        if abs(a.x - b.x) < max(a.w, b.w) * 0.5:
            gap = b.y - (a.y + a.h)
            if 0 < gap < 200:
                v_gaps.append(gap)

    # Internal padding: distance from container edge to first/last child
    if kids:
        first = min(kids, key=lambda n: n.y)
        last = max(kids, key=lambda n: n.y + n.h)
        leftmost = min(kids, key=lambda n: n.x)
        rightmost = max(kids, key=lambda n: n.x + n.w)

        top_pad = first.y - node.y
        bottom_pad = (node.y + node.h) - (last.y + last.h)
        left_pad = leftmost.x - node.x
        right_pad = (node.x + node.w) - (rightmost.x + rightmost.w)

        for pad in [top_pad, bottom_pad, left_pad, right_pad]:
            if 2 < pad < 100:
                paddings.append(pad)

    # Recurse
    for child in kids:
        _collect_gaps(child, h_gaps, v_gaps, paddings)


def _find_dominant_values(gaps: List[int], bin_width: int = 2) -> List[int]:
    """Find most common gap values using histogram peak detection."""
    if not gaps:
        return [4, 8, 16]  # sensible defaults

    # Build histogram
    max_val = max(gaps) + 1
    bins = [0] * (max_val // bin_width + 1)
    for g in gaps:
        idx = g // bin_width
        if idx < len(bins):
            bins[idx] += 1

    # Find peaks (bins with count above mean)
    if not bins:
        return [4, 8, 16]

    mean_count = sum(bins) / len(bins)
    peaks = []
    for i, count in enumerate(bins):
        if count > mean_count * 1.5 and count >= 2:
            value = i * bin_width + bin_width // 2
            if value > 0:
                peaks.append(value)

    if not peaks:
        # Fall back to most common raw values
        from collections import Counter
        counter = Counter(gaps)
        peaks = [val for val, _ in counter.most_common(5) if val > 0]

    # Round peaks to nearest common spacing value
    rounded = []
    for p in peaks:
        # Snap to nearest multiple of 2
        snapped = round(p / 2) * 2
        if snapped > 0 and snapped not in rounded:
            rounded.append(snapped)

    return sorted(rounded)[:8]


def _detect_base(dominant: List[int]) -> int:
    """Detect the spacing base unit from dominant gap values."""
    if not dominant:
        return 4

    # Try common bases: 4, 8, 6, 5
    for base in [4, 8, 6, 5]:
        # Check how many dominant values are multiples of this base
        multiples = sum(1 for d in dominant if d % base == 0 or abs(d % base) <= 1)
        if multiples >= len(dominant) * 0.6:
            return base

    # GCD approach
    values = [d for d in dominant if d > 0]
    if len(values) >= 2:
        result = values[0]
        for v in values[1:]:
            result = math.gcd(result, v)
        if 2 <= result <= 8:
            return result

    return 4  # safe default


def _generate_scale(base: int) -> List[int]:
    """Generate a spacing scale from the base unit."""
    multipliers = [1, 2, 3, 4, 6, 8, 10, 12, 16, 24]
    scale = sorted(set(base * m for m in multipliers))
    return [s for s in scale if s <= 200]
