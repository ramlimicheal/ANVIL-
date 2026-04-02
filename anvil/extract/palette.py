"""
ANVIL Palette Extractor — Extracts color palette from screenshots using CIELAB K-means.
Assigns semantic roles (background, text, accent, success, warning, error) automatically.
"""

import math
import colorsys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

try:
    import cv2
    import numpy as np
    from sklearn.cluster import KMeans
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


@dataclass
class ExtractedColor:
    """A single extracted color with metadata."""
    hex: str
    rgb: Tuple[int, int, int]
    lab: Tuple[float, float, float]
    area_pct: float  # percentage of image this color covers
    role: str = ""   # semantic role: bg_0, text_primary, accent, etc.


@dataclass
class ExtractedPalette:
    """Complete extracted palette with semantic roles."""
    colors: List[ExtractedColor]
    roles: Dict[str, str]  # role -> hex mapping
    is_dark_mode: bool = False
    dominant_hue: float = 0.0  # 0-360

    def to_style_tensor_palette(self) -> Dict[str, str]:
        """Convert to StyleTensor palette format."""
        return dict(self.roles)


def _require_deps():
    if not HAS_DEPS:
        raise ImportError("Extract dependencies required: pip install opencv-python numpy scikit-learn")


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def _hex_to_rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """Convert RGB array to CIELAB via OpenCV."""
    # OpenCV expects BGR uint8 in a 3D array
    bgr = rgb[:, ::-1].reshape(1, -1, 3).astype(np.uint8)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    return lab.reshape(-1, 3).astype(np.float64)


