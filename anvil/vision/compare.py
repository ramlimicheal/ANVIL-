"""
ANVIL Vision Compare — Mathematical image comparison for visual fidelity.

No neural networks. Pure signal processing:
- SSIM (Structural Similarity Index) — perceptual quality metric
- Region-based deviation mapping — identifies WHERE differences are
- Color histogram distance — verifies palette compliance at pixel level
- Edge structure comparison — verifies layout/borders match

All implemented with Pillow + standard math. No scikit-image dependency.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from pathlib import Path

try:
    from PIL import Image, ImageFilter, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


@dataclass
class RegionScore:
    """Score for a single grid region."""
    row: int
    col: int
    ssim: float
    label: str  # e.g., "sidebar", "chart-area", "header"
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0


@dataclass
class VisionResult:
    """Complete visual comparison result."""
    overall_ssim: float           # 0.0 - 1.0 (1.0 = identical)
    score: float                  # 0.0 - 10.0 (ANVIL scale)
    passed: bool                  # score >= 7.0
    color_distance: float         # 0.0 - 1.0 (0.0 = identical palettes)
    edge_similarity: float        # 0.0 - 1.0 (1.0 = identical structure)
    physics_score: float = 0.0
    physics_details: Dict[str, float] = field(default_factory=dict)
    semantic_score: float = 0.0   # Semantic/CLIP similarity (0-1)
    semantic_details: Dict = field(default_factory=dict)
    block_match_score: float = 0.0  # Element IoU matching (0-10)
    block_match_details: Dict = field(default_factory=dict)
    region_scores: List[RegionScore] = field(default_factory=list)
    worst_regions: List[str] = field(default_factory=list)
    diff_map_path: Optional[str] = None
    reference_size: Tuple[int, int] = (0, 0)
    generated_size: Tuple[int, int] = (0, 0)

    def summary(self) -> str:
        icon = "✅" if self.passed else "❌"
        lines = [
            f"ANVIL VISION ━━━ {icon} Score: {self.score}/10",
            f"  SSIM:       {self.overall_ssim:.4f} (structural similarity)",
            f"  Semantic:   {self.semantic_score:.4f} (CLIP/CV semantic match)",
            f"  BlockMatch: {self.block_match_score}/10 (element IoU)",
            f"  Physics:    {self.physics_score:.4f} (bloom/light decay)",
            f"  Color:      {1.0 - self.color_distance:.4f} (palette match)",
        ]
        if self.worst_regions:
            lines.append(f"  Worst:      {', '.join(self.worst_regions[:3])}")
        if self.diff_map_path:
            lines.append(f"  Diff map:   {self.diff_map_path}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    def violations_report(self) -> dict:
        """Machine-readable violations report for AI ingestion."""
        regions_failing = []
        for r in self.region_scores:
            if r.ssim < 0.85:
                # Add context mapping to help the AI map regions to code sections
                regions_failing.append({
                    "label": r.label,
                    "ssim": r.ssim,
                    "fix_hint": f"Structural or layout mismatch in region '{r.label}' (score: {r.ssim:.2f}). Adjust sizing, padding, or flex/grid alignment to match reference."
                })
        
        color_violations = []
        if self.color_distance > 0.05:
            color_violations.append({
                "issue": "palette_mismatch",
                "distance": self.color_distance,
                "fix_hint": f"Color distribution differs significantly from reference (distance: {self.color_distance:.3f}). Verify that the background and primary foreground colors perfectly match the design system tokens."
            })
            
        physics_violations = []
        if self.physics_score < 0.7 and self.physics_score > 0.0: # 0.0 usually means not run/skipped
             physics_violations.append({
                "issue": "lighting_physics_mismatch",
                "score": self.physics_score,
                "fix_hint": "Photometric analysis failed. Ensure drop shadows, gradients, and inner glows match the reference exactly in spread, blur, and opacity."
            })

        return {
            "overall_ssim": self.overall_ssim,
            "regions_failing": regions_failing,
            "color_violations": color_violations,
            "physics_violations": physics_violations
        }


class VisualComparator:
    """Compares two images using mathematical metrics."""

    def __init__(self, grid_rows: int = 4, grid_cols: int = 6):
        """
        Args:
            grid_rows: Number of rows for region analysis
            grid_cols: Number of columns for region analysis
        """
        if not HAS_PIL:
            raise ImportError("Pillow is required: pip install Pillow")
        self.grid_rows = grid_rows
        self.grid_cols = grid_cols

    def compare(
        self,
        reference_path: str,
        generated_path: str,
        diff_output_path: Optional[str] = None,
    ) -> VisionResult:
        """Compare reference and generated images.

        Args:
            reference_path: Path to reference screenshot (the target)
            generated_path: Path to generated screenshot (what we built)
            diff_output_path: Optional path to save visual diff map

        Returns:
            VisionResult with scores and analysis
        """
        ref_img = Image.open(reference_path).convert("RGB")
        gen_img = Image.open(generated_path).convert("RGB")

        # Resize generated to match reference dimensions
        if ref_img.size != gen_img.size:
            gen_img = gen_img.resize(ref_img.size, Image.LANCZOS)

        # 1. Global SSIM
        overall_ssim = self._compute_ssim(ref_img, gen_img)

        # 2. Edge structure comparison
        edge_sim = self._compare_edges(ref_img, gen_img)

        # 3. Color histogram distance
        color_dist = self._color_histogram_distance(ref_img, gen_img)

        # 4. Photonic Physics Gate
        physics_score = 0.0
        physics_res = {
            "TotalPhysics": 0.0, "VectorScore": 0.0,
            "BloomR2": 0.0, "SpecularMatch": 0.0,
            "Diagnostics": {"RefAngle": 0.0, "GenAngle": 0.0},
        }
        if HAS_CV2:
            try:
                from anvil.vision.physics import PhotonicVerifier
                print("  [ANVIL] Engaging Computational Photometry Gate...")
                ref_cv = cv2.imread(reference_path)
                gen_cv = cv2.imread(generated_path)

                if ref_cv is not None and gen_cv is not None:
                    if ref_cv.shape != gen_cv.shape:
                        gen_cv = cv2.resize(gen_cv, (ref_cv.shape[1], ref_cv.shape[0]))

                    photonic_gate = PhotonicVerifier(ref_cv, gen_cv)
                    physics_res = photonic_gate.evaluate()
                    physics_score = physics_res["TotalPhysics"]

                    # AXIOM CAGE: RIGID GATE FAILURES
                    if physics_res["VectorScore"] < 0.85:
                        print(f"  ❌ [AXIOM FAIL] Light Vector Mismatch. Ref: {physics_res['Diagnostics']['RefAngle']:.1f}°, Gen: {physics_res['Diagnostics']['GenAngle']:.1f}°")
                        physics_score = 0.0
                    if physics_res["BloomR2"] < 0.90:
                        print(f"  ❌ [AXIOM FAIL] Inverse-Square Violation: R^2 Fit ({physics_res['BloomR2']:.2f}).")
                        physics_score = 0.0
                    if physics_res["SpecularMatch"] < 0.50:
                        print(f"  ❌ [AXIOM FAIL] Specular Rim Light violation.")
                        physics_score = 0.0
            except ImportError:
                pass  # scipy not installed — skip physics gate

        # 5. Region-based analysis
        region_scores = self._region_analysis(ref_img, gen_img)

        # 6. Semantic Gate (CLIP or CV-based)
        semantic_score = 0.0
        semantic_details = {}
        try:
            from anvil.vision.semantic import SemanticComparator
            sem = SemanticComparator()
            sem_result = sem.compare(reference_path, generated_path)
            semantic_score = sem_result.overall_score
            semantic_details = {
                "method": sem_result.method,
                "phash": sem_result.phash_similarity,
                "hog": sem_result.hog_similarity,
                "color_lab": sem_result.color_similarity,
                "frequency": sem_result.frequency_similarity,
            }
        except Exception as e:
            semantic_details = {"error": str(e)}

        # 7. Block-Match Gate (Element IoU)
        block_match_score = 0.0
        block_match_details = {}
        try:
            from anvil.vision.block_match import BlockMatcher
            bm = BlockMatcher()
            bm_result = bm.match(reference_path, generated_path)
            block_match_score = bm_result.score
            block_match_details = bm_result.violations_report()
        except Exception as e:
            block_match_details = {"error": str(e)}

        # 8. Generate diff map
        diff_path = None
        if diff_output_path:
            diff_path = self._generate_diff_map(ref_img, gen_img, region_scores, diff_output_path)

        # Identify worst regions
        sorted_regions = sorted(region_scores, key=lambda r: r.ssim)
        worst = [f"{r.label} ({r.ssim:.2f})" for r in sorted_regions[:3] if r.ssim < 0.85]

        # Composite score: 6-layer weighted combination
        # SSIM (25%) + Semantic (20%) + Block-Match (20%) + Physics (15%) + Color (10%) + Edge (10%)
        bm_norm = block_match_score / 10.0  # normalize to 0-1
        raw = (
            overall_ssim * 0.25 +
            semantic_score * 0.20 +
            bm_norm * 0.20 +
            physics_score * 0.15 +
            (1.0 - color_dist) * 0.10 +
            edge_sim * 0.10
        ) * 10.0
        score = max(0.0, min(10.0, round(raw, 1)))

        return VisionResult(
            overall_ssim=round(overall_ssim, 4),
            score=score,
            passed=score >= 7.0,
            color_distance=round(color_dist, 4),
            edge_similarity=round(edge_sim, 4),
            physics_score=round(physics_score, 4),
            physics_details=physics_res,
            semantic_score=round(semantic_score, 4),
            semantic_details=semantic_details,
            block_match_score=round(block_match_score, 1),
            block_match_details=block_match_details,
            region_scores=region_scores,
            worst_regions=worst,
            diff_map_path=diff_path,
            reference_size=ref_img.size,
            generated_size=gen_img.size,
        )

    def _compute_ssim(
        self,
        img1: "Image.Image",
        img2: "Image.Image",
        window_size: int = 11,
    ) -> float:
        """Compute SSIM (Structural Similarity Index) between two images.

        Implementation follows Wang et al. 2004 paper.
        Uses luminance channel only for structural comparison.
        """
        # Convert to grayscale
        g1 = img1.convert("L")
        g2 = img2.convert("L")

        w, h = g1.size
        if w < window_size or h < window_size:
            return 0.0

        # Get pixel data
        p1 = list(g1.getdata())
        p2 = list(g2.getdata())

        # Constants (from SSIM paper)
        L = 255  # dynamic range
        K1, K2 = 0.01, 0.03
        C1 = (K1 * L) ** 2
        C2 = (K2 * L) ** 2

        # Compute SSIM over a grid of sample windows for speed
        step = max(window_size, min(w, h) // 20)
        ssim_values = []

        for y in range(0, h - window_size, step):
            for x in range(0, w - window_size, step):
                # Extract windows
                win1 = []
                win2 = []
                for wy in range(window_size):
                    for wx in range(window_size):
                        idx = (y + wy) * w + (x + wx)
                        win1.append(p1[idx])
                        win2.append(p2[idx])

                n = len(win1)
                mu1 = sum(win1) / n
                mu2 = sum(win2) / n

                var1 = sum((v - mu1) ** 2 for v in win1) / n
                var2 = sum((v - mu2) ** 2 for v in win2) / n
                cov = sum((a - mu1) * (b - mu2) for a, b in zip(win1, win2)) / n

                num = (2 * mu1 * mu2 + C1) * (2 * cov + C2)
                den = (mu1 ** 2 + mu2 ** 2 + C1) * (var1 + var2 + C2)

                ssim_values.append(num / den if den != 0 else 0)

        return sum(ssim_values) / len(ssim_values) if ssim_values else 0.0

    def _compare_edges(self, img1: "Image.Image", img2: "Image.Image") -> float:
        """Compare edge structures using Sobel-like filter.

        This catches layout/border differences that SSIM might average out.
        """
        # Apply edge detection
        e1 = img1.convert("L").filter(ImageFilter.FIND_EDGES)
        e2 = img2.convert("L").filter(ImageFilter.FIND_EDGES)

        # Compute correlation of edge maps
        p1 = list(e1.getdata())
        p2 = list(e2.getdata())

        # Sample for speed (every 4th pixel)
        step = 4
        n = len(range(0, len(p1), step))
        if n == 0:
            return 0.0

        # Normalized cross-correlation
        mean1 = sum(p1[i] for i in range(0, len(p1), step)) / n
        mean2 = sum(p2[i] for i in range(0, len(p2), step)) / n

        num = 0.0
        den1 = 0.0
        den2 = 0.0

        for i in range(0, len(p1), step):
            d1 = p1[i] - mean1
            d2 = p2[i] - mean2
            num += d1 * d2
            den1 += d1 ** 2
            den2 += d2 ** 2

        denom = math.sqrt(den1 * den2)
        if denom == 0:
            return 1.0 if den1 == 0 and den2 == 0 else 0.0

        return max(0.0, num / denom)

    def _color_histogram_distance(self, img1: "Image.Image", img2: "Image.Image") -> float:
        """Compute normalized color histogram distance (Bhattacharyya).

        Lower = more similar palettes at the pixel level.
        """
        h1_r = img1.histogram()[:256]
        h1_g = img1.histogram()[256:512]
        h1_b = img1.histogram()[512:768]

        h2_r = img2.histogram()[:256]
        h2_g = img2.histogram()[256:512]
        h2_b = img2.histogram()[512:768]

        def bhattacharyya(h1: list, h2: list) -> float:
            total1 = sum(h1) or 1
            total2 = sum(h2) or 1
            bc = sum(
                math.sqrt((a / total1) * (b / total2))
                for a, b in zip(h1, h2)
            )
            # Bhattacharyya distance
            return -math.log(max(bc, 1e-10)) if bc < 1.0 else 0.0

        dist_r = bhattacharyya(h1_r, h2_r)
        dist_g = bhattacharyya(h1_g, h2_g)
        dist_b = bhattacharyya(h1_b, h2_b)

        # Normalize to 0-1 range (typical max ~3.0)
        avg_dist = (dist_r + dist_g + dist_b) / 3.0
        return min(1.0, avg_dist / 2.0)

    def _region_analysis(
        self,
        img1: "Image.Image",
        img2: "Image.Image",
    ) -> List[RegionScore]:
        """Divide images into grid and compute per-region SSIM."""
        w, h = img1.size
        rw = w // self.grid_cols
        rh = h // self.grid_rows
        results = []

        # Semantic labels based on typical dashboard layout
        label_map = self._generate_labels()

        for row in range(self.grid_rows):
            for col in range(self.grid_cols):
                x1 = col * rw
                y1 = row * rh
                x2 = min(x1 + rw, w)
                y2 = min(y1 + rh, h)

                region1 = img1.crop((x1, y1, x2, y2))
                region2 = img2.crop((x1, y1, x2, y2))

                ssim = self._compute_ssim(region1, region2, window_size=7)
                label = label_map.get((row, col), f"R{row}C{col}")

                results.append(RegionScore(
                    row=row, col=col, ssim=round(ssim, 4),
                    label=label, x=x1, y=y1, w=x2 - x1, h=y2 - y1,
                ))

        return results

    def _generate_labels(self) -> Dict[Tuple[int, int], str]:
        """Generate semantic labels for grid regions based on typical dashboard layout."""
        labels = {}
        for row in range(self.grid_rows):
            for col in range(self.grid_cols):
                if col == 0:
                    labels[(row, col)] = "sidebar"
                elif row == 0:
                    labels[(row, col)] = f"header-{col}"
                elif row == 1:
                    labels[(row, col)] = f"stat-card-{col}"
                elif row == 2:
                    if col <= 3:
                        labels[(row, col)] = f"chart-area-{col}"
                    else:
                        labels[(row, col)] = f"revenue-{col}"
                else:
                    labels[(row, col)] = f"table-{col}"
        return labels

    def _generate_diff_map(
        self,
        img1: "Image.Image",
        img2: "Image.Image",
        regions: List[RegionScore],
        output_path: str,
    ) -> str:
        """Generate a visual diff map showing where images differ.

        - Green overlay = high similarity (>0.9 SSIM)
        - Yellow overlay = moderate difference (0.7-0.9)
        - Red overlay = significant difference (<0.7)
        """
        w, h = img1.size
        # Create diff base from reference with reduced opacity
        diff = img1.copy()
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        for region in regions:
            if region.ssim >= 0.90:
                color = (0, 200, 0, 40)     # Green: good match
            elif region.ssim >= 0.70:
                color = (255, 200, 0, 60)    # Yellow: moderate diff
            else:
                color = (255, 0, 0, 80)      # Red: poor match

            draw.rectangle(
                [region.x, region.y, region.x + region.w, region.y + region.h],
                fill=color,
                outline=(255, 255, 255, 100),
                width=2,
            )

            # Add SSIM score text
            try:
                draw.text(
                    (region.x + 4, region.y + 4),
                    f"{region.ssim:.2f}",
                    fill=(255, 255, 255, 200),
                )
            except Exception:
                pass  # Font rendering may fail on some systems

        # Composite
        diff = diff.convert("RGBA")
        diff = Image.alpha_composite(diff, overlay)
        diff.save(output_path, "PNG")
        return output_path
