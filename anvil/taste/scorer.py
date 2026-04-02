"""
TASTE Scorer — Aesthetic quality scoring via color harmony analysis.
Pure math, no GPU. Based on color theory fundamentals.
"""

import colorsys
import math
from typing import Dict, List, Tuple
from .tensor import StyleTensor


class AestheticScorer:
    """Scores aesthetic quality of a color palette."""

    def score_palette(self, colors: List[str]) -> dict:
        hsv_colors = []
        for c in colors:
            h = c.lstrip('#')
            if len(h) < 6:
                continue
            try:
                r = int(h[0:2], 16) / 255
                g = int(h[2:4], 16) / 255
                b = int(h[4:6], 16) / 255
                hsv_colors.append(colorsys.rgb_to_hsv(r, g, b))
            except ValueError:
                continue

        if len(hsv_colors) < 3:
            return {"total": 5.0, "harmony": 5.0, "contrast": 5.0,
                    "saturation_balance": 5.0, "hue_diversity": 5.0}

        hues = [h[0] * 360 for h in hsv_colors if h[1] > 0.05]
        harmony = self._harmony_score(hues)

        values = [h[2] for h in hsv_colors]
        contrast = min(10, (max(values) - min(values)) * 12)

        sats = [h[1] for h in hsv_colors]
        avg_sat = sum(sats) / len(sats)
        sat_balance = 10 - abs(avg_sat - 0.4) * 15
        sat_balance = max(1, min(10, sat_balance))

        unique_hues = len(set(int(h) // 30 for h in hues)) if hues else 0
        count_score = 10 if 3 <= unique_hues <= 5 else max(5, 10 - abs(unique_hues - 4) * 1.5)

        total = round(harmony * 0.35 + contrast * 0.25 + sat_balance * 0.2 + count_score * 0.2, 1)
        return {
            "total": round(total, 1),
            "harmony": round(harmony, 1),
            "contrast": round(contrast, 1),
            "saturation_balance": round(sat_balance, 1),
            "hue_diversity": round(count_score, 1),
        }

    def _harmony_score(self, hues: List[float]) -> float:
        if len(hues) < 2:
            return 5.0
        best = 0.0
        for i in range(len(hues)):
            for j in range(i + 1, len(hues)):
                diff = abs(hues[i] - hues[j]) % 360
                if diff > 180:
                    diff = 360 - diff
                if abs(diff - 180) < 20:
                    best = max(best, 9.0)
                elif abs(diff - 120) < 20:
                    best = max(best, 8.5)
                elif abs(diff - 150) < 20:
                    best = max(best, 8.0)
                elif diff < 30:
                    best = max(best, 7.5)
                elif abs(diff - 90) < 20:
                    best = max(best, 7.0)
        return max(best, 5.0)

    def score_tensor(self, tensor: StyleTensor) -> dict:
        """Score a StyleTensor's palette quality."""
        colors = [v for k, v in tensor.palette.items()
                  if isinstance(v, str) and v.startswith("#")]
        return self.score_palette(colors)

    def compare(self, source_colors: List[str], output_colors: List[str]) -> dict:
        """Compare source and output palette fidelity."""
        src = self.score_palette(source_colors)
        out = self.score_palette(output_colors)
        fidelity = round(min(100, (out["total"] / max(src["total"], 0.1)) * 100), 1)
        return {
            "source_score": src,
            "output_score": out,
            "fidelity_pct": fidelity,
            "pass": fidelity >= 75,
        }
