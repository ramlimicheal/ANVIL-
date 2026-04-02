"""
ANVIL Typography Extractor — Detects font classification, type scale, and weights.
Classifies fonts into serif/sans-serif/monospace/decorative and suggests popular matches.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

try:
    import cv2
    import numpy as np
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


# Font suggestion mappings: classification → popular fonts
FONT_SUGGESTIONS = {
    "sans-serif": [
        ("Inter", "system-ui", "sans-serif"),
        ("SF Pro Display", "-apple-system", "BlinkMacSystemFont", "sans-serif"),
        ("Geist", "system-ui", "sans-serif"),
        ("Plus Jakarta Sans", "system-ui", "sans-serif"),
    ],
    "serif": [
        ("Playfair Display", "Georgia", "serif"),
        ("Merriweather", "Georgia", "serif"),
        ("Lora", "Georgia", "serif"),
    ],
    "monospace": [
        ("JetBrains Mono", "Fira Code", "monospace"),
        ("SF Mono", "Menlo", "Monaco", "monospace"),
        ("Fira Code", "monospace"),
    ],
    "decorative": [
        ("Outfit", "system-ui", "sans-serif"),
        ("Space Grotesk", "system-ui", "sans-serif"),
    ],
}

# Common type scale ratios
SCALE_RATIOS = {
    1.125: "Major Second",
    1.200: "Minor Third",
    1.250: "Major Third",
    1.333: "Perfect Fourth",
    1.414: "Augmented Fourth",
    1.500: "Perfect Fifth",
    1.618: "Golden Ratio",
}


@dataclass
class TextRegion:
    """A detected text region with measurements."""
    bounds: Tuple[int, int, int, int]  # x, y, w, h
    height: int  # text height in px
    estimated_weight: int  # 300-900
    is_heading: bool = False


@dataclass
class ExtractedTypography:
    """Complete extracted typography system."""
    classification: str          # sans-serif, serif, monospace, decorative
    suggested_fonts: Tuple[str, ...]
    scale: List[int]             # type scale in px (e.g., [12, 14, 16, 20, 24, 32])
    scale_ratio: float           # ratio between steps (e.g., 1.25)
    scale_name: str              # e.g., "Major Third"
    weights: List[str]           # detected weights (e.g., ["400", "500", "600", "700"])
    base_size: int               # most common text size
    heading_sizes: List[int]     # sizes classified as headings
    body_sizes: List[int]        # sizes classified as body text
    mono_suggested: Tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "family_sans": ", ".join(self.suggested_fonts),
            "family_mono": ", ".join(self.mono_suggested),
            "scale": self.scale,
            "scale_ratio": self.scale_ratio,
            "scale_name": self.scale_name,
            "base_size": f"{self.base_size}px",
            "weights": {f"weight_{self._weight_name(w)}": w for w in self.weights},
        }

    @staticmethod
    def _weight_name(w: str) -> str:
        names = {"300": "light", "400": "regular", "500": "medium",
                 "600": "semibold", "700": "bold", "800": "extrabold"}
        return names.get(w, f"w{w}")


def extract_typography(image_path: str) -> ExtractedTypography:
    """Extract typography system from a screenshot.

    Args:
        image_path: Path to screenshot

    Returns:
        ExtractedTypography with font classification, scale, and weights
    """
    if not HAS_DEPS:
        raise ImportError("opencv-python and numpy required")

    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not read: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # Detect text regions
    text_regions = _detect_text_regions(gray, w, h)

    # Extract text heights and cluster into size groups
    heights = [r.height for r in text_regions if r.height > 0]
    size_groups = _cluster_sizes(heights)

    # Derive type scale
    scale, ratio, ratio_name = _derive_scale(size_groups)

    # Classify font type
    classification = _classify_font(gray, text_regions)

    # Detect weights
    weights = _detect_weights(gray, text_regions)

    # Suggest fonts
    suggested = FONT_SUGGESTIONS.get(classification, FONT_SUGGESTIONS["sans-serif"])[0]
    mono = FONT_SUGGESTIONS["monospace"][0]

    # Base size = most common
    base_size = _most_common_size(heights) if heights else 16

    # Split heading vs body
    heading_sizes = [s for s in scale if s > base_size * 1.3]
    body_sizes = [s for s in scale if s <= base_size * 1.3]

    return ExtractedTypography(
        classification=classification,
        suggested_fonts=suggested,
        scale=scale,
        scale_ratio=ratio,
        scale_name=ratio_name,
        weights=weights,
        base_size=base_size,
        heading_sizes=heading_sizes,
        body_sizes=body_sizes,
        mono_suggested=mono,
    )


def _detect_text_regions(gray: "np.ndarray", w: int, h: int) -> List[TextRegion]:
    """Detect text regions using morphological operations."""
    # Binarize
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Dilate horizontally to connect text characters into lines
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
    dilated = cv2.dilate(binary, kernel_h, iterations=2)

    # Then dilate slightly vertically to merge close lines
    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3))
    dilated = cv2.dilate(dilated, kernel_v, iterations=1)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    regions = []
    for contour in contours:
        x, y, rw, rh = cv2.boundingRect(contour)

        # Filter: text lines are wider than tall, reasonable size
        if rw < 20 or rh < 6 or rh > 80 or rw < rh:
            continue
        if rw * rh < 100:
            continue

        # Estimate weight from stroke thickness
        region = binary[y:y + rh, x:x + rw]
        weight = _estimate_weight(region, rh)

        is_heading = rh > 20

        regions.append(TextRegion(
            bounds=(x, y, rw, rh),
            height=rh,
            estimated_weight=weight,
            is_heading=is_heading,
        ))

    return regions


def _estimate_weight(binary_region: "np.ndarray", text_height: int) -> int:
    """Estimate font weight from stroke thickness analysis."""
    if binary_region.size == 0:
        return 400

    # Ratio of white pixels (text) to total
    fill_ratio = binary_region.mean() / 255.0

    # Normalize by text height (larger text naturally has thicker strokes)
    normalized = fill_ratio / max(math.sqrt(text_height / 16.0), 0.5)

    if normalized > 0.6:
        return 700  # bold
    elif normalized > 0.5:
        return 600  # semibold
    elif normalized > 0.4:
        return 500  # medium
    elif normalized > 0.25:
        return 400  # regular
    else:
        return 300  # light


def _cluster_sizes(heights: List[int], tolerance: int = 3) -> List[int]:
    """Cluster text heights into distinct size groups."""
    if not heights:
        return [14, 16, 20, 24]

    # Sort and group nearby values
    sorted_h = sorted(set(heights))
    groups = []
    current_group = [sorted_h[0]]

    for h in sorted_h[1:]:
        if h - current_group[-1] <= tolerance:
            current_group.append(h)
        else:
            groups.append(current_group)
            current_group = [h]
    groups.append(current_group)

    # Representative value for each group (median)
    representatives = []
    for g in groups:
        rep = sorted(g)[len(g) // 2]
        # Round to even numbers
        rep = round(rep / 2) * 2
        if rep > 0 and rep not in representatives:
            representatives.append(rep)

    return sorted(representatives) if representatives else [14, 16, 20, 24]


def _derive_scale(sizes: List[int]) -> Tuple[List[int], float, str]:
    """Derive the type scale ratio from detected sizes."""
    if len(sizes) < 2:
        return sizes or [14, 16, 20, 24], 1.25, "Major Third"

    # Compute ratios between consecutive sizes
    ratios = []
    for i in range(len(sizes) - 1):
        if sizes[i] > 0:
            r = sizes[i + 1] / sizes[i]
            if 1.05 < r < 2.0:
                ratios.append(r)

    if not ratios:
        return sizes, 1.25, "Major Third"

    avg_ratio = sum(ratios) / len(ratios)

    # Find closest named ratio
    best_name = "Custom"
    best_dist = float("inf")
    best_ratio = avg_ratio
    for known_ratio, name in SCALE_RATIOS.items():
        dist = abs(avg_ratio - known_ratio)
        if dist < best_dist:
            best_dist = dist
            best_name = name
            best_ratio = known_ratio

    # If close enough, snap to known ratio
    if best_dist < 0.05:
        avg_ratio = best_ratio
    else:
        best_name = f"Custom ({avg_ratio:.3f})"

    return sizes, round(avg_ratio, 3), best_name


def _classify_font(gray: "np.ndarray", regions: List[TextRegion]) -> str:
    """Classify the dominant font type from text regions."""
    if not regions:
        return "sans-serif"

    # Use the largest text regions for classification
    sorted_regions = sorted(regions, key=lambda r: r.height, reverse=True)
    sample_regions = sorted_regions[:min(5, len(sorted_regions))]

    serif_score = 0
    mono_score = 0
    total = 0

    for region in sample_regions:
        x, y, w, h = region.bounds
        roi = gray[max(0, y):min(gray.shape[0], y + h),
                    max(0, x):min(gray.shape[1], x + w)]
        if roi.size == 0:
            continue

        total += 1

        # Serif detection: serifs create high-frequency horizontal detail
        # at the baseline and cap height
        _, binary = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Check stroke width variance (monospace = uniform, serif = variable)
        col_sums = binary.sum(axis=0) / 255.0
        nonzero_cols = col_sums[col_sums > 0]

        if len(nonzero_cols) > 5:
            variance = float(np.var(nonzero_cols))
            mean_width = float(np.mean(nonzero_cols))

            # High variance in stroke width → serif
            if mean_width > 0 and variance / mean_width > 2.0:
                serif_score += 1

            # Check for uniform character spacing (monospace indicator)
            # Find character boundaries
            char_gaps = []
            in_char = False
            char_start = 0
            for i, val in enumerate(col_sums):
                if val > 0 and not in_char:
                    in_char = True
                    char_start = i
                elif val == 0 and in_char:
                    in_char = False
                    char_gaps.append(i - char_start)

            if len(char_gaps) >= 3:
                gap_variance = np.var(char_gaps) / max(np.mean(char_gaps), 1)
                if gap_variance < 0.1:  # very uniform → monospace
                    mono_score += 1

    if total == 0:
        return "sans-serif"

    if mono_score > total * 0.4:
        return "monospace"
    elif serif_score > total * 0.4:
        return "serif"
    else:
        return "sans-serif"


def _detect_weights(gray: "np.ndarray", regions: List[TextRegion]) -> List[str]:
    """Detect font weight distribution from text regions."""
    if not regions:
        return ["400", "500", "600", "700"]

    weight_counts = {}
    for region in regions:
        # Snap to standard weights
        w = region.estimated_weight
        snapped = min([300, 400, 500, 600, 700, 800], key=lambda x: abs(x - w))
        weight_counts[snapped] = weight_counts.get(snapped, 0) + 1

    # Return weights that appear with meaningful frequency
    threshold = len(regions) * 0.05
    detected = sorted(w for w, count in weight_counts.items() if count >= threshold)

    if not detected:
        detected = [400, 600, 700]

    return [str(w) for w in detected]


def _most_common_size(heights: List[int]) -> int:
    """Find the most common text height."""
    if not heights:
        return 16
    from collections import Counter
    counter = Counter(round(h / 2) * 2 for h in heights)  # round to even
    return counter.most_common(1)[0][0]