def _delta_e(lab1: Tuple[float, ...], lab2: Tuple[float, ...]) -> float:
    """CIE76 color difference in CIELAB space."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(lab1, lab2)))


def _relative_luminance(r: int, g: int, b: int) -> float:
    """WCAG relative luminance."""
    def channel(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast_ratio(rgb1: Tuple[int, ...], rgb2: Tuple[int, ...]) -> float:
    """WCAG contrast ratio between two colors."""
    l1 = _relative_luminance(*rgb1)
    l2 = _relative_luminance(*rgb2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _optimal_k(data: np.ndarray, k_min: int = 4, k_max: int = 16) -> int:
    """Find optimal K via elbow method on inertia."""
    inertias = []
    k_range = range(k_min, k_max + 1)
    for k in k_range:
        km = KMeans(n_clusters=k, n_init=3, max_iter=100, random_state=42)
        km.fit(data)
        inertias.append(km.inertia_)

    # Find elbow: maximum second derivative
    if len(inertias) < 3:
        return k_min

    diffs = [inertias[i] - inertias[i + 1] for i in range(len(inertias) - 1)]
    diffs2 = [diffs[i] - diffs[i + 1] for i in range(len(diffs) - 1)]

    best_idx = max(range(len(diffs2)), key=lambda i: diffs2[i])
    return list(k_range)[best_idx + 1]


def extract_palette(
    image_path: str,
    max_colors: int = 12,
    sample_step: int = 4,
    merge_threshold: float = 12.0,
) -> ExtractedPalette:
    """Extract color palette from a screenshot.

    Args:
        image_path: Path to screenshot PNG/JPG
        max_colors: Maximum palette colors to extract
        sample_step: Sample every Nth pixel (speed vs accuracy)
        merge_threshold: CIELAB ΔE below which colors merge

    Returns:
        ExtractedPalette with semantic role assignments
    """
    _require_deps()

    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")

    h, w = img.shape[:2]
    total_pixels = h * w

    # Convert BGR -> RGB
    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # Sample pixels for speed
    sampled = rgb_img[::sample_step, ::sample_step].reshape(-1, 3)

    # Convert to CIELAB for perceptually uniform clustering
    lab_pixels = _rgb_to_lab(sampled)

    # Find optimal K and cluster
    k = min(max_colors, _optimal_k(lab_pixels, k_min=4, k_max=max_colors))
    kmeans = KMeans(n_clusters=k, n_init=5, max_iter=200, random_state=42)
    labels = kmeans.fit_predict(lab_pixels)

    # Compute cluster stats
    raw_colors = []
    for i in range(k):
        mask = labels == i
        count = mask.sum()
        area_pct = round(count / len(labels) * 100, 1)

        # Mean color in RGB (from sampled pixels, not LAB centers)
        mean_rgb = sampled[mask].mean(axis=0).astype(int)
        r, g, b = int(mean_rgb[0]), int(mean_rgb[1]), int(mean_rgb[2])

        lab_center = tuple(kmeans.cluster_centers_[i])

        raw_colors.append(ExtractedColor(
            hex=_rgb_to_hex(r, g, b),
            rgb=(r, g, b),
            lab=lab_center,
            area_pct=area_pct,
        ))

    # Merge perceptually similar colors (ΔE < threshold)
    merged = _merge_similar(raw_colors, merge_threshold)

    # Sort by area (largest first)
    merged.sort(key=lambda c: c.area_pct, reverse=True)

    # Classify: dark mode or light mode
    bg_color = merged[0]  # largest area = background
    bg_lum = _relative_luminance(*bg_color.rgb)
    is_dark = bg_lum < 0.2

    # Assign semantic roles
    roles = _assign_roles(merged, is_dark)

    # Find dominant chromatic hue
    chromatic = [c for c in merged if _saturation(c.rgb) > 0.15]
    dom_hue = 0.0
    if chromatic:
        r, g, b = chromatic[0].rgb
        h_val, _, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        dom_hue = round(h_val * 360, 1)

    return ExtractedPalette(
        colors=merged,
        roles=roles,
        is_dark_mode=is_dark,
        dominant_hue=dom_hue,
    )


def _merge_similar(colors: List[ExtractedColor], threshold: float) -> List[ExtractedColor]:
    """Merge colors with ΔE below threshold."""
    merged = []
    used = set()

    for i, c1 in enumerate(colors):
        if i in used:
            continue
        group = [c1]
        for j, c2 in enumerate(colors):
            if j <= i or j in used:
                continue
            if _delta_e(c1.lab, c2.lab) < threshold:
                group.append(c2)
                used.add(j)

        # Merge: area-weighted average
        total_area = sum(c.area_pct for c in group)
        if total_area == 0:
            continue

        avg_r = int(sum(c.rgb[0] * c.area_pct for c in group) / total_area)
        avg_g = int(sum(c.rgb[1] * c.area_pct for c in group) / total_area)
        avg_b = int(sum(c.rgb[2] * c.area_pct for c in group) / total_area)
        avg_lab = tuple(
            sum(c.lab[ch] * c.area_pct for c in group) / total_area
            for ch in range(3)
        )

        merged.append(ExtractedColor(
            hex=_rgb_to_hex(avg_r, avg_g, avg_b),
            rgb=(avg_r, avg_g, avg_b),
            lab=avg_lab,
            area_pct=round(total_area, 1),
        ))
        used.add(i)

    return merged


def _saturation(rgb: Tuple[int, int, int]) -> float:
    """Get HSV saturation of an RGB color."""
    _, s, _ = colorsys.rgb_to_hsv(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    return s


def _hue_deg(rgb: Tuple[int, int, int]) -> float:
    """Get hue in degrees."""
    h, _, _ = colorsys.rgb_to_hsv(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    return h * 360


def _assign_roles(colors: List[ExtractedColor], is_dark: bool) -> Dict[str, str]:
    """Assign semantic roles to extracted colors."""
    roles: Dict[str, str] = {}

    if not colors:
        return roles

    # Background layers: top 3 by area with low saturation
    bg_candidates = sorted(colors, key=lambda c: c.area_pct, reverse=True)
    bg_layers = []
    for c in bg_candidates:
        if len(bg_layers) >= 3:
            break
        if _saturation(c.rgb) < 0.3:
            bg_layers.append(c)

    for i, c in enumerate(bg_layers):
        role = f"bg_layer_{i}"
        roles[role] = c.hex
        c.role = role

    # Text colors: highest contrast against bg_layer_0
    bg0_rgb = bg_layers[0].rgb if bg_layers else (0, 0, 0)
    unassigned = [c for c in colors if not c.role]
    text_candidates = sorted(
        unassigned,
        key=lambda c: _contrast_ratio(c.rgb, bg0_rgb),
        reverse=True,
    )

    text_roles = ["text_primary", "text_secondary", "text_tertiary"]
    for role, c in zip(text_roles, text_candidates[:3]):
        if _contrast_ratio(c.rgb, bg0_rgb) >= 2.0:
            roles[role] = c.hex
            c.role = role

    # Accent: highest saturation among remaining
    unassigned = [c for c in colors if not c.role]
    by_sat = sorted(unassigned, key=lambda c: _saturation(c.rgb), reverse=True)

    if by_sat:
        roles["accent_primary"] = by_sat[0].hex
        by_sat[0].role = "accent_primary"
    if len(by_sat) > 1:
        roles["accent_secondary"] = by_sat[1].hex
        by_sat[1].role = "accent_secondary"

    # Semantic colors by hue
    unassigned = [c for c in colors if not c.role and _saturation(c.rgb) > 0.2]
    for c in unassigned:
        hue = _hue_deg(c.rgb)
        if 80 <= hue <= 160 and "success" not in roles:
            roles["success"] = c.hex
            c.role = "success"
        elif (hue <= 30 or hue >= 340) and "error" not in roles:
            roles["error"] = c.hex
            c.role = "error"
        elif 30 < hue < 80 and "warning" not in roles:
            roles["warning"] = c.hex
            c.role = "warning"
        elif 180 <= hue <= 260 and "info" not in roles:
            roles["info"] = c.hex
            c.role = "info"

    # Border colors: low saturation, medium contrast against bg
    unassigned = [c for c in colors if not c.role]
    for c in unassigned:
        ratio = _contrast_ratio(c.rgb, bg0_rgb)
        if 1.2 < ratio < 3.0 and _saturation(c.rgb) < 0.15:
            if "border_subtle" not in roles:
                roles["border_subtle"] = c.hex
                c.role = "border_subtle"
            elif "border_active" not in roles:
                roles["border_active"] = c.hex
                c.role = "border_active"

    return roles
