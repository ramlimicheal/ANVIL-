"""
ANVIL Gestalt — Optical mass centroid calculation.

Catches the difference between geometric centering (CSS flexbox)
and optical centering (human visual perception).

A play button ▶ inside a circle ● looks off-center when
geometrically centered because the visual mass of a triangle
concentrates at its base. A human designer nudges it 2px.
This module detects whether the AI replicated that nudge.

Dependencies: OpenCV, numpy (already installed).
"""

from dataclasses import dataclass, field
from typing import List, Tuple

try:
    import cv2
    import numpy as np
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


@dataclass
class OpticalCentroidResult:
    """Optical vs geometric centroid comparison for one element."""
    label: str
    geo_center: Tuple[float, float]      # Geometric center (x, y)
    optical_center: Tuple[float, float]   # Luminance-weighted centroid (x, y)
    delta_px: float                       # Euclidean distance between the two
    is_asymmetric: bool                   # True if element shape is non-rectangular


@dataclass
class GestaltResult:
    """Complete Gestalt optical mass analysis."""
    elements_analyzed: int
    asymmetric_elements: int
    mean_optical_delta: float
    max_optical_delta: float
    ref_deltas: List[OpticalCentroidResult] = field(default_factory=list)
    gen_deltas: List[OpticalCentroidResult] = field(default_factory=list)
    match_violations: List[dict] = field(default_factory=list)
    passed: bool = True
    score_10: float = 10.0

    def violations_report(self) -> dict:
        return {
            "elements_analyzed": self.elements_analyzed,
            "asymmetric_elements": self.asymmetric_elements,
            "violations": self.match_violations,
            "passed": self.passed,
            "score": self.score_10,
        }


class GestaltAnalyzer:
    """Analyze optical mass distribution in UI elements."""

    def __init__(self, significance_threshold_px: float = 1.5):
        if not HAS_DEPS:
            raise ImportError("OpenCV + numpy required")
        self.threshold = significance_threshold_px

    def compare_optical_mass(
        self,
        reference_path: str,
        generated_path: str,
        blocks_ref: list,
        blocks_gen: list,
    ) -> GestaltResult:
        """Compare optical centroids of matched element pairs.

        Args:
            reference_path: Path to reference screenshot
            generated_path: Path to generated screenshot
            blocks_ref: List of VisualBlock from reference (from block_match)
            blocks_gen: List of VisualBlock from generated (from block_match)
        """
        ref_img = cv2.imread(reference_path)
        gen_img = cv2.imread(generated_path)

        if ref_img is None or gen_img is None:
            return GestaltResult(elements_analyzed=0, passed=True, score_10=10.0)

        ref_results = []
        gen_results = []
        violations = []
        n_asymmetric = 0

        pairs = min(len(blocks_ref), len(blocks_gen))
        for i in range(pairs):
            rb = blocks_ref[i]
            gb = blocks_gen[i]

            # Crop regions
            ref_crop = ref_img[rb.y:rb.y+rb.h, rb.x:rb.x+rb.w]
            gen_crop = gen_img[gb.y:gb.y+gb.h, gb.x:gb.x+gb.w]

            if ref_crop.size == 0 or gen_crop.size == 0:
                continue

            ref_oc = self._optical_centroid(ref_crop, f"ref_{i}")
            gen_oc = self._optical_centroid(gen_crop, f"gen_{i}")

            ref_results.append(ref_oc)
            gen_results.append(gen_oc)

            if ref_oc.is_asymmetric:
                n_asymmetric += 1

            # Only flag if BOTH are asymmetric AND the optical deltas differ significantly
            if ref_oc.is_asymmetric and ref_oc.delta_px > self.threshold:
                delta_diff = abs(ref_oc.delta_px - gen_oc.delta_px)
                if delta_diff > self.threshold:
                    violations.append({
                        "element_index": i,
                        "ref_optical_offset": f"({ref_oc.optical_center[0]-ref_oc.geo_center[0]:.1f}, {ref_oc.optical_center[1]-ref_oc.geo_center[1]:.1f})px",
                        "gen_optical_offset": f"({gen_oc.optical_center[0]-gen_oc.geo_center[0]:.1f}, {gen_oc.optical_center[1]-gen_oc.geo_center[1]:.1f})px",
                        "delta_mismatch_px": round(delta_diff, 1),
                        "fix_hint": f"Element has asymmetric visual mass. Designer applied {ref_oc.delta_px:.1f}px optical nudge. AI used geometric centering. Apply transform: translate() to match.",
                    })

        # Score
        if violations:
            penalty = min(len(violations) * 1.0, 5.0)
            score = max(0.0, 10.0 - penalty)
        else:
            score = 10.0

        all_deltas = [v["delta_mismatch_px"] for v in violations] if violations else [0.0]

        return GestaltResult(
            elements_analyzed=pairs,
            asymmetric_elements=n_asymmetric,
            mean_optical_delta=round(sum(all_deltas) / max(len(all_deltas), 1), 1),
            max_optical_delta=round(max(all_deltas), 1) if all_deltas else 0.0,
            ref_deltas=ref_results,
            gen_deltas=gen_results,
            match_violations=violations,
            passed=len(violations) == 0,
            score_10=round(score, 1),
        )

    def _optical_centroid(self, crop: np.ndarray, label: str) -> OpticalCentroidResult:
        """Compute optical centroid via binary thresholding + image moments.

        CRITICAL FIX: Playwright screenshots are fully opaque (alpha=255).
        Using raw luminance weights the background as visual mass, collapsing
        the centroid to the geometric center. Instead, we threshold to isolate
        the foreground geometry, then compute moments on the binary mask.
        """
        import math
        h, w = crop.shape[:2]

        # Geometric center
        geo_cx = w / 2.0
        geo_cy = h / 2.0

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        # Isolate foreground via adaptive thresholding
        # THRESH_BINARY_INV: dark content on light bg → white mask
        # Also try OTSU for automatic threshold selection
        _, thresh_dark = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # For light content on dark bg, invert
        mean_val = gray.mean()
        if mean_val < 128:
            # Dark background — content is light pixels
            _, thresh_dark = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # cv2.moments on the binary foreground mask
        M = cv2.moments(thresh_dark)
        m00 = M["m00"] + 1e-8

        opt_cx = M["m10"] / m00
        opt_cy = M["m01"] / m00

        # Clamp to bounding box
        opt_cx = max(0.0, min(float(w), opt_cx))
        opt_cy = max(0.0, min(float(h), opt_cy))

        delta = math.sqrt((opt_cx - geo_cx) ** 2 + (opt_cy - geo_cy) ** 2)

        is_asym = self._is_asymmetric(crop)

        return OpticalCentroidResult(
            label=label,
            geo_center=(round(geo_cx, 1), round(geo_cy, 1)),
            optical_center=(round(opt_cx, 1), round(opt_cy, 1)),
            delta_px=round(delta, 1),
            is_asymmetric=is_asym,
        )

    @staticmethod
    def _is_asymmetric(crop: np.ndarray) -> bool:
        """Detect if the element shape is non-rectangular (asymmetric visual mass)."""
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return False

        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        rect_area = crop.shape[0] * crop.shape[1]

        if rect_area == 0:
            return False

        # If the contour fills less than 80% of the bounding rect, it's asymmetric
        fill_ratio = area / rect_area
        return fill_ratio < 0.80
