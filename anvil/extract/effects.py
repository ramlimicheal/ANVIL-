"""
ANVIL Effects Extractor — Extracts shadows, gradients, glassmorphism, and borders.
Uses Erf curve fitting from physics.py for mathematically precise shadow extraction.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from .structure import StructuralTree, LayoutNode

try:
    import cv2
    import numpy as np
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

try:
    from scipy.optimize import curve_fit
    from scipy.special import erf
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


@dataclass
class ExtractedShadow:
    """A single extracted box-shadow."""
    offset_x: int
    offset_y: int
    blur: int
    spread: int
    color: str       # rgba(...)
    inset: bool = False

    def to_css(self) -> str:
        prefix = "inset " if self.inset else ""
        return f"{prefix}{self.offset_x}px {self.offset_y}px {self.blur}px {self.spread}px {self.color}"


@dataclass
class ExtractedGradient:
    """A detected gradient."""
    type: str        # linear, radial
    direction: str   # e.g., "135deg", "to bottom"
    stops: List[Tuple[str, float]]  # (color, position%)

    def to_css(self) -> str:
        stops_str = ", ".join(f"{c} {p:.0f}%" for c, p in self.stops)
        if self.type == "linear":
            return f"linear-gradient({self.direction}, {stops_str})"
        return f"radial-gradient(circle, {stops_str})"


@dataclass
class ExtractedEffects:
    """Complete extracted visual effects."""
    shadows: List[ExtractedShadow]
    gradients: List[ExtractedGradient]
    has_glassmorphism: bool = False
    glassmorphism_blur: int = 0
    border_width: int = 0
    border_color: str = ""
    border_style: str = "solid"

    def to_dict(self) -> dict:
        result = {}
        if self.shadows:
            result["shadow_sm"] = self.shadows[0].to_css() if len(self.shadows) > 0 else ""
            result["shadow_md"] = self.shadows[1].to_css() if len(self.shadows) > 1 else ""
        if self.has_glassmorphism:
            result["backdrop_blur"] = f"blur({self.glassmorphism_blur}px)"
            result["shadow_glass"] = "inset 0 1px 0 0 rgba(255,255,255,0.05)"
        if self.gradients:
            result["gradient_primary"] = self.gradients[0].to_css()
        if self.border_width:
            result["border"] = f"{self.border_width}px {self.border_style} {self.border_color}"
        return result


def _erf_decay(x, a, b, mu, sigma):
    """Erf model for box-shadow off a straight edge."""
    return b + (a / 2.0) * (1.0 - erf((x - mu) / (sigma * np.sqrt(2))))


def extract_effects(image_path: str, tree: StructuralTree) -> ExtractedEffects:
    """Extract visual effects from a screenshot + structural tree.

    Args:
        image_path: Path to screenshot
        tree: StructuralTree from structure.py

    Returns:
        ExtractedEffects with shadows, gradients, glassmorphism
    """
    if not HAS_DEPS:
        raise ImportError("opencv-python and numpy required")

    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not read: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float64) / 255.0
    h, w = gray.shape

    # Extract shadows from component edges
    shadows = _extract_shadows(gray, tree.root, w, h)

    # Extract gradients from large surfaces
    gradients = _extract_gradients(img, tree.root)

    # Detect glassmorphism
    has_glass, blur_radius = _detect_glassmorphism(img, gray, tree.root)

    # Detect borders
    border_w, border_color, border_style = _detect_borders(gray, tree.root)

    return ExtractedEffects(
        shadows=shadows,
        gradients=gradients,
        has_glassmorphism=has_glass,
        glassmorphism_blur=blur_radius,
        border_width=border_w,
        border_color=border_color,
        border_style=border_style,
    )


def _extract_shadows(
    gray: "np.ndarray", root: LayoutNode, w: int, h: int,
) -> List[ExtractedShadow]:
    """Extract box-shadow parameters from component edges using Erf fitting."""
    shadows = []
    components = _get_components(root, max_depth=3)

    for node in components[:10]:  # Sample up to 10 components
        x, y, nw, nh = node.bounds
        if nw < 30 or nh < 30:
            continue

        shadow = _analyze_edge_shadow(gray, x, y, nw, nh, w, h)
        if shadow:
            shadows.append(shadow)

    # Deduplicate similar shadows
    if shadows:
        shadows = _deduplicate_shadows(shadows)

    return shadows


def _analyze_edge_shadow(
    gray: "np.ndarray", x: int, y: int, nw: int, nh: int, w: int, h: int,
) -> Optional[ExtractedShadow]:
    """Analyze luminance decay from a component edge to extract shadow params."""
    ray_length = min(30, w - (x + nw) - 1, h - (y + nh) - 1)
    if ray_length < 8:
        return None

    # Cast ray downward from bottom edge
    mid_x = x + nw // 2
    start_y = y + nh

    if start_y + ray_length >= h:
        return None

    ray = gray[start_y:start_y + ray_length, mid_x]
    if ray.size < 8:
        return None

    # Check if there's actually a luminance gradient (shadow)
    if np.ptp(ray) < 0.02:
        return None  # flat — no shadow

    # Try Erf fit if scipy available
    if HAS_SCIPY:
        x_data = np.arange(len(ray))
        p0 = [np.ptp(ray), np.min(ray), len(ray) / 4, max(1.0, len(ray) / 6)]

        try:
            popt, _ = curve_fit(_erf_decay, x_data, ray, p0=p0, maxfev=1000)
            amplitude, baseline, mu, sigma = popt
            blur = max(1, int(abs(sigma) * 2))
            opacity = min(0.5, max(0.02, float(abs(amplitude))))

            return ExtractedShadow(
                offset_x=0,
                offset_y=max(1, int(mu / 2)),
                blur=blur,
                spread=0,
                color=f"rgba(0,0,0,{opacity:.2f})",
            )
        except (RuntimeError, ValueError):
            pass

    # Fallback: simple gradient measurement
    half_point = len(ray) // 2
    top_half = float(ray[:half_point].mean())
    bot_half = float(ray[half_point:].mean())
    diff = abs(top_half - bot_half)

    if diff > 0.02:
        blur = max(2, ray_length // 3)
        opacity = min(0.3, diff)
        return ExtractedShadow(
            offset_x=0, offset_y=max(1, blur // 3),
            blur=blur, spread=0,
            color=f"rgba(0,0,0,{opacity:.2f})",
        )

    return None


def _extract_gradients(img: "np.ndarray", root: LayoutNode) -> List[ExtractedGradient]:
    """Detect gradients in large surface areas."""
    gradients = []
    components = _get_components(root, max_depth=2)

    for node in components[:5]:
        x, y, nw, nh = node.bounds
        if nw < 60 or nh < 60:
            continue

        region = img[max(0, y):min(img.shape[0], y + nh),
                      max(0, x):min(img.shape[1], x + nw)]
        if region.size == 0:
            continue

        gradient = _detect_gradient(region)
        if gradient:
            gradients.append(gradient)

    return gradients


def _detect_gradient(region: "np.ndarray") -> Optional[ExtractedGradient]:
    """Detect if a region contains a linear or radial gradient."""
    h, w = region.shape[:2]
    if h < 10 or w < 10:
        return None

    # Sample horizontal and vertical color rays
    mid_y = h // 2
    mid_x = w // 2

    h_ray = region[mid_y, ::max(1, w // 20)].astype(float)
    v_ray = region[::max(1, h // 20), mid_x].astype(float)

    # Check for monotonic color change (gradient indicator)
    h_diff = np.diff(h_ray.mean(axis=1)) if h_ray.ndim > 1 else np.diff(h_ray)
    v_diff = np.diff(v_ray.mean(axis=1)) if v_ray.ndim > 1 else np.diff(v_ray)

    h_monotonic = _is_monotonic(h_diff)
    v_monotonic = _is_monotonic(v_diff)

    if not h_monotonic and not v_monotonic:
        return None

    # Extract start and end colors
    if v_monotonic:
        start_color = _rgb_to_hex_str(region[0, mid_x])
        end_color = _rgb_to_hex_str(region[-1, mid_x])
        direction = "to bottom" if v_diff.mean() > 0 else "to top"
    else:
        start_color = _rgb_to_hex_str(region[mid_y, 0])
        end_color = _rgb_to_hex_str(region[mid_y, -1])
        direction = "to right" if h_diff.mean() > 0 else "to left"

    if start_color == end_color:
        return None

    return ExtractedGradient(
        type="linear",
        direction=direction,
        stops=[(start_color, 0), (end_color, 100)],
    )


def _detect_glassmorphism(
    img: "np.ndarray", gray: "np.ndarray", root: LayoutNode,
) -> Tuple[bool, int]:
    """Detect glassmorphism (backdrop-filter: blur + transparency)."""
    components = _get_components(root, max_depth=2)

    for node in components[:5]:
        x, y, nw, nh = node.bounds
        if nw < 50 or nh < 50:
            continue

        region = gray[max(0, y):min(gray.shape[0], y + nh),
                       max(0, x):min(gray.shape[1], x + nw)]
        if region.size == 0:
            continue

        # Glassmorphism indicators:
        # 1. Low contrast within the surface
        # 2. Visible but blurred background
        std = float(np.std(region))
        mean_val = float(np.mean(region))

        # Low internal variance + mid-range luminance = glass-like
        if std < 0.08 and 0.05 < mean_val < 0.4:
            # Estimate blur from edge sharpness
            edges = cv2.Laplacian(region, cv2.CV_64F)
            edge_strength = float(np.abs(edges).mean())
            if edge_strength < 0.02:
                blur_radius = max(8, int(40 * (1 - edge_strength * 50)))
                return True, min(blur_radius, 60)

    return False, 0


def _detect_borders(
    gray: "np.ndarray", root: LayoutNode,
) -> Tuple[int, str, str]:
    """Detect border properties from component edges."""
    components = _get_components(root, max_depth=3)

    for node in components[:8]:
        x, y, nw, nh = node.bounds
        if nw < 20 or nh < 20:
            continue

        # Sample top edge
        if y > 0 and y + nh < gray.shape[0]:
            edge_row = gray[y, max(0, x):min(gray.shape[1], x + nw)]
            above_row = gray[max(0, y - 2), max(0, x):min(gray.shape[1], x + nw)]

            if edge_row.size > 0 and above_row.size > 0:
                diff = float(np.abs(edge_row.mean() - above_row.mean()))
                if diff > 0.05:  # visible edge = border
                    brightness = float(edge_row.mean())
                    color = f"rgba(255,255,255,{min(brightness, 0.15):.2f})"
                    return 1, color, "solid"

    return 0, "", ""


def _is_monotonic(diff: "np.ndarray", threshold: float = 0.6) -> bool:
    """Check if differences are mostly monotonic (gradient indicator)."""
    if len(diff) < 3:
        return False
    positive = (diff > 0).sum()
    negative = (diff < 0).sum()
    total = len(diff)
    return positive > total * threshold or negative > total * threshold


def _rgb_to_hex_str(pixel) -> str:
    """Convert a BGR pixel to hex string."""
    if len(pixel) >= 3:
        b, g, r = int(pixel[0]), int(pixel[1]), int(pixel[2])
        return f"#{r:02X}{g:02X}{b:02X}"
    return "#000000"


def _get_components(root: LayoutNode, max_depth: int = 3) -> List[LayoutNode]:
    """Get all nodes up to max_depth."""
    result = []

    def _collect(node: LayoutNode):
        if node.depth <= max_depth and node.area > 0:
            result.append(node)
        for child in node.children:
            _collect(child)

    _collect(root)
    return result


def _deduplicate_shadows(shadows: List[ExtractedShadow]) -> List[ExtractedShadow]:
    """Merge similar shadows."""
    if len(shadows) <= 1:
        return shadows

    unique = [shadows[0]]
    for s in shadows[1:]:
        is_dup = False
        for u in unique:
            if (abs(s.blur - u.blur) <= 2
                    and abs(s.offset_y - u.offset_y) <= 1
                    and s.inset == u.inset):
                is_dup = True
                break
        if not is_dup:
            unique.append(s)

    # Sort: smaller shadow first (sm), then larger (md)
    unique.sort(key=lambda s: s.blur)
    return unique[:3]
