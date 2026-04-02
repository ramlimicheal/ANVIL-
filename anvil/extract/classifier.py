"""
ANVIL Page Classifier — Detects page type and semantic sections from screenshots.
Uses density profiles, aspect ratios, and structural heuristics — no LLM needed.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

try:
    import cv2
    import numpy as np
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


PAGE_TYPES = [
    "landing", "dashboard", "login", "signup", "settings",
    "pricing", "blog", "profile", "onboarding", "modal", "mobile_app",
]

SECTION_TYPES = [
    "navbar", "hero", "sidebar", "features", "pricing_table",
    "testimonials", "footer", "stat_cards", "chart_area",
    "form", "table", "cta", "content", "header", "toolbar",
]


@dataclass
class Section:
    """A detected semantic section."""
    type: str
    bounds: Tuple[int, int, int, int]  # x, y, w, h
    confidence: float = 0.0

    @property
    def area(self) -> int:
        return self.bounds[2] * self.bounds[3]


@dataclass
class PageClassification:
    """Result of page type classification."""
    page_type: str
    confidence: float
    sections: List[Section]
    image_size: Tuple[int, int]  # w, h
    has_sidebar: bool = False
    has_navbar: bool = False
    has_footer: bool = False
    content_width: int = 0
    estimated_columns: int = 1


def classify_page(image_path: str) -> PageClassification:
    """Classify a screenshot into page type and detect sections.

    Args:
        image_path: Path to screenshot

    Returns:
        PageClassification with page type and section map
    """
    if not HAS_DEPS:
        raise ImportError("opencv-python and numpy required")

    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not read: {image_path}")

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Compute structural features
    features = _compute_features(gray, w, h)
    sections = _detect_sections(gray, w, h, features)

    # Classify page type from features
    page_type, confidence = _classify_type(features, sections, w, h)

    return PageClassification(
        page_type=page_type,
        confidence=round(confidence, 2),
        sections=sections,
        image_size=(w, h),
        has_sidebar=features["has_sidebar"],
        has_navbar=features["has_navbar"],
        has_footer=features["has_footer"],
        content_width=features["content_width"],
        estimated_columns=features["est_columns"],
    )


def _compute_features(gray: "np.ndarray", w: int, h: int) -> Dict:
    """Compute structural features from grayscale image."""
    # Edge density
    edges = cv2.Canny(gray, 50, 150)

    # Horizontal density profile: average edge density per row band
    band_h = max(1, h // 20)
    h_profile = []
    for y in range(0, h - band_h, band_h):
        band = edges[y:y + band_h, :]
        h_profile.append(float(band.mean()))

    # Vertical density profile: average edge density per column band
    band_w = max(1, w // 20)
    v_profile = []
    for x in range(0, w - band_w, band_w):
        band = edges[:, x:x + band_w]
        v_profile.append(float(band.mean()))

    # Sidebar detection: dense narrow left column
    left_quarter = edges[:, :w // 5]
    right_area = edges[:, w // 5:]
    left_density = float(left_quarter.mean())
    right_density = float(right_area.mean()) if right_area.size > 0 else 0
    has_sidebar = left_density > right_density * 1.5 and left_density > 5.0

    # Navbar detection: dense top band (full width)
    top_band = edges[:max(1, h // 12), :]
    has_navbar = float(top_band.mean()) > 3.0

    # Footer detection: dense bottom band
    bot_band = edges[h - max(1, h // 12):, :]
    has_footer = float(bot_band.mean()) > 2.0

    # Content width: find the horizontal extent of content
    col_sums = edges.sum(axis=0)
    threshold = col_sums.max() * 0.1
    content_cols = np.where(col_sums > threshold)[0]
    if len(content_cols) > 0:
        content_width = int(content_cols[-1] - content_cols[0])
    else:
        content_width = w

    # Vertical section count: number of distinct density peaks
    if h_profile:
        mean_density = sum(h_profile) / len(h_profile)
        section_boundaries = sum(
            1 for i in range(1, len(h_profile))
            if (h_profile[i] > mean_density * 1.5 and h_profile[i - 1] < mean_density * 0.5)
            or (h_profile[i] < mean_density * 0.5 and h_profile[i - 1] > mean_density * 1.5)
        )
    else:
        section_boundaries = 0

    # Estimate columns from vertical edge patterns in the middle third
    mid_start = h // 3
    mid_end = 2 * h // 3
    mid_edges = edges[mid_start:mid_end, :]
    v_sums = mid_edges.sum(axis=0).astype(float)
    if v_sums.max() > 0:
        v_sums_smooth = np.convolve(v_sums, np.ones(20) / 20, mode="same")
        peaks = _find_peaks(v_sums_smooth, min_distance=w // 8)
        est_columns = max(1, min(6, len(peaks)))
    else:
        est_columns = 1

    # Aspect ratio
    aspect = w / max(h, 1)

    # Centered content check (login/signup pattern)
    if content_cols.size > 0:
        center = w // 2
        content_center = int((content_cols[0] + content_cols[-1]) / 2)
        is_centered = abs(content_center - center) < w * 0.1
    else:
        is_centered = False

    is_narrow_content = content_width < w * 0.5

    return {
        "h_profile": h_profile,
        "v_profile": v_profile,
        "has_sidebar": has_sidebar,
        "has_navbar": has_navbar,
        "has_footer": has_footer,
        "content_width": content_width,
        "section_count": section_boundaries // 2 + 1,
        "est_columns": est_columns,
        "aspect_ratio": aspect,
        "is_centered": is_centered,
        "is_narrow_content": is_narrow_content,
        "edge_density": float(edges.mean()),
    }


def _find_peaks(data: "np.ndarray", min_distance: int = 50) -> List[int]:
    """Simple peak finding in 1D array."""
    peaks = []
    threshold = data.mean() + data.std()
    for i in range(1, len(data) - 1):
        if data[i] > data[i - 1] and data[i] > data[i + 1] and data[i] > threshold:
            if not peaks or (i - peaks[-1]) >= min_distance:
                peaks.append(i)
    return peaks


def _classify_type(features: Dict, sections: List[Section], w: int, h: int) -> Tuple[str, float]:
    """Classify page type from features."""
    scores = {t: 0.0 for t in PAGE_TYPES}

    # Dashboard: sidebar + dense content + multiple columns
    if features["has_sidebar"]:
        scores["dashboard"] += 3.0
    if features["est_columns"] >= 3:
        scores["dashboard"] += 2.0
    if features["edge_density"] > 5.0:
        scores["dashboard"] += 1.0

    # Landing page: no sidebar, tall, many sections, has hero
    if not features["has_sidebar"] and features["section_count"] >= 3:
        scores["landing"] += 3.0
    if features["has_navbar"] and features["has_footer"]:
        scores["landing"] += 1.5
    if features["aspect_ratio"] < 0.7:  # tall page
        scores["landing"] += 1.0

    # Login/Signup: centered, narrow content, short
    if features["is_centered"] and features["is_narrow_content"]:
        scores["login"] += 3.0
        scores["signup"] += 2.5
    if features["section_count"] <= 2 and features["is_narrow_content"]:
        scores["login"] += 2.0
        scores["signup"] += 1.5

    # Modal: small centered card, dark surround typically
    if features["is_centered"] and features["is_narrow_content"] and features["aspect_ratio"] > 0.8:
        scores["modal"] += 2.5

    # Pricing: multiple equal-width columns in mid section
    if features["est_columns"] >= 3 and not features["has_sidebar"]:
        scores["pricing"] += 2.0

    # Settings: sidebar + form-like content
    if features["has_sidebar"] and features["est_columns"] <= 2:
        scores["settings"] += 2.5

    # Blog: single column, long, navbar + footer
    if features["est_columns"] == 1 and features["section_count"] >= 2 and not features["has_sidebar"]:
        scores["blog"] += 2.0

    # Mobile app: narrow aspect ratio
    if w < 500 or (w < 600 and h > w * 1.5):
        scores["mobile_app"] += 3.0

    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]
    total = sum(scores.values()) or 1
    confidence = best_score / total

    return best_type, min(confidence, 0.99)


def _detect_sections(gray: "np.ndarray", w: int, h: int, features: Dict) -> List[Section]:
    """Detect semantic sections from structural features."""
    sections = []
    edges = cv2.Canny(gray, 50, 150)

    # Navbar: top ~8% of image
    if features["has_navbar"]:
        nav_h = max(40, h // 12)
        sections.append(Section("navbar", (0, 0, w, nav_h), 0.85))

    # Sidebar: left ~20% of image
    sidebar_w = 0
    if features["has_sidebar"]:
        sidebar_w = w // 5
        sections.append(Section("sidebar", (0, 0, sidebar_w, h), 0.80))

    # Footer: bottom ~10%
    if features["has_footer"]:
        footer_h = max(40, h // 10)
        sections.append(Section("footer", (0, h - footer_h, w, footer_h), 0.75))

    # Detect horizontal content bands in the remaining area
    content_x = sidebar_w
    content_w = w - sidebar_w
    nav_h = sections[0].bounds[3] if features["has_navbar"] else 0
    footer_h = sections[-1].bounds[3] if features["has_footer"] else 0
    content_start = nav_h
    content_end = h - footer_h

    # Split content area into bands using edge density valleys
    h_profile = features["h_profile"]
    if h_profile:
        band_h = max(1, h // 20)
        mean_d = sum(h_profile) / len(h_profile)

        # Find valley positions (low density = section boundaries)
        in_content = False
        section_start = content_start
        band_idx = 0

        for i, density in enumerate(h_profile):
            y_pos = i * band_h
            if y_pos < content_start or y_pos > content_end:
                continue

            if density > mean_d * 0.3 and not in_content:
                in_content = True
                section_start = y_pos
            elif density < mean_d * 0.2 and in_content:
                in_content = False
                sec_h = y_pos - section_start
                if sec_h > 30:
                    sections.append(Section(
                        "content", (content_x, section_start, content_w, sec_h), 0.60
                    ))

        # Capture final section
        if in_content and content_end - section_start > 30:
            sections.append(Section(
                "content", (content_x, section_start, content_w, content_end - section_start), 0.55
            ))

    # Label content sections by position
    content_sections = [s for s in sections if s.type == "content"]
    for i, sec in enumerate(content_sections):
        y_center = sec.bounds[1] + sec.bounds[3] / 2
        rel_pos = y_center / h

        if i == 0 and rel_pos < 0.35:
            sec.type = "hero"
            sec.confidence = 0.70
        elif i == 1 and features.get("est_columns", 1) >= 3:
            sec.type = "features"
            sec.confidence = 0.65
        elif i == len(content_sections) - 1 and rel_pos > 0.7:
            sec.type = "cta"
            sec.confidence = 0.55

    return sections
