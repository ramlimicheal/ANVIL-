"""
ANVIL Design System Compiler — Assembles extracted tokens into a complete design system.
Outputs: design_system.json, tokens.css, tailwind.config.js, components.html
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .palette import ExtractedPalette, extract_palette
from .classifier import PageClassification, classify_page
from .structure import StructuralTree, extract_structure
from .spacing import ExtractedSpacing, extract_spacing
from .typography import ExtractedTypography, extract_typography
from .effects import ExtractedEffects, extract_effects
from .components import ComponentCatalog, detect_components
from .icons import IconAnalysis, detect_icons
from .responsive import ResponsiveFramework, generate_responsive


@dataclass
class DesignSystem:
    """Complete extracted design system."""
    palette: ExtractedPalette
    typography: ExtractedTypography
    spacing: ExtractedSpacing
    effects: ExtractedEffects
    components: ComponentCatalog
    icons: IconAnalysis
    responsive: ResponsiveFramework
    classification: PageClassification
    structure: StructuralTree

    def to_dict(self) -> dict:
        return {
            "meta": {
                "page_type": self.classification.page_type,
                "confidence": self.classification.confidence,
                "image_size": self.classification.image_size,
                "is_dark_mode": self.palette.is_dark_mode,
            },
            "palette": self.palette.roles,
            "typography": self.typography.to_dict(),
            "geometry": {
                "spacing_base": f"{self.spacing.base}px",
                "spacing_scale": self.spacing.scale,
                **{f"radius_{k}": v for k, v in self._extract_radii().items()},
            },
            "effects": self.effects.to_dict(),
            "grid": self.structure.to_dict()["grid"],
            "components": self.components.to_dict(),
            "icons": self.icons.to_dict(),
            "responsive": self.responsive.to_dict(),
            "taste_vector": self._compute_taste_vector(),
        }

    def _extract_radii(self) -> Dict[str, str]:
        """Derive border radii from common component dimensions."""
        # Heuristic: derive from spacing scale
        base = self.spacing.base
        return {
            "surface": f"{base * 6}px",
            "inner": f"{base * 4}px",
            "button": f"{base * 2}px",
            "pill": "99px",
        }

    def _compute_taste_vector(self) -> Dict[str, float]:
        """Compute 6D TasteVector from extracted properties."""
        p = self.palette
        t = self.typography
        s = self.spacing

        # Temperature: warm (high) vs cool (low) based on dominant hue
        hue = p.dominant_hue
        if 30 < hue < 90:
            temp = 0.8  # warm (yellow/orange range)
        elif 180 < hue < 270:
            temp = 0.2  # cool (blue range)
        else:
            temp = 0.5

        # Density: based on spacing base (tight = dense, loose = sparse)
        density = max(0.1, min(0.9, 1.0 - (s.base / 12.0)))

        # Formality: serif = formal, sans = moderate, decorative = informal
        formality = {"serif": 0.9, "sans-serif": 0.7, "monospace": 0.8, "decorative": 0.3}
        form = formality.get(t.classification, 0.5)

        # Energy: based on color saturation and contrast
        energy = 0.5  # default
        if len(p.colors) > 0:
            avg_sat = sum(
                1 for c in p.colors if hasattr(c, 'rgb')
            ) / max(len(p.colors), 1)
            energy = min(0.9, avg_sat)

        # Age: modern (high) vs classic — based on geometric radii
        age = 0.8 if s.base <= 4 else 0.5

        # Price: premium feel — dark mode + glassmorphism = premium
        price = 0.5
        if p.is_dark_mode:
            price += 0.2
        if self.effects.has_glassmorphism:
            price += 0.2

        return {
            "temperature": round(temp, 2),
            "density": round(density, 2),
            "formality": round(form, 2),
            "energy": round(energy, 2),
            "age": round(age, 2),
            "price": round(min(price, 0.99), 2),
        }


def extract_design_system(image_path: str) -> DesignSystem:
    """Full extraction pipeline: screenshot → complete design system.

    Args:
        image_path: Path to screenshot PNG/JPG

    Returns:
        DesignSystem with all tokens extracted
    """
    print(f"  [ANVIL] Extracting design system from: {os.path.basename(image_path)}")

    print("    → Classifying page type...")
    classification = classify_page(image_path)
    print(f"      Page: {classification.page_type} (confidence: {classification.confidence})")

    print("    → Extracting color palette...")
    palette = extract_palette(image_path)
    mode = "dark" if palette.is_dark_mode else "light"
    print(f"      {len(palette.colors)} colors, {mode} mode, {len(palette.roles)} roles assigned")

    print("    → Decomposing structure...")
    structure = extract_structure(image_path)
    print(f"      {structure.total_nodes} nodes, depth {structure.max_depth}, {structure.grid.columns}-column grid")

    print("    → Extracting spacing grid...")
    spacing = extract_spacing(structure)
    print(f"      Base: {spacing.base}px, Scale: {spacing.scale[:6]}...")

    print("    → Analyzing typography...")
    typography = extract_typography(image_path)
    print(f"      Font: {typography.classification}, Scale ratio: {typography.scale_ratio} ({typography.scale_name})")

    print("    → Extracting visual effects...")
    effects = extract_effects(image_path, structure)
    print(f"      {len(effects.shadows)} shadows, {len(effects.gradients)} gradients, glass: {effects.has_glassmorphism}")

    print("    → Detecting components...")
    components = detect_components(structure)
    print(f"      {len(components.components)} patterns, {components.total_instances} instances")

    print("    → Classifying icons...")
    icons = detect_icons(image_path, structure)
    print(f"      {icons.total_count} icons, style: {icons.dominant_style}, library: {icons.dominant_library}")

    print("    → Generating responsive framework...")
    responsive = generate_responsive(classification)
    print(f"      {len(responsive.rules)} rules for {responsive.page_type}")

    return DesignSystem(
        palette=palette,
        typography=typography,
        spacing=spacing,
        effects=effects,
        components=components,
        icons=icons,
        responsive=responsive,
        classification=classification,
        structure=structure,
    )


def compile_design_system(ds: DesignSystem, output_dir: str):
    """Compile design system to output files.

    Generates:
        - design_system.json
        - tokens.css
        - tailwind.config.js
    """
    os.makedirs(output_dir, exist_ok=True)

    # 1. design_system.json
    ds_path = os.path.join(output_dir, "design_system.json")
    with open(ds_path, "w") as f:
        json.dump(ds.to_dict(), f, indent=2, default=str)
    print(f"    ✅ {ds_path}")

    # 2. tokens.css
    css_path = os.path.join(output_dir, "tokens.css")
    with open(css_path, "w") as f:
        f.write(_generate_css_tokens(ds))
    print(f"    ✅ {css_path}")

    # 3. tailwind.config.js
    tw_path = os.path.join(output_dir, "tailwind.config.js")
    with open(tw_path, "w") as f:
        f.write(_generate_tailwind_config(ds))
    print(f"    ✅ {tw_path}")

    # 4. Responsive CSS
    resp_path = os.path.join(output_dir, "responsive.css")
    with open(resp_path, "w") as f:
        f.write(ds.responsive.to_css())
    print(f"    ✅ {resp_path}")


def _generate_css_tokens(ds: DesignSystem) -> str:
    """Generate CSS custom properties from design system."""
    lines = ["/* ANVIL Design Tokens — Auto-extracted */", ":root {"]

    # Palette
    lines.append("  /* Colors */")
    for role, hex_val in sorted(ds.palette.roles.items()):
        css_name = role.replace("_", "-")
        lines.append(f"  --{css_name}: {hex_val};")

    # Typography
    lines.append("\n  /* Typography */")
    typo = ds.typography.to_dict()
    lines.append(f"  --font-sans: {typo['family_sans']};")
    lines.append(f"  --font-mono: {typo['family_mono']};")
    for key, val in typo.get("weights", {}).items():
        lines.append(f"  --{key.replace('_', '-')}: {val};")

    # Spacing
    lines.append("\n  /* Spacing */")
    lines.append(f"  --spacing-base: {ds.spacing.base}px;")
    for val in ds.spacing.scale:
        lines.append(f"  --spacing-{val}: {val}px;")

    # Geometry
    lines.append("\n  /* Border Radius */")
    radii = ds._extract_radii()
    for name, val in radii.items():
        lines.append(f"  --radius-{name}: {val};")

    # Effects
    lines.append("\n  /* Effects */")
    for key, val in ds.effects.to_dict().items():
        css_name = key.replace("_", "-")
        lines.append(f"  --{css_name}: {val};")

    lines.append("}")
    return "\n".join(lines)


def _generate_tailwind_config(ds: DesignSystem) -> str:
    """Generate tailwind.config.js from design system."""
    palette = ds.palette.roles
    spacing = ds.spacing

    # Build color config
    color_entries = []
    for role, hex_val in sorted(palette.items()):
        key = role.replace("_", "-")
        color_entries.append(f'        "{key}": "{hex_val}"')
    colors_str = ",\n".join(color_entries)

    # Build spacing config
    spacing_entries = []
    for val in spacing.scale:
        spacing_entries.append(f'        "{val}": "{val}px"')
    spacing_str = ",\n".join(spacing_entries)

    return f"""/** @type {{import('tailwindcss').Config}} */
/* ANVIL Auto-Generated Tailwind Configuration */
module.exports = {{
  content: ["./src/**/*.{{html,js,jsx,ts,tsx,vue,svelte}}"],
  theme: {{
    extend: {{
      colors: {{
{colors_str}
      }},
      spacing: {{
{spacing_str}
      }},
      borderRadius: {{
        surface: "{ds._extract_radii()['surface']}",
        inner: "{ds._extract_radii()['inner']}",
        button: "{ds._extract_radii()['button']}",
        pill: "99px",
      }},
      fontFamily: {{
        sans: ["{ds.typography.suggested_fonts[0] if ds.typography.suggested_fonts else 'Inter'}", "system-ui", "sans-serif"],
        mono: ["{ds.typography.mono_suggested[0] if ds.typography.mono_suggested else 'JetBrains Mono'}", "monospace"],
      }},
    }},
  }},
  plugins: [],
}};
"""
