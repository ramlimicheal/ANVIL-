"""
ANVIL Cognitive Saliency — Attention map comparison via Spectral Residual.

Academic basis: Hou & Zhang (2007) Spectral Residual saliency.
Metric: Jensen-Shannon Divergence between reference and generated attention maps.

Catches: AI shifts visual attention away from the designer's intended focus point
(e.g., background noise stealing attention from the CTA button).

Dependencies: OpenCV cv2.saliency (built-in), numpy.
"""

from dataclasses import dataclass
from typing import Optional

try:
    import cv2
    import numpy as np
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


@dataclass
class SaliencyResult:
    """Saliency comparison result."""
    similarity: float          # 0.0-1.0 (1.0 = identical attention pattern)
    jsd: float                 # Jensen-Shannon Divergence (lower = better)
    ref_hotspot: tuple         # (x, y) peak attention in reference
    gen_hotspot: tuple         # (x, y) peak attention in generated
    hotspot_delta_px: float    # Euclidean distance between hotspots
    passed: bool
    score_10: float            # 0-10 ANVIL scale

    def violations_report(self) -> dict:
        violations = []
        if self.hotspot_delta_px > 50:
            violations.append({
                "issue": "attention_shift",
                "ref_focus": f"({self.ref_hotspot[0]}, {self.ref_hotspot[1]})",
                "gen_focus": f"({self.gen_hotspot[0]}, {self.gen_hotspot[1]})",
                "delta_px": round(self.hotspot_delta_px, 1),
                "fix_hint": "Primary attention point shifted. Check contrast, color weight, and element prominence near the focal area.",
            })
        if self.jsd > 0.15:
            violations.append({
                "issue": "attention_distribution_mismatch",
                "jsd": round(self.jsd, 4),
                "fix_hint": "Overall visual weight distribution differs. Check background noise, element sizing, and color contrast ratios.",
            })
        return {
            "saliency_similarity": self.similarity,
            "violations": violations,
            "passed": self.passed,
        }


class SaliencyComparator:
    """Compare cognitive attention maps between reference and generated screenshots."""

    def __init__(self):
        if not HAS_DEPS:
            raise ImportError("OpenCV required: pip install opencv-python")

    def compare(self, reference_path: str, generated_path: str) -> SaliencyResult:
        ref = cv2.imread(reference_path)
        gen = cv2.imread(generated_path)

        if ref is None:
            raise FileNotFoundError(f"Cannot read: {reference_path}")
        if gen is None:
            raise FileNotFoundError(f"Cannot read: {generated_path}")

        # Resize to match
        if ref.shape[:2] != gen.shape[:2]:
            gen = cv2.resize(gen, (ref.shape[1], ref.shape[0]))

        # Compute saliency maps
        ref_map = self._compute_saliency(ref)
        gen_map = self._compute_saliency(gen)

        # Find hotspots (peak attention points)
        ref_hotspot = self._find_hotspot(ref_map)
        gen_hotspot = self._find_hotspot(gen_map)

        import math
        hotspot_delta = math.sqrt(
            (ref_hotspot[0] - gen_hotspot[0]) ** 2 +
            (ref_hotspot[1] - gen_hotspot[1]) ** 2
        )

        # Jensen-Shannon Divergence
        jsd = self._jensen_shannon(ref_map, gen_map)
        similarity = max(0.0, 1.0 - jsd)

        return SaliencyResult(
            similarity=round(similarity, 4),
            jsd=round(jsd, 4),
            ref_hotspot=ref_hotspot,
            gen_hotspot=gen_hotspot,
            hotspot_delta_px=round(hotspot_delta, 1),
            passed=similarity >= 0.80,
            score_10=round(similarity * 10.0, 1),
        )

    def _compute_saliency(self, img: np.ndarray) -> np.ndarray:
        """Spectral Residual saliency detection."""
        # Try OpenCV's built-in saliency module first
        try:
            saliency_algo = cv2.saliency.StaticSaliencySpectralResidual_create()
            success, saliency_map = saliency_algo.computeSaliency(img)
            if success:
                return saliency_map.astype(np.float64)
        except (AttributeError, cv2.error):
            pass

        # Fallback: manual Spectral Residual implementation
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float64)
        # Resize for FFT efficiency
        small = cv2.resize(gray, (64, 64))

        # FFT
        spectrum = np.fft.fft2(small)
        log_amplitude = np.log1p(np.abs(spectrum))
        phase = np.angle(spectrum)

        # Spectral residual = log amplitude - smoothed log amplitude
        smoothed = cv2.blur(log_amplitude, (3, 3))
        residual = log_amplitude - smoothed

        # Reconstruct with residual amplitude and original phase
        saliency = np.abs(np.fft.ifft2(np.exp(residual + 1j * phase))) ** 2

        # Gaussian blur for final saliency map
        saliency = cv2.GaussianBlur(saliency, (9, 9), 2.5)

        # Resize back
        saliency = cv2.resize(saliency, (img.shape[1], img.shape[0]))
        return saliency

    def _find_hotspot(self, saliency_map: np.ndarray) -> tuple:
        """Find peak attention via largest connected cluster (not global average).

        FIX: Global weighted mean of bimodal attention (logo left + CTA right)
        averages to dead center on whitespace. Connected components isolates
        the single largest contiguous attention island.
        """
        threshold = np.percentile(saliency_map, 95)
        hot_mask = np.uint8(saliency_map >= threshold) * 255

        if hot_mask.sum() == 0:
            h, w = saliency_map.shape[:2]
            return (w // 2, h // 2)

        # Connected components: isolate distinct attention clusters
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(hot_mask)

        if num_labels <= 1:
            h, w = saliency_map.shape[:2]
            return (w // 2, h // 2)

        # Largest cluster by area (label 0 = background, skip it)
        largest_label = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        cx = int(centroids[largest_label][0])
        cy = int(centroids[largest_label][1])
        return (cx, cy)

    @staticmethod
    def _jensen_shannon(p_map: np.ndarray, q_map: np.ndarray) -> float:
        """Symmetric Jensen-Shannon Divergence between two saliency maps."""
        p = p_map.flatten().astype(np.float64)
        q = q_map.flatten().astype(np.float64)

        # Normalize to probability distributions
        p = p / (p.sum() + 1e-10)
        q = q / (q.sum() + 1e-10)

        m = 0.5 * (p + q)

        # KL(P||M) and KL(Q||M)
        kl_pm = np.sum(p * np.log((p + 1e-12) / (m + 1e-12)))
        kl_qm = np.sum(q * np.log((q + 1e-12) / (m + 1e-12)))

        jsd = 0.5 * (kl_pm + kl_qm)
        return max(0.0, min(1.0, jsd))
