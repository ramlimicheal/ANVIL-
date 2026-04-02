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
from .css_tokenizer import CSSTokenizer


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
        """Pre-compute CIE Lab* values for all palette colors."""
        for name, value in self.tensor.palette.items():
            rgb = self._parse_color(value)
            if rgb:
                self._color_cache[name] = self._srgb_to_lab(rgb)

    # ─── Main Verification Entry Point ────────────────────────────

    @staticmethod
    def _is_css_file(filepath: str) -> bool:
        return filepath.lower().endswith((".css", ".scss", ".less"))

    def verify(self, code: str, filepath: str = "") -> List[Violation]:
        """Run all TASTE checks against code. Returns violations list.
        Uses CSS tokenizer for .css/.scss files (eliminates false positives
        from comments, strings, URLs). Falls back to regex for JSX/Vue/etc."""
        violations = []

        # Use proper CSS tokenizer for CSS files
        if self._is_css_file(filepath):
            violations.extend(self._check_colors_tokenized(code, filepath))
            violations.extend(self._check_spacing_tokenized(code, filepath))
            violations.extend(self._check_typography_tokenized(code, filepath))
            violations.extend(self._check_radius_tokenized(code, filepath))
        else:
            violations.extend(self._check_colors(code, filepath))
            violations.extend(self._check_spacing(code, filepath))
            violations.extend(self._check_typography(code, filepath))
            violations.extend(self._check_border_radius(code, filepath))

        violations.extend(self._check_accessibility(code, filepath))
        violations.extend(self._check_hardcoded_values(code, filepath))
        violations.extend(self._check_inline_styles(code, filepath))
        violations.extend(self._check_design_formality(code, filepath))
        return violations

    # ─── CSS Tokenizer-Based Checks (no false positives) ──────────

    def _check_colors_tokenized(self, code: str, filepath: str) -> List[Violation]:
        """Check colors using CSS tokenizer — excludes comments, strings, URLs."""
        violations = []
        tokenizer = CSSTokenizer(code)
        colors = tokenizer.get_colors()

        for color_val, line_num in colors:
            if not self._is_in_palette(color_val):
                nearest = self._find_nearest_palette_color(color_val)
                if nearest:
                    name, dist = nearest
                    if dist > 2.3:  # CIEDE2000 JND threshold
                        violations.append(Violation(
                            severity="warning" if dist < 12.0 else "error",
                            category="color",
                            message=f"Hardcoded color {color_val} not in design system. "
                                    f"Nearest: --{name.replace('_', '-')} (\u0394E={dist:.1f})",
                            file=filepath, line=line_num,
                            found=color_val,
                            expected=f"var(--{name.replace('_', '-')})",
                        ))
        return violations

    def _check_spacing_tokenized(self, code: str, filepath: str) -> List[Violation]:
        """Check spacing using CSS tokenizer."""
        violations = []
        tokenizer = CSSTokenizer(code)
        grid = self.tensor.get_spacing_grid()
        base = int(self.tensor.geometry.get("spacing_base", "4").replace("px", ""))

        for prop, value, line_num in tokenizer.get_spacing_values():
            px_matches = re.findall(r'(-?\d+)px', value)
            for px_str in px_matches:
                px_val = int(px_str)
                if px_val == 0:
                    continue
                abs_val = abs(px_val)
                if abs_val not in grid and abs_val > 2:
                    nearest = min(grid, key=lambda x: abs(x - abs_val)) if grid else abs_val
                    violations.append(Violation(
                        severity="warning",
                        category="spacing",
                        message=f"{prop}: {px_val}px not on {base}px grid. Nearest: {nearest}px",
                        file=filepath, line=line_num,
                        found=f"{px_val}px",
                        expected=f"{nearest}px",
                    ))
        return violations

    def _check_typography_tokenized(self, code: str, filepath: str) -> List[Violation]:
        """Check fonts using CSS tokenizer."""
        violations = []
        tokenizer = CSSTokenizer(code)
        allowed_fonts = self.tensor.get_allowed_fonts()
        allowed_lower = [f.lower() for f in allowed_fonts]
        generic_families = {"inherit", "initial", "unset", "sans-serif", "serif",
                           "monospace", "system-ui", "cursive", "fantasy"}

        for fonts_str, line_num in tokenizer.get_fonts():
            declared = [f.strip().strip("'\"" ) for f in fonts_str.split(",")]
            for font in declared:
                if font.lower() not in allowed_lower and font.lower() not in generic_families:
                    violations.append(Violation(
                        severity="error",
                        category="typography",
                        message=f"Font '{font}' not in design system. "
                                f"Allowed: {', '.join(allowed_fonts[:3])}",
                        file=filepath, line=line_num,
                        found=font,
                        expected=allowed_fonts[0] if allowed_fonts else "Inter",
                    ))
        return violations

    def _check_radius_tokenized(self, code: str, filepath: str) -> List[Violation]:
        """Check border-radius using CSS tokenizer."""
        violations = []
        tokenizer = CSSTokenizer(code)
        allowed = set(self.tensor.get_allowed_radii())
        allowed.update({"0px", "0", "50%", "100%"})

        for value, line_num in tokenizer.get_radii():
            parts = value.split()
            for part in parts:
                part = part.strip()
                if part and part not in allowed and not part.startswith("var("):
                    violations.append(Violation(
                        severity="info",
                        category="radius",
                        message=f"border-radius: {part} not in design tokens. "
                                f"Allowed: {', '.join(sorted(allowed))}",
                        file=filepath, line=line_num,
                        found=part,
                        expected=", ".join(sorted(allowed)),
                    ))
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
                        if dist > 2.3:  # CIEDE2000 JND threshold
                            violations.append(Violation(
                                severity="warning" if dist < 12.0 else "error",
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
                        if dist > 2.3:
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
        """Find closest palette color by CIEDE2000 perceptual distance. Returns (name, ΔE)."""
        rgb = self._parse_color(hex_color)
        if not rgb:
            return None

        lab = self._srgb_to_lab(rgb)
        best_name = None
        best_dist = float("inf")

        for name, palette_lab in self._color_cache.items():
            dist = self._ciede2000(lab, palette_lab)
            if dist < best_dist:
                best_dist = dist
                best_name = name

        if best_name:
            return (best_name, best_dist)
        return None

    @staticmethod
    def _srgb_to_lab(rgb: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """Convert sRGB [0,1] to CIE Lab* via D65 XYZ."""
        # sRGB → linear RGB (inverse gamma)
        def linearize(c):
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

        r_lin, g_lin, b_lin = linearize(rgb[0]), linearize(rgb[1]), linearize(rgb[2])

        # Linear RGB → XYZ (sRGB D65 matrix)
        x = r_lin * 0.4124564 + g_lin * 0.3575761 + b_lin * 0.1804375
        y = r_lin * 0.2126729 + g_lin * 0.7151522 + b_lin * 0.0721750
        z = r_lin * 0.0193339 + g_lin * 0.1191920 + b_lin * 0.9503041

        # XYZ → Lab* (D65 white point: 0.95047, 1.0, 1.08883)
        def f(t):
            return t ** (1/3) if t > 0.008856 else (7.787 * t) + (16 / 116)

        fx = f(x / 0.95047)
        fy = f(y / 1.0)
        fz = f(z / 1.08883)

        L = (116 * fy) - 16
        a = 500 * (fx - fy)
        b = 200 * (fy - fz)
        return (L, a, b)

    @staticmethod
    def _ciede2000(lab1: Tuple[float, float, float], lab2: Tuple[float, float, float]) -> float:
        """CIEDE2000 color difference — the gold standard for perceptual distance.
        Returns ΔE₀₀. JND ≈ 2.3, noticeable ≈ 5, different ≈ 12+."""
        L1, a1, b1 = lab1
        L2, a2, b2 = lab2

        # Step 1: Calculate C'ab, h'ab
        C1 = math.sqrt(a1**2 + b1**2)
        C2 = math.sqrt(a2**2 + b2**2)
        C_avg = (C1 + C2) / 2
        C_avg7 = C_avg**7
        G = 0.5 * (1 - math.sqrt(C_avg7 / (C_avg7 + 25**7)))

        a1p = a1 * (1 + G)
        a2p = a2 * (1 + G)
        C1p = math.sqrt(a1p**2 + b1**2)
        C2p = math.sqrt(a2p**2 + b2**2)

        h1p = math.degrees(math.atan2(b1, a1p)) % 360
        h2p = math.degrees(math.atan2(b2, a2p)) % 360

        # Step 2: Calculate ΔL', ΔC', ΔH'
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

        dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))

        # Step 3: Calculate CIEDE2000
        Lp_avg = (L1 + L2) / 2
        Cp_avg = (C1p + C2p) / 2

        if C1p * C2p == 0:
            hp_avg = h1p + h2p
        elif abs(h1p - h2p) <= 180:
            hp_avg = (h1p + h2p) / 2
        elif h1p + h2p < 360:
            hp_avg = (h1p + h2p + 360) / 2
        else:
            hp_avg = (h1p + h2p - 360) / 2

        T = (1
             - 0.17 * math.cos(math.radians(hp_avg - 30))
             + 0.24 * math.cos(math.radians(2 * hp_avg))
             + 0.32 * math.cos(math.radians(3 * hp_avg + 6))
             - 0.20 * math.cos(math.radians(4 * hp_avg - 63)))

        SL = 1 + 0.015 * (Lp_avg - 50)**2 / math.sqrt(20 + (Lp_avg - 50)**2)
        SC = 1 + 0.045 * Cp_avg
        SH = 1 + 0.015 * Cp_avg * T

        Cp_avg7 = Cp_avg**7
        RT = (-2 * math.sqrt(Cp_avg7 / (Cp_avg7 + 25**7))
              * math.sin(math.radians(60 * math.exp(-((hp_avg - 275) / 25)**2))))

        dE = math.sqrt(
            (dLp / SL)**2 + (dCp / SC)**2 + (dHp / SH)**2
            + RT * (dCp / SC) * (dHp / SH)
        )
        return round(dE, 4)

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

    # ─── Inline Style Detection ───────────────────────────────────

    # Layout properties that MUST live in the CSS registry, never inline
    _LAYOUT_PROPERTIES = {
        "width", "height", "min-width", "min-height", "max-width", "max-height",
        "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
        "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
        "display", "position", "top", "right", "bottom", "left",
        "flex", "flex-direction", "flex-wrap", "justify-content", "align-items",
        "grid", "grid-template-columns", "grid-template-rows", "grid-column", "grid-row",
        "gap", "row-gap", "column-gap",
        "border-radius", "z-index", "overflow",
    }

    # Visual properties that should be in CSS but are lower severity
    _VISUAL_PROPERTIES = {
        "color", "background", "background-color", "opacity",
        "border", "border-color", "box-shadow", "text-shadow",
        "font-size", "font-weight", "font-family", "line-height",
        "text-align", "text-decoration", "text-transform",
    }

    def _check_inline_styles(self, code: str, filepath: str) -> List[Violation]:
        """Detect inline style=\"...\" attributes in HTML.

        Layout properties in inline styles are errors.
        Visual properties in inline styles are warnings.
        Pure var() references with no layout props get a pass.
        """
        violations = []

        # Match style="..." attributes (handles single and double quotes)
        inline_pattern = re.compile(
            r'style\s*=\s*["\']([^"\']*)["\']',
            re.IGNORECASE,
        )

        lines = code.split("\n")
        total_inline = 0
        layout_inline = 0
        visual_inline = 0

        for line_num, line in enumerate(lines, 1):
            for match in inline_pattern.finditer(line):
                style_content = match.group(1).strip()
                if not style_content:
                    continue

                total_inline += 1

                # Parse individual properties from the inline style
                props = [p.strip() for p in style_content.split(";") if p.strip()]
                for prop in props:
                    if ":" not in prop:
                        continue
                    prop_name = prop.split(":")[0].strip().lower()

                    if prop_name in self._LAYOUT_PROPERTIES:
                        layout_inline += 1
                        violations.append(Violation(
                            severity="error",
                            category="inline_style",
                            message=f"Layout property '{prop_name}' in inline style — "
                                    f"must be in CSS registry. Inline: {prop.strip()}",
                            file=filepath, line=line_num,
                            found=f"style=\"...{prop_name}...\"",
                            expected=f".class {{ {prop.strip()}; }}",
                        ))
                    elif prop_name in self._VISUAL_PROPERTIES:
                        # Check if it uses var() — that's acceptable at info level
                        prop_value = prop.split(":", 1)[1].strip()
                        if "var(--" in prop_value:
                            continue  # var() reference inline is tolerable
                        visual_inline += 1
                        violations.append(Violation(
                            severity="warning",
                            category="inline_style",
                            message=f"Visual property '{prop_name}' hardcoded inline — "
                                    f"should use CSS class or var(). Found: {prop.strip()}",
                            file=filepath, line=line_num,
                            found=f"style=\"...{prop_name}...\"",
                            expected="CSS class or var(--token)",
                        ))

        # Summary violation if excessive inline styles
        if total_inline > 3:
            violations.append(Violation(
                severity="error",
                category="inline_style",
                message=f"Excessive inline styles: {total_inline} found "
                        f"({layout_inline} layout, {visual_inline} visual). "
                        f"Move all styling to the CSS registry.",
                file=filepath, line=0,
                found=f"{total_inline} inline style attributes",
                expected="0 inline styles (all in CSS)",
            ))

        return violations

    # ─── 6D Taste Vector: Design Formality Gate ──────────────────

    def _check_design_formality(self, code: str, filepath: str) -> List[Violation]:
        """Use the 6D taste vector's formality dimension to gate var() usage.

        High formality (>0.6) = most values MUST use var().
        Low formality (<0.4) = some hardcoding tolerated.

        Also uses density to check CSS complexity expectations.
        """
        violations = []
        tv = getattr(self.tensor, 'taste_vector', None) or {}
        if not tv:
            return violations

        formality = tv.get("formality", 0.5)
        density = tv.get("density", 0.5)

        # Count var() references vs hardcoded values
        var_count = len(re.findall(r'var\(--[\w-]+\)', code))
        hardcoded_colors = len(re.findall(r':\s*#[0-9a-fA-F]{3,8}', code))
        hardcoded_px = len(re.findall(r':\s*\d+px', code))
        total_hardcoded = hardcoded_colors + hardcoded_px
        total_values = var_count + total_hardcoded

        # Formality ratio check (only if there are values to measure)
        var_ratio = var_count / total_values if total_values > 0 else -1

        # Formality gate: map formality to minimum var() ratio
        # formality 0.9 → need 80%+ var() usage
        # formality 0.7 → need 60%+ var() usage
        # formality 0.5 → need 40%+ var() usage
        # formality 0.3 → need 20%+ var() usage
        required_ratio = max(0.1, (formality - 0.1) * 1.0)

        if var_ratio >= 0 and var_ratio < required_ratio:
            violations.append(Violation(
                severity="warning",
                category="formality",
                message=f"Design formality {formality:.1f} requires ≥{required_ratio:.0%} "
                        f"var() usage, but found {var_ratio:.0%} "
                        f"({var_count} var refs vs {total_hardcoded} hardcoded). "
                        f"Replace hardcoded values with design tokens.",
                file=filepath, line=0,
                found=f"{var_ratio:.0%} var() usage",
                expected=f"≥{required_ratio:.0%} var() usage",
            ))

        # Density check: count CSS rules vs expected complexity
        rule_count = len(re.findall(r'\{[^}]+\}', code))
        if density > 0.7 and rule_count < 5:
            violations.append(Violation(
                severity="info",
                category="density",
                message=f"Taste vector density {density:.1f} expects rich CSS, "
                        f"but only {rule_count} rules found.",
                file=filepath, line=0,
                found=f"{rule_count} rules",
                expected=f"Higher rule density",
            ))

        # ── Temperature: warm/cool color bias ──
        # Low temperature (<0.3) = cool palette (blues, grays). Warm colors are violations.
        # High temperature (>0.7) = warm palette (reds, oranges, yellows). Cool-only is a violation.
        temperature = tv.get("temperature", 0.5)
        hex_colors = re.findall(r'#([0-9a-fA-F]{6})', code)
        if hex_colors and abs(temperature - 0.5) > 0.15:
            warm_count = 0
            cool_count = 0
            for hc in hex_colors:
                try:
                    r = int(hc[0:2], 16) / 255.0
                    g = int(hc[2:4], 16) / 255.0
                    b = int(hc[4:6], 16) / 255.0
                    h, s, v = colorsys.rgb_to_hsv(r, g, b)
                    hue_deg = h * 360
                    if s > 0.1:  # Skip near-grays
                        if 0 <= hue_deg <= 60 or 300 <= hue_deg <= 360:
                            warm_count += 1
                        elif 180 <= hue_deg <= 270:
                            cool_count += 1
                except ValueError:
                    continue

            chromatic = warm_count + cool_count
            if chromatic > 0:
                warm_ratio = warm_count / chromatic
                if temperature < 0.35 and warm_ratio > 0.5:
                    violations.append(Violation(
                        severity="warning",
                        category="temperature",
                        message=f"Taste temperature {temperature:.1f} (cool) but "
                                f"{warm_ratio:.0%} of chromatic colors are warm. "
                                f"Expect blues/grays for this design system.",
                        file=filepath, line=0,
                        found=f"{warm_ratio:.0%} warm colors",
                        expected="Cool-dominant palette",
                    ))
                elif temperature > 0.65 and warm_ratio < 0.3:
                    violations.append(Violation(
                        severity="warning",
                        category="temperature",
                        message=f"Taste temperature {temperature:.1f} (warm) but "
                                f"only {warm_ratio:.0%} warm colors found. "
                                f"Expect warmer hues for this design system.",
                        file=filepath, line=0,
                        found=f"{warm_ratio:.0%} warm colors",
                        expected="Warm-dominant palette",
                    ))

        # ── Energy: animation/transition density ──
        # High energy (>0.7) = expects transitions, transforms, animations
        # Low energy (<0.3) = static design, animations are violations
        energy = tv.get("energy", 0.5)
        transition_count = len(re.findall(r'transition|animation|@keyframes|transform', code, re.IGNORECASE))
        if energy < 0.3 and transition_count > 2:
            violations.append(Violation(
                severity="info",
                category="energy",
                message=f"Taste energy {energy:.1f} (static/calm) but found "
                        f"{transition_count} animation/transition declarations. "
                        f"This design system prefers minimal motion.",
                file=filepath, line=0,
                found=f"{transition_count} motion properties",
                expected="Minimal or no animations",
            ))
        elif energy > 0.7 and transition_count == 0 and rule_count > 3:
            violations.append(Violation(
                severity="info",
                category="energy",
                message=f"Taste energy {energy:.1f} (dynamic) but no transitions "
                        f"or animations found. This design system expects motion.",
                file=filepath, line=0,
                found="0 motion properties",
                expected="Transitions and/or animations",
            ))

        # ── Age: modern CSS feature usage ──
        # High age (>0.7) = modern/cutting-edge. Expects modern features.
        # Low age (<0.3) = conservative/legacy-safe.
        age = tv.get("age", 0.5)
        modern_features = len(re.findall(
            r'(?:container-type|:has\(|:is\(|:where\(|aspect-ratio|gap:|'
            r'grid-template|place-items|backdrop-filter|color-mix|light-dark)',
            code, re.IGNORECASE,
        ))
        legacy_patterns = len(re.findall(
            r'(?:-webkit-|-moz-|-ms-|float:\s*(?:left|right)|clear:\s*both)',
            code, re.IGNORECASE,
        ))
        if age > 0.8 and legacy_patterns > 2 and modern_features == 0:
            violations.append(Violation(
                severity="info",
                category="age",
                message=f"Taste age {age:.1f} (modern) but found {legacy_patterns} "
                        f"legacy patterns and 0 modern CSS features. "
                        f"Use grid, :has(), container queries, etc.",
                file=filepath, line=0,
                found=f"{legacy_patterns} legacy, {modern_features} modern",
                expected="Modern CSS features",
            ))
        elif age < 0.3 and modern_features > 3:
            violations.append(Violation(
                severity="info",
                category="age",
                message=f"Taste age {age:.1f} (conservative) but found "
                        f"{modern_features} cutting-edge CSS features. "
                        f"May break in older browsers.",
                file=filepath, line=0,
                found=f"{modern_features} modern features",
                expected="Conservative, widely-supported CSS",
            ))

        # ── Price: visual richness/complexity ──
        # High price (>0.7) = premium feel. Expects shadows, gradients, layering.
        # Low price (<0.3) = budget/casual. Minimal decoration.
        price = tv.get("price", 0.5)
        premium_count = len(re.findall(
            r'(?:box-shadow|text-shadow|linear-gradient|radial-gradient|'
            r'backdrop-filter|filter:|opacity:|clip-path|mask-image)',
            code, re.IGNORECASE,
        ))
        if price > 0.7 and premium_count == 0 and rule_count > 3:
            violations.append(Violation(
                severity="info",
                category="price",
                message=f"Taste price {price:.1f} (premium) but no shadows, "
                        f"gradients, or visual effects found. "
                        f"Premium design systems use depth and layering.",
                file=filepath, line=0,
                found="0 premium effects",
                expected="Shadows, gradients, or visual depth",
            ))
        elif price < 0.3 and premium_count > 4:
            violations.append(Violation(
                severity="info",
                category="price",
                message=f"Taste price {price:.1f} (minimal/budget) but found "
                        f"{premium_count} premium visual effects. "
                        f"This design system prefers flat, simple styling.",
                file=filepath, line=0,
                found=f"{premium_count} premium effects",
                expected="Flat, minimal styling",
            ))

        return violations
