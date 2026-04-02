"""
ANVIL Semantic Gate — CLIP-equivalent semantic similarity without PyTorch.

Academic basis: Design2Code (Stanford SALT, 2024) uses CLIP ViT cosine similarity.
CANVAS (AAAI 2025) uses hierarchical feature/pattern/object evaluation.

Since PyTorch/transformers are not installed, this implements a multi-layer
semantic comparison using pure OpenCV + numpy that captures the same signal:

Layer 1: Perceptual Hash (pHash) — global structure fingerprint
Layer 2: HOG (Histogram of Oriented Gradients) — layout pattern matching
Layer 3: Color Distribution in Lab Space — palette semantic alignment
Layer 4: Spatial Frequency Spectrum — texture/density matching via DCT

When PyTorch becomes available, this module auto-upgrades to real CLIP.

Dependencies: OpenCV (cv2), numpy (already in ANVIL venv).
"""

import math
from dataclasses import dataclass
from typing import Tuple

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# Check for optional CLIP (auto-upgrade path)
try:
    import torch
    from transformers import CLIPProcessor, CLIPModel
    HAS_CLIP = True
except ImportError:
    HAS_CLIP = False


@dataclass
class SemanticResult:
    """Result of semantic similarity comparison."""
    overall_score: float       # 0.0 - 1.0 (1.0 = semantically identical)
    phash_similarity: float    # Perceptual hash hamming distance
    hog_similarity: float      # HOG descriptor cosine similarity
    color_similarity: float    # Lab-space distribution similarity
    frequency_similarity: float  # DCT spectrum correlation
    method: str                # "clip" or "cv_semantic"
    score_10: float            # 0-10 ANVIL scale

    def violations_report(self) -> dict:
        """Machine-readable violations for AI ingestion."""
        violations = []
        if self.phash_similarity < 0.85:
            violations.append({
                "layer": "structure",
                "score": self.phash_similarity,
                "fix_hint": "Overall page structure doesn't match. Check major layout sections (header/sidebar/main/footer).",
            })
        if self.hog_similarity < 0.80:
            violations.append({
                "layer": "layout_patterns",
                "score": self.hog_similarity,
                "fix_hint": "Layout patterns (edge orientations, element arrangements) differ. Check flex/grid alignment and element grouping.",
            })
        if self.color_similarity < 0.85:
            violations.append({
                "layer": "color_semantics",
                "score": self.color_similarity,
                "fix_hint": "Color distribution doesn't match semantically. Verify dark/light balance and accent color usage.",
            })
        if self.frequency_similarity < 0.80:
            violations.append({
                "layer": "texture_density",
                "score": self.frequency_similarity,
                "fix_hint": "Texture/density mismatch. Check text density, spacing between elements, and background patterns.",
            })
        return {
            "semantic_score": self.overall_score,
            "method": self.method,
            "violations": violations,
        }


