"""
TASTE Verifier — Checks AI-generated frontend code against a StyleTensor.
Parses CSS/Tailwind/inline styles and flags design system violations.
"""

import re
import colorsys
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from .tensor import StyleTensor


@dataclass
class Violation:
    """A single design system violation."""
    severity: str  # "error", "warning", "info"
    category: str  # "color", "spacing", "typography", "radius", "accessibility"
    message: str
    file: str = ""
    line: int = 0
    found: str = ""
    expected: str = ""

    def __str__(self):
        loc = f"{self.file}:{self.line}" if self.file else "unknown"
        return f"[{self.severity.upper()}] {self.category} @ {loc}: {self.message}"


class TasteVerifier:
    """Verifies frontend code against a loaded StyleTensor."""

    def __init__(self, tensor: StyleTensor):
        self.tensor = tensor
        self._color_cache: Dict[str, Tuple[float, float, float]] = {}
        self._build_color_index()

    def _build_color_index(self):
        """Pre-compute HSL values for all palette colors."""
        for name, value in self.tensor.palette.items():
            rgb = self._parse_color(value)
            if rgb:
                self._color_cache[name] = rgb

    # ─── Main Verification Entry Point ────────────────────────────

    def verify(self, code: str, filepath: str = "") -> List[Violation]:
        """Run all TASTE checks against code. Returns violations list."""
        violations = []
        violations.extend(self._check_colors(code, filepath))
        violations.extend(self._check_spacing(code, filepath))
        violations.extend(self._check_typography(code, filepath))
        violations.extend(self._check_border_radius(code, filepath))
        violations.extend(self._check_accessibility(code, filepath))
        violations.extend(self._check_hardcoded_values(code, filepath))
        return violations

    def score(self, code: str) -> dict:
        """Score code compliance. Returns dict with score/10 and details."""
        violations = self.verify(code)
        errors = sum(1 for v in violations if v.severity == "error")
        warnings = sum(1 for v in violations if v.severity == "warning")
        infos = sum(1 for v in violations if v.severity == "info")

        # Scoring: start at 10, deduct per violation type
        raw = 10.0 - (errors * 1.5) - (warnings * 0.5) - (infos * 0.1)
        final = max(0.0, min(10.0, round(raw, 1)))

        return {
            "score": final,
            "pass": final >= 6.0,
            "errors": errors,
            "warnings": warnings,
            "infos": infos,
            "violations": violations,
            "total_violations": len(violations),
        }

    # ─── Color Verification ───────────────────────────────────────

    def _check_colors(self, code: str, filepath: str) -> List[Violation]:
        violations = []
        # Find all hex colors in code
        hex_pattern = re.compile(r'[#]([0-9a-fA-F]{3,8})\b')
        rgb_pattern = re.compile(r'rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)')
        rgba_pattern = re.compile(r'rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*[\d.]+\s*\)')

        lines = code.split("\n")
        for line_num, line in enumerate(lines, 1):
            # Check hex colors
            for match in hex_pattern.finditer(line):
                hex_val = match.group(0)
                if not self._is_in_palette(hex_val):
                    nearest = self._find_nearest_palette_color(hex_val)
                    if nearest:
                        name, dist = nearest
                        if dist > 0.02:  # Tolerance: very close colors are OK
                            violations.append(Violation(
                                severity="warning" if dist < 0.15 else "error",
                                category="color",
                                message=f"Hardcoded color {hex_val} not in design system. Nearest: --{name.replace('_', '-')}",
                                file=filepath, line=line_num,
                                found=hex_val,
                                expected=f"var(--{name.replace('_', '-')})",
                            ))

            # Check rgb() colors
            for match in rgb_pattern.finditer(line):
                r, g, b = int(match.group(1)), int(match.group(2)), int(match.group(3))
                hex_val = f"#{r:02x}{g:02x}{b:02x}"
                if not self._is_in_palette(hex_val):
                    nearest = self._find_nearest_palette_color(hex_val)
                    if nearest:
                        name, dist = nearest
                        if dist > 0.02:
                            violations.append(Violation(
                                severity="warning",
                                category="color",
                                message=f"Hardcoded rgb({r},{g},{b}) not in design system. Use var(--{name.replace('_', '-')})",
                                file=filepath, line=line_num,
                                found=match.group(0),
                                expected=f"var(--{name.replace('_', '-')})",
                            ))

        return violations

    def _is_in_palette(self, hex_color: str) -> bool:
        """Check if a color exactly matches any palette value."""
        normalized = self._normalize_hex(hex_color)
        for _, palette_val in self.tensor.palette.items():
            if self._normalize_hex(palette_val) == normalized:
                return True
        return False

    def _find_nearest_palette_color(self, hex_color: str) -> Optional[Tuple[str, float]]:
        """Find closest palette color by perceptual distance. Returns (name, distance)."""
        rgb = self._parse_color(hex_color)
        if not rgb:
            return None

        best_name = None
        best_dist = float("inf")

        for name, palette_rgb in self._color_cache.items():
            dist = self._color_distance(rgb, palette_rgb)
            if dist < best_dist:
                best_dist = dist
                best_name = name

        if best_name:
            return (best_name, best_dist)
        return None

    @staticmethod
    def _color_distance(c1: Tuple[float, ...], c2: Tuple[float, ...]) -> float:
        """Perceptual color distance (CIE76-like in sRGB space)."""
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))

    @staticmethod
    def _parse_color(value: str) -> Optional[Tuple[float, float, float]]:
        """Parse hex/rgb string to normalized (r, g, b) tuple."""
        if not value:
            return None
        value = value.strip()

        # Hex
        if value.startswith("#"):
            h = value.lstrip("#")
            if len(h) == 3:
                h = h[0]*2 + h[1]*2 + h[2]*2
            if len(h) >= 6:
                try:
                    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                    return (r / 255.0, g / 255.0, b / 255.0)
                except ValueError:
                    return None

        # rgba(...)
        m = re.match(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', value)
        if m:
            return (int(m.group(1)) / 255.0, int(m.group(2)) / 255.0, int(m.group(3)) / 255.0)

        return None

    @staticmethod
    def _normalize_hex(value: str) -> str:
        """Normalize hex color to lowercase 6-digit."""
        if not value or not value.startswith("#"):
            return value.lower().strip()
        h = value.lstrip("#").lower()
        if len(h) == 3:
            h = h[0]*2 + h[1]*2 + h[2]*2
        return f"#{h[:6]}"

    # ─── Spacing Verification ─────────────────────────────────────

    def _check_spacing(self, code: str, filepath: str) -> List[Violation]:
        violations = []
        grid = self.tensor.get_spacing_grid()
        # Only check micro-spacing properties — not structural layout dimensions
        spacing_props = re.compile(
            r'(margin|padding|gap|top|right|bottom|left|inset)'
            r'[^:]*:\s*(-?\d+)px',
            re.IGNORECASE,
        )

        lines = code.split("\n")
        for line_num, line in enumerate(lines, 1):
            # Skip media queries and CSS variables — these are structural, not micro-spacing
            stripped = line.strip()
            if stripped.startswith('@media') or stripped.startswith('--'):
                continue

            for match in spacing_props.finditer(line):
                px_val = int(match.group(2))
                if px_val == 0:
                    continue
                abs_val = abs(px_val)
                if abs_val not in grid and abs_val > 2:
                    base = int(self.tensor.geometry.get("spacing_base", "4").replace("px", ""))
                    nearest = min(grid, key=lambda x: abs(x - abs_val)) if grid else abs_val
                    violations.append(Violation(
                        severity="warning",
                        category="spacing",
                        message=f"{match.group(1)}: {px_val}px not on {base}px grid. Nearest: {nearest}px",
                        file=filepath, line=line_num,
                        found=f"{px_val}px",
                        expected=f"{nearest}px",
                    ))

        return violations

    # ─── Typography Verification ──────────────────────────────────

    def _check_typography(self, code: str, filepath: str) -> List[Violation]:
        violations = []
        allowed_fonts = self.tensor.get_allowed_fonts()
        allowed_lower = [f.lower() for f in allowed_fonts]

        font_pattern = re.compile(r'font-family\s*:\s*([^;}\n]+)', re.IGNORECASE)

        lines = code.split("\n")
        for line_num, line in enumerate(lines, 1):
            for match in font_pattern.finditer(line):
                fonts_str = match.group(1).strip().rstrip(";")
                # Skip CSS variable references — they're indirections, not literal font names
                if 'var(' in fonts_str:
                    continue
                declared_fonts = [f.strip().strip("'\"") for f in fonts_str.split(",")]
                for font in declared_fonts:
                    if font.lower() not in allowed_lower and font.lower() not in (
                        "inherit", "initial", "unset", "sans-serif", "serif", "monospace",
                        "system-ui", "cursive", "fantasy",
                    ):
                        violations.append(Violation(
                            severity="error",
                            category="typography",
                            message=f"Font '{font}' not in design system. Allowed: {', '.join(allowed_fonts[:3])}",
                            file=filepath, line=line_num,
                            found=font,
                            expected=allowed_fonts[0] if allowed_fonts else "Inter",
                        ))

        # Check font weights
        allowed_weights = set()
        for k, v in self.tensor.typography.items():
            if "weight" in k:
                allowed_weights.add(v)

        weight_pattern = re.compile(r'font-weight\s*:\s*(\d+)', re.IGNORECASE)
        for line_num, line in enumerate(lines, 1):
            for match in weight_pattern.finditer(line):
                weight = match.group(1)
                if weight not in allowed_weights and allowed_weights:
                    violations.append(Violation(
                        severity="info",
                        category="typography",
                        message=f"Font weight {weight} not in design system. Allowed: {', '.join(sorted(allowed_weights))}",
                        file=filepath, line=line_num,
                        found=weight,
                        expected=", ".join(sorted(allowed_weights)),
                    ))

        return violations

    # ─── Border Radius Verification ───────────────────────────────

    def _check_border_radius(self, code: str, filepath: str) -> List[Violation]:
        violations = []
        allowed = set(self.tensor.get_allowed_radii())
        allowed.add("0px")
        allowed.add("0")
        allowed.add("50%")
        allowed.add("100%")

        radius_pattern = re.compile(r'border-radius\s*:\s*([^;}\n]+)', re.IGNORECASE)

        lines = code.split("\n")
        for line_num, line in enumerate(lines, 1):
            for match in radius_pattern.finditer(line):
                value = match.group(1).strip().rstrip(";").strip()
                # Handle shorthand (e.g., "12px 8px")
                parts = value.split()
                for part in parts:
                    part = part.strip()
                    if part and part not in allowed and not part.startswith("var("):
                        violations.append(Violation(
                            severity="info",
                            category="radius",
                            message=f"border-radius: {part} not in design tokens. Allowed: {', '.join(sorted(allowed))}",
                            file=filepath, line=line_num,
                            found=part,
                            expected=", ".join(sorted(allowed)),
                        ))

        return violations

    # ─── WCAG Accessibility ───────────────────────────────────────

    def _check_accessibility(self, code: str, filepath: str) -> List[Violation]:
        """Check color contrast ratios for WCAG AA compliance."""
        violations = []

        # Find color + background-color pairs
        bg_pattern = re.compile(r'background(?:-color)?\s*:\s*([#][0-9a-fA-F]{3,8})', re.IGNORECASE)
        fg_pattern = re.compile(r'(?:^|[;\s])color\s*:\s*([#][0-9a-fA-F]{3,8})', re.IGNORECASE)

        bg_colors = []
        fg_colors = []

        lines = code.split("\n")
        for line_num, line in enumerate(lines, 1):
            for m in bg_pattern.finditer(line):
                bg_colors.append((line_num, m.group(1)))
            for m in fg_pattern.finditer(line):
                fg_colors.append((line_num, m.group(1)))

        # Check all fg/bg combinations within proximity (same block)
        for fg_line, fg_color in fg_colors:
            for bg_line, bg_color in bg_colors:
                if abs(fg_line - bg_line) <= 10:  # Within ~10 lines = likely same block
                    ratio = self._contrast_ratio(fg_color, bg_color)
                    if ratio is not None and ratio < 4.5:  # WCAG AA for normal text
                        violations.append(Violation(
                            severity="error",
                            category="accessibility",
                            message=f"WCAG AA fail: contrast ratio {ratio:.2f}:1 (need 4.5:1). "
                                    f"Text {fg_color} on {bg_color}",
                            file=filepath, line=fg_line,
                            found=f"{ratio:.2f}:1",
                            expected="≥ 4.5:1",
                        ))

        return violations

    def _contrast_ratio(self, fg_hex: str, bg_hex: str) -> Optional[float]:
        """Calculate WCAG contrast ratio between two colors."""
        fg = self._parse_color(fg_hex)
        bg = self._parse_color(bg_hex)
        if not fg or not bg:
            return None

        def luminance(rgb):
            channels = []
            for c in rgb:
                if c <= 0.03928:
                    channels.append(c / 12.92)
                else:
                    channels.append(((c + 0.055) / 1.055) ** 2.4)
            return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

        l1 = luminance(fg)
        l2 = luminance(bg)
        lighter = max(l1, l2)
        darker = min(l1, l2)
        return round((lighter + 0.05) / (darker + 0.05), 2)

    # ─── Hardcoded Value Detection ────────────────────────────────

    def _check_hardcoded_values(self, code: str, filepath: str) -> List[Violation]:
        """Flag hardcoded values that should use CSS variables."""
        violations = []

        # Check for var(--...) usage vs hardcoded
        has_vars = "var(--" in code
        hardcoded_count = len(re.findall(r':\s*#[0-9a-fA-F]{3,8}', code))

        if hardcoded_count > 5 and not has_vars:
            violations.append(Violation(
                severity="warning",
                category="color",
                message=f"Found {hardcoded_count} hardcoded colors with 0 CSS variable references. "
                        f"Consider using design tokens via var(--color-name)",
                file=filepath, line=0,
                found=f"{hardcoded_count} hardcoded",
                expected="CSS variables",
            ))

        return violations
