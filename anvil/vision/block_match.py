"""
ANVIL Block-Match — Per-element visual fidelity via bounding box IoU.

Academic basis: Design2Code (Stanford SALT, 2024) + LayoutCoder (ISSTA 2025).

Pipeline:
  1. Detect visual blocks via adaptive thresholding + connected components
  2. Filter noise (min area, aspect ratio)
  3. Match reference blocks to generated blocks by IoU (Hungarian algorithm)
  4. Per-matched-pair: measure position delta, size delta, color delta (CIEDE2000)
  5. Return per-element violations with fix hints

Dependencies: OpenCV (cv2), numpy, scipy (already in ANVIL venv).
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

try:
    import cv2
    import numpy as np
    from scipy.optimize import linear_sum_assignment
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


@dataclass
class VisualBlock:
    """A detected visual element with bounding box and color stats."""
    x: int
    y: int
    w: int
    h: int
    area: int
    mean_color_bgr: Tuple[int, int, int]
    label: str = ""

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0

    @property
    def bbox(self) -> Tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.w, self.y + self.h)


@dataclass
class ElementMatch:
    """A matched pair of reference and generated blocks."""
    ref_block: VisualBlock
    gen_block: VisualBlock
    iou: float
    position_delta_px: float   # Euclidean distance of centers
    size_delta_pct: float      # % difference in area
    color_delta_e: float       # CIEDE2000 perceptual color distance
    passed: bool = True
    fix_hint: str = ""


@dataclass
class BlockMatchResult:
    """Complete block-matching analysis result."""
    ref_blocks_count: int
    gen_blocks_count: int
    matched_count: int
    unmatched_ref: int          # Elements in reference not found in generated
    unmatched_gen: int          # Extra elements in generated not in reference
    element_recall: float       # matched / ref_blocks
    mean_iou: float
    mean_position_delta: float
    mean_color_delta: float
    matches: List[ElementMatch] = field(default_factory=list)
    missing_elements: List[VisualBlock] = field(default_factory=list)
    extra_elements: List[VisualBlock] = field(default_factory=list)
    score: float = 0.0         # 0-10 ANVIL scale

    def violations_report(self) -> dict:
        """Machine-readable violations for AI ingestion."""
        failing_matches = []
        for m in self.matches:
            issues = []
            if m.iou < 0.7:
                issues.append(f"position/size mismatch (IoU={m.iou:.2f})")
            if m.position_delta_px > 10:
                issues.append(f"shifted {m.position_delta_px:.0f}px from reference")
            if m.size_delta_pct > 15:
                issues.append(f"size differs by {m.size_delta_pct:.0f}%")
            if m.color_delta_e > 5.0:
                issues.append(f"color ΔE={m.color_delta_e:.1f}")
            if issues:
                failing_matches.append({
                    "ref_position": f"({m.ref_block.x}, {m.ref_block.y})",
                    "ref_size": f"{m.ref_block.w}×{m.ref_block.h}",
                    "gen_position": f"({m.gen_block.x}, {m.gen_block.y})",
                    "gen_size": f"{m.gen_block.w}×{m.gen_block.h}",
                    "iou": m.iou,
                    "issues": issues,
                    "fix_hint": m.fix_hint,
                })

        missing = []
        for b in self.missing_elements:
            missing.append({
                "position": f"({b.x}, {b.y})",
                "size": f"{b.w}×{b.h}",
                "fix_hint": f"Element at ({b.x},{b.y}) size {b.w}×{b.h} exists in reference but missing in generated output.",
            })

        return {
            "element_recall": self.element_recall,
            "mean_iou": self.mean_iou,
            "failing_elements": failing_matches,
            "missing_elements": missing,
            "extra_elements_count": self.unmatched_gen,
            "score": self.score,
        }


class BlockMatcher:
    """Detects and matches visual blocks between reference and generated images."""

    def __init__(
        self,
        min_area_pct: float = 0.001,
        max_area_pct: float = 0.5,
        iou_threshold: float = 0.3,
    ):
        """
        Args:
            min_area_pct: Minimum block area as % of image area (filters noise)
            max_area_pct: Maximum block area as % of image area (filters full-page blocks)
            iou_threshold: Minimum IoU to consider a match valid
        """
        if not HAS_DEPS:
            raise ImportError("OpenCV + numpy + scipy required for BlockMatcher")
        self.min_area_pct = min_area_pct
        self.max_area_pct = max_area_pct
        self.iou_threshold = iou_threshold

    def match(
        self,
        reference_path: str,
        generated_path: str,
    ) -> BlockMatchResult:
        """Detect and match visual blocks between two screenshots.

        Args:
            reference_path: Path to reference screenshot
            generated_path: Path to generated screenshot

        Returns:
            BlockMatchResult with per-element analysis
        """
        ref_img = cv2.imread(reference_path)
        gen_img = cv2.imread(generated_path)

        if ref_img is None:
            raise FileNotFoundError(f"Cannot read reference: {reference_path}")
        if gen_img is None:
            raise FileNotFoundError(f"Cannot read generated: {generated_path}")

        # Resize generated to match reference
        if ref_img.shape[:2] != gen_img.shape[:2]:
            gen_img = cv2.resize(gen_img, (ref_img.shape[1], ref_img.shape[0]))

        # 1. Detect blocks in both images
        ref_blocks = self._detect_blocks(ref_img)
        gen_blocks = self._detect_blocks(gen_img)

        if not ref_blocks or not gen_blocks:
            return BlockMatchResult(
                ref_blocks_count=len(ref_blocks),
                gen_blocks_count=len(gen_blocks),
                matched_count=0,
                unmatched_ref=len(ref_blocks),
                unmatched_gen=len(gen_blocks),
                element_recall=0.0,
                mean_iou=0.0,
                mean_position_delta=0.0,
                mean_color_delta=0.0,
                missing_elements=ref_blocks,
                score=0.0,
            )

        # 2. Build IoU cost matrix
        cost_matrix = np.zeros((len(ref_blocks), len(gen_blocks)))
        for i, rb in enumerate(ref_blocks):
            for j, gb in enumerate(gen_blocks):
                iou = self._compute_iou(rb.bbox, gb.bbox)
                cost_matrix[i, j] = 1.0 - iou  # Hungarian minimizes cost

        # 3. Hungarian algorithm for optimal assignment
        ref_indices, gen_indices = linear_sum_assignment(cost_matrix)

        # 4. Build matches
        matches = []
        matched_ref = set()
        matched_gen = set()

        for ri, gi in zip(ref_indices, gen_indices):
            iou = 1.0 - cost_matrix[ri, gi]
            if iou < self.iou_threshold:
                continue  # Below threshold — not a valid match

            rb = ref_blocks[ri]
            gb = gen_blocks[gi]
            matched_ref.add(ri)
            matched_gen.add(gi)

            # Position delta (center-to-center Euclidean)
            pos_delta = math.sqrt((rb.cx - gb.cx) ** 2 + (rb.cy - gb.cy) ** 2)

            # Size delta (area percentage difference)
            size_delta = abs(rb.area - gb.area) / max(rb.area, 1) * 100.0

            # Color delta (CIEDE2000)
            color_de = self._ciede2000_bgr(rb.mean_color_bgr, gb.mean_color_bgr)

            # Generate fix hint
            hints = []
            if pos_delta > 10:
                dx = gb.cx - rb.cx
                dy = gb.cy - rb.cy
                direction = []
                if abs(dx) > 5:
                    direction.append(f"{'right' if dx > 0 else 'left'} by {abs(dx):.0f}px")
                if abs(dy) > 5:
                    direction.append(f"{'down' if dy > 0 else 'up'} by {abs(dy):.0f}px")
                hints.append(f"Element shifted {', '.join(direction)}. Adjust margin/padding.")
            if size_delta > 15:
                hints.append(f"Size off by {size_delta:.0f}%. Check width/height/padding.")
            if color_de > 5.0:
                hints.append(f"Color mismatch ΔE={color_de:.1f}. Verify background/border-color.")

            passed = iou >= 0.7 and pos_delta <= 10 and color_de <= 5.0
            fix_hint = " | ".join(hints) if hints else "Element matches reference."

            matches.append(ElementMatch(
                ref_block=rb,
                gen_block=gb,
                iou=round(iou, 3),
                position_delta_px=round(pos_delta, 1),
                size_delta_pct=round(size_delta, 1),
                color_delta_e=round(color_de, 1),
                passed=passed,
                fix_hint=fix_hint,
            ))

        # 5. Identify unmatched
        missing = [ref_blocks[i] for i in range(len(ref_blocks)) if i not in matched_ref]
        extra = [gen_blocks[i] for i in range(len(gen_blocks)) if i not in matched_gen]

        # 6. Compute aggregate stats
        matched_count = len(matches)
        recall = matched_count / max(len(ref_blocks), 1)
        mean_iou = sum(m.iou for m in matches) / max(matched_count, 1)
        mean_pos = sum(m.position_delta_px for m in matches) / max(matched_count, 1)
        mean_color = sum(m.color_delta_e for m in matches) / max(matched_count, 1)

        # Score: weighted combination
        # Recall (40%) + Mean IoU (30%) + Position accuracy (15%) + Color accuracy (15%)
        pos_score = max(0.0, 1.0 - mean_pos / 50.0)  # 50px+ = 0 score
        color_score = max(0.0, 1.0 - mean_color / 20.0)  # ΔE 20+ = 0 score
        raw = (recall * 0.4 + mean_iou * 0.3 + pos_score * 0.15 + color_score * 0.15) * 10.0
        score = round(max(0.0, min(10.0, raw)), 1)

        return BlockMatchResult(
            ref_blocks_count=len(ref_blocks),
            gen_blocks_count=len(gen_blocks),
            matched_count=matched_count,
            unmatched_ref=len(missing),
            unmatched_gen=len(extra),
            element_recall=round(recall, 3),
            mean_iou=round(mean_iou, 3),
            mean_position_delta=round(mean_pos, 1),
            mean_color_delta=round(mean_color, 1),
            matches=matches,
            missing_elements=missing,
            extra_elements=extra,
            score=score,
        )

    def _detect_blocks(self, img: np.ndarray) -> List[VisualBlock]:
        """Detect visual blocks using edge detection + connected components.

        Uses Canny edge detection → morphological closing → connected components.
        This is more robust than simple thresholding for UI elements with
        varying backgrounds (dark mode, gradients).
        """
        h, w = img.shape[:2]
        total_area = h * w
        min_area = int(total_area * self.min_area_pct)
        max_area = int(total_area * self.max_area_pct)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Adaptive edge detection
        edges = cv2.Canny(gray, 30, 100)

        # Morphological closing to connect nearby edges into solid blocks
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=3)

        # Fill enclosed regions
        # Flood fill from borders to find background, then invert
        flood = closed.copy()
        mask = np.zeros((h + 2, w + 2), np.uint8)
        cv2.floodFill(flood, mask, (0, 0), 255)
        filled = cv2.bitwise_not(flood) | closed

        # Connected components
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
            filled, connectivity=8
        )

        blocks = []
        for i in range(1, num_labels):  # Skip background (label 0)
            x = stats[i, cv2.CC_STAT_LEFT]
            y = stats[i, cv2.CC_STAT_TOP]
            bw = stats[i, cv2.CC_STAT_WIDTH]
            bh = stats[i, cv2.CC_STAT_HEIGHT]
            area = stats[i, cv2.CC_STAT_AREA]

            # Filter by area
            if area < min_area or area > max_area:
                continue

            # Filter degenerate aspect ratios (lines, noise)
            aspect = max(bw, bh) / max(min(bw, bh), 1)
            if aspect > 20:
                continue

            # Extract mean color of the block region
            block_mask = (labels[y:y+bh, x:x+bw] == i).astype(np.uint8)
            region = img[y:y+bh, x:x+bw]
            if block_mask.sum() > 0:
                mean_b = np.mean(region[:,:,0][block_mask > 0])
                mean_g = np.mean(region[:,:,1][block_mask > 0])
                mean_r = np.mean(region[:,:,2][block_mask > 0])
                mean_color = (int(mean_b), int(mean_g), int(mean_r))
            else:
                mean_color = (0, 0, 0)

            blocks.append(VisualBlock(
                x=x, y=y, w=bw, h=bh, area=area,
                mean_color_bgr=mean_color,
            ))

        # Sort by area descending (largest structural elements first)
        blocks.sort(key=lambda b: b.area, reverse=True)

        # Cap at 100 blocks to avoid noise explosion
        return blocks[:100]

    @staticmethod
    def _compute_iou(
        box1: Tuple[int, int, int, int],
        box2: Tuple[int, int, int, int],
    ) -> float:
        """Compute Intersection over Union between two bounding boxes.
        Box format: (x1, y1, x2, y2).
        """
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])

        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - inter

        return inter / max(union, 1)

    @staticmethod
    def _ciede2000_bgr(
        bgr1: Tuple[int, int, int],
        bgr2: Tuple[int, int, int],
    ) -> float:
        """Compute CIEDE2000 color distance between two BGR colors.

        Converts BGR→Lab then applies the CIEDE2000 formula.
        Simplified implementation covering the core terms.
        """
        # BGR to Lab via OpenCV
        c1 = np.uint8([[list(bgr1)]])
        c2 = np.uint8([[list(bgr2)]])
        lab1 = cv2.cvtColor(c1, cv2.COLOR_BGR2Lab).astype(np.float64)[0][0]
        lab2 = cv2.cvtColor(c2, cv2.COLOR_BGR2Lab).astype(np.float64)[0][0]

        # OpenCV Lab ranges: L [0,255], a [0,255], b [0,255]
        # Convert to standard Lab: L [0,100], a [-128,127], b [-128,127]
        L1, a1, b1 = lab1[0] * 100 / 255, lab1[1] - 128, lab1[2] - 128
        L2, a2, b2 = lab2[0] * 100 / 255, lab2[1] - 128, lab2[2] - 128

        # Chroma
        C1 = math.sqrt(a1**2 + b1**2)
        C2 = math.sqrt(a2**2 + b2**2)
        C_avg = (C1 + C2) / 2.0

        # G factor
        C_avg_7 = C_avg**7
        G = 0.5 * (1.0 - math.sqrt(C_avg_7 / (C_avg_7 + 25.0**7)))

        a1p = a1 * (1.0 + G)
        a2p = a2 * (1.0 + G)

        C1p = math.sqrt(a1p**2 + b1**2)
        C2p = math.sqrt(a2p**2 + b2**2)

        h1p = math.degrees(math.atan2(b1, a1p)) % 360
        h2p = math.degrees(math.atan2(b2, a2p)) % 360

        dLp = L2 - L1
        dCp = C2p - C1p

        if C1p * C2p == 0:
            dhp = 0
        elif abs(h2p - h1p) <= 180:
            dhp = h2p - h1p
        elif h2p - h1p > 180:
            dhp = h2p - h1p - 360
        else:
            dhp = h2p - h1p + 360

        dHp = 2.0 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2.0))

        # Weighting functions
        L_avg = (L1 + L2) / 2.0
        C_avgp = (C1p + C2p) / 2.0

        SL = 1.0 + 0.015 * (L_avg - 50.0)**2 / math.sqrt(20.0 + (L_avg - 50.0)**2)
        SC = 1.0 + 0.045 * C_avgp
        T = (1.0
             - 0.17 * math.cos(math.radians(h1p - 30))
             + 0.24 * math.cos(math.radians(2 * h1p))
             + 0.32 * math.cos(math.radians(3 * h1p + 6))
             - 0.20 * math.cos(math.radians(4 * h1p - 63)))
        SH = 1.0 + 0.015 * C_avgp * T

        dE = math.sqrt(
            (dLp / SL)**2 + (dCp / SC)**2 + (dHp / SH)**2
        )
        return dE