class SemanticComparator:
    """Multi-layer semantic similarity comparison.

    Auto-upgrades to real CLIP when PyTorch is available.
    Falls back to pure-CV semantic analysis otherwise.
    """

    def __init__(self, target_size: int = 224):
        """
        Args:
            target_size: Image resize target for comparison (224 = CLIP standard)
        """
        if not HAS_CV2:
            raise ImportError("OpenCV required: pip install opencv-python")
        self.target_size = target_size

    def compare(
        self,
        reference_path: str,
        generated_path: str,
    ) -> SemanticResult:
        """Compare semantic similarity between reference and generated images.

        Auto-selects CLIP (if available) or CV-based semantic analysis.
        """
        if HAS_CLIP:
            return self._compare_clip(reference_path, generated_path)
        else:
            return self._compare_cv(reference_path, generated_path)

    # ─── CLIP Path (auto-upgrade when PyTorch available) ─────

    def _compare_clip(self, ref_path: str, gen_path: str) -> SemanticResult:
        """Real CLIP ViT cosine similarity."""
        from PIL import Image

        model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

        ref_img = Image.open(ref_path).convert("RGB")
        gen_img = Image.open(gen_path).convert("RGB")

        inputs = processor(
            images=[ref_img, gen_img],
            return_tensors="pt",
            padding=True,
        )

        with torch.no_grad():
            features = model.get_image_features(**inputs)
            features = features / features.norm(dim=-1, keepdim=True)
            similarity = torch.nn.functional.cosine_similarity(
                features[0].unsqueeze(0),
                features[1].unsqueeze(0),
            ).item()

        # Normalize from [-1, 1] to [0, 1]
        score = (similarity + 1.0) / 2.0

        return SemanticResult(
            overall_score=round(score, 4),
            phash_similarity=score,  # CLIP subsumes these
            hog_similarity=score,
            color_similarity=score,
            frequency_similarity=score,
            method="clip",
            score_10=round(score * 10.0, 1),
        )

    # ─── Pure CV Path (no PyTorch) ───────────────────────────

    def _compare_cv(self, ref_path: str, gen_path: str) -> SemanticResult:
        """Multi-layer semantic comparison using pure OpenCV."""
        ref_img = cv2.imread(ref_path)
        gen_img = cv2.imread(gen_path)

        if ref_img is None:
            raise FileNotFoundError(f"Cannot read: {ref_path}")
        if gen_img is None:
            raise FileNotFoundError(f"Cannot read: {gen_path}")

        # Resize both to standard size
        ref = cv2.resize(ref_img, (self.target_size, self.target_size))
        gen = cv2.resize(gen_img, (self.target_size, self.target_size))

        # Layer 1: Perceptual Hash
        phash_sim = self._perceptual_hash_similarity(ref, gen)

        # Layer 2: HOG descriptor similarity
        hog_sim = self._hog_similarity(ref, gen)

        # Layer 3: Lab-space color distribution
        color_sim = self._lab_color_distribution_similarity(ref, gen)

        # Layer 4: DCT frequency spectrum
        freq_sim = self._frequency_similarity(ref, gen)

        # Weighted composite — HOG and pHash are strongest for UI layout
        overall = (
            phash_sim * 0.25 +
            hog_sim * 0.30 +
            color_sim * 0.25 +
            freq_sim * 0.20
        )

        return SemanticResult(
            overall_score=round(overall, 4),
            phash_similarity=round(phash_sim, 4),
            hog_similarity=round(hog_sim, 4),
            color_similarity=round(color_sim, 4),
            frequency_similarity=round(freq_sim, 4),
            method="cv_semantic",
            score_10=round(overall * 10.0, 1),
        )

    def _perceptual_hash_similarity(
        self,
        img1: np.ndarray,
        img2: np.ndarray,
        hash_size: int = 32,
    ) -> float:
        """Perceptual hash using DCT (pHash algorithm).

        More robust than average hash. Captures structural "fingerprint"
        of the image that's invariant to minor color/brightness changes.
        """
        def _phash(img: np.ndarray) -> np.ndarray:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            resized = cv2.resize(gray, (hash_size, hash_size), interpolation=cv2.INTER_AREA)
            dct = cv2.dct(resized.astype(np.float32))
            # Use top-left 8×8 low-frequency coefficients
            low_freq = dct[:8, :8]
            median = np.median(low_freq)
            return (low_freq > median).flatten()

        h1 = _phash(img1)
        h2 = _phash(img2)

        # Hamming distance → similarity
        hamming = np.sum(h1 != h2)
        max_bits = len(h1)
        return 1.0 - (hamming / max_bits)

    def _hog_similarity(self, img1: np.ndarray, img2: np.ndarray) -> float:
        """HOG (Histogram of Oriented Gradients) cosine similarity.

        Captures the dominant edge orientations and spatial layout patterns.
        Robust to color changes — focuses purely on structure.
        """
        def _compute_hog(img: np.ndarray) -> np.ndarray:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            resized = cv2.resize(gray, (128, 128))

            # Compute gradients
            gx = cv2.Sobel(resized, cv2.CV_64F, 1, 0, ksize=3)
            gy = cv2.Sobel(resized, cv2.CV_64F, 0, 1, ksize=3)

            magnitude = np.sqrt(gx**2 + gy**2)
            angle = np.arctan2(gy, gx) * 180.0 / np.pi
            angle[angle < 0] += 180.0

            # Build histogram: 9 orientation bins, 16×16 cells
            n_bins = 9
            cell_size = 16
            h, w = resized.shape
            n_cells_y = h // cell_size
            n_cells_x = w // cell_size

            hog_descriptor = []
            for cy in range(n_cells_y):
                for cx in range(n_cells_x):
                    y1 = cy * cell_size
                    x1 = cx * cell_size
                    cell_mag = magnitude[y1:y1+cell_size, x1:x1+cell_size]
                    cell_ang = angle[y1:y1+cell_size, x1:x1+cell_size]

                    hist = np.zeros(n_bins)
                    for m, a in zip(cell_mag.flatten(), cell_ang.flatten()):
                        bin_idx = int(a / 20.0) % n_bins
                        hist[bin_idx] += m
                    hog_descriptor.extend(hist)

            desc = np.array(hog_descriptor)
            norm = np.linalg.norm(desc)
            return desc / max(norm, 1e-8)

        h1 = _compute_hog(img1)
        h2 = _compute_hog(img2)

        # Cosine similarity
        dot = np.dot(h1, h2)
        return float(np.clip(dot, 0.0, 1.0))

    def _lab_color_distribution_similarity(
        self,
        img1: np.ndarray,
        img2: np.ndarray,
        n_bins: int = 32,
    ) -> float:
        """Compare color distributions in Lab space using histogram intersection.

        Lab space separates luminance from chromaticity, matching human
        color perception better than RGB histograms.
        """
        lab1 = cv2.cvtColor(img1, cv2.COLOR_BGR2Lab)
        lab2 = cv2.cvtColor(img2, cv2.COLOR_BGR2Lab)

        similarities = []
        for ch in range(3):  # L, a, b channels
            h1 = cv2.calcHist([lab1], [ch], None, [n_bins], [0, 256])
            h2 = cv2.calcHist([lab2], [ch], None, [n_bins], [0, 256])

            # Normalize
            cv2.normalize(h1, h1)
            cv2.normalize(h2, h2)

            # Histogram intersection (Swain & Ballard)
            intersection = cv2.compareHist(h1, h2, cv2.HISTCMP_INTERSECT)
            similarities.append(float(intersection))

        return sum(similarities) / len(similarities)

    def _frequency_similarity(self, img1: np.ndarray, img2: np.ndarray) -> float:
        """Compare spatial frequency spectra via 2D DCT.

        Captures texture density and repetitive patterns (grids, cards, lists).
        Low frequencies = major layout blocks.
        High frequencies = text density, borders, fine details.
        """
        def _freq_descriptor(img: np.ndarray, size: int = 64) -> np.ndarray:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            resized = cv2.resize(gray, (size, size)).astype(np.float32)
            dct = cv2.dct(resized)
            # Log magnitude for better dynamic range
            log_mag = np.log1p(np.abs(dct))
            # Flatten top-left quadrant (dominant frequencies)
            half = size // 2
            desc = log_mag[:half, :half].flatten()
            norm = np.linalg.norm(desc)
            return desc / max(norm, 1e-8)

        f1 = _freq_descriptor(img1)
        f2 = _freq_descriptor(img2)

        # Cosine similarity
        dot = np.dot(f1, f2)
        return float(np.clip(dot, 0.0, 1.0))
