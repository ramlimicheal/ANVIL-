"""
ANVIL Code Generator — Generates HTML/CSS from the StructuralTree + DesignSystem.

V2: Layout-driven generation. Every element comes from the extracted structural tree.
No hardcoded templates. All values derived from extraction data.
"""

import os
from typing import Dict, List, Optional, Tuple
from ..extract.compiler import DesignSystem
from ..extract.structure import LayoutNode
from .layout_engine import build_layout, ComponentSpec


def generate_html(ds: DesignSystem, output_dir: str) -> str:
    """Generate complete HTML/CSS from design system using the layout engine.

    Args:
        ds: Complete DesignSystem from compiler
        output_dir: Directory to write output files

    Returns:
        Path to generated HTML file
    """
    os.makedirs(output_dir, exist_ok=True)

    meta = ds.to_dict()["meta"]
    page_type = meta["page_type"]

    # Phase 1: Build layout specs from structural tree
    specs = build_layout(ds)

    # Phase 2: Generate CSS tokens + component styles
    css = _generate_css(ds, specs)

    # Phase 3: Generate HTML from specs
    html_body = _specs_to_html(specs)

    # Responsive CSS
    responsive_css = ds.responsive.to_css()

    # Font import
    font = ds.typography.suggested_fonts[0] if ds.typography.suggested_fonts else "Inter"
    font_import = f'@import url("https://fonts.googleapis.com/css2?family={font.replace(" ", "+")}:wght@300;400;500;600;700&display=swap");'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ANVIL Generated — {page_type.replace('_', ' ').title()}</title>
<style>
{font_import}

{css}

{responsive_css}
</style>
</head>
<body>
{html_body}
</body>
</html>
"""

    output_path = os.path.join(output_dir, "index.html")
    with open(output_path, "w") as f:
        f.write(html)

    return output_path


def _generate_css(ds: DesignSystem, specs: List[ComponentSpec]) -> str:
    """Generate CSS: custom properties + per-component styles from specs."""
    lines = []
    lines.append("/* ANVIL Auto-Generated Styles — Layout-Driven V2 */")
    lines.append("*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }")
    lines.append("")

    # CSS custom properties from extracted tokens
    lines.append(":root {")
    for role, hex_val in sorted(ds.palette.roles.items()):
        lines.append(f"  --{role.replace('_', '-')}: {hex_val};")

    typo = ds.typography.to_dict()
    lines.append(f"  --font-sans: {typo['family_sans']};")
    lines.append(f"  --font-mono: {typo['family_mono']};")

    for val in ds.spacing.scale[:12]:
        lines.append(f"  --spacing-{val}: {val}px;")

    radii = ds._extract_radii()
    for name, val in radii.items():
        lines.append(f"  --radius-{name}: {val};")

    for key, val in ds.effects.to_dict().items():
        lines.append(f"  --{key.replace('_', '-')}: {val};")

    lines.append("}")
    lines.append("")

    # Body
    bg_color = ds.palette.roles.get("bg_layer_0", "#FFFFFF")
    text_color = ds.palette.roles.get("text_primary", "#000000")
    lines.append("body {")
    lines.append("  font-family: var(--font-sans);")
    lines.append(f"  background: var(--bg-layer-0, {bg_color});")
    lines.append(f"  color: var(--text-primary, {text_color});")
    lines.append("  min-height: 100vh;")
    lines.append("  -webkit-font-smoothing: antialiased;")
    lines.append("}")
    lines.append("")

    # Generate per-component CSS from specs
    _collect_css_from_specs(specs, lines)

    # Glassmorphism
    if ds.effects.has_glassmorphism:
        lines.append(f".glass {{ backdrop-filter: blur({ds.effects.glassmorphism_blur}px); "
                      f"-webkit-backdrop-filter: blur({ds.effects.glassmorphism_blur}px); }}")

    # Shadow utility
    if ds.effects.shadows:
        lines.append(f".shadow-sm {{ box-shadow: {ds.effects.shadows[0].to_css()}; }}")
        if len(ds.effects.shadows) > 1:
            lines.append(f".shadow-md {{ box-shadow: {ds.effects.shadows[1].to_css()}; }}")

    return "\n".join(lines)


def _collect_css_from_specs(specs: List[ComponentSpec], lines: List[str]):
    """Generate CSS rules for each component spec."""
    for spec in specs:
        class_name = f"anvil-{spec.id}"
        props = spec.css_properties
        if props:
            lines.append(f".{class_name} {{")
            for prop, val in props.items():
                lines.append(f"  {prop}: {val};")
            lines.append("}")
            lines.append("")
        # Recurse
        _collect_css_from_specs(spec.children, lines)


def _specs_to_html(specs: List[ComponentSpec], indent: int = 1) -> str:
    """Convert ComponentSpecs to HTML recursively."""
    parts = []
    for spec in specs:
        parts.append(_spec_to_element(spec, indent))
    return "\n".join(parts)


def _spec_to_element(spec: ComponentSpec, indent: int) -> str:
    """Convert a single ComponentSpec to an HTML element."""
    pad = "  " * indent
    class_name = f"anvil-{spec.id}"
    extra_classes = " ".join(spec.css_classes)
    all_classes = f"{class_name} {extra_classes}".strip()

    tag = spec.tag

    # Self-closing tags
    if tag == "hr":
        return f'{pad}<hr class="{all_classes}" />'
    if tag == "input":
        placeholder = spec.text_placeholder or "Search..."
        return f'{pad}<input class="{all_classes}" placeholder="{placeholder}" />'

    # Build attributes
    attrs = f'class="{all_classes}"'
    if tag == "button":
        attrs += ' type="button"'

    # Content
    inner = ""
    if spec.children:
        child_html = "\n".join(
            _spec_to_element(child, indent + 1)
            for child in spec.children
        )
        inner = f"\n{child_html}\n{pad}"
    elif spec.text_placeholder:
        inner = _render_placeholder_content(spec)

    return f"{pad}<{tag} {attrs}>{inner}</{tag}>"


def _render_placeholder_content(spec: ComponentSpec) -> str:
    """Render meaningful placeholder content based on component type."""
    ct = spec.component_type
    w, h = spec.bounds[2], spec.bounds[3]

    if ct == "stat_card":
        return (
            f'<div style="font-size:12px;opacity:0.6;margin-bottom:4px">Metric</div>'
            f'<div style="font-size:24px;font-weight:600">$0.00</div>'
            f'<div style="font-size:11px;color:var(--accent-primary,#5e6ad2);margin-top:4px">+0%</div>'
        )
    elif ct == "button":
        return "Action"
    elif ct == "badge":
        return "Label"
    elif ct == "chip":
        return "Tag"
    elif ct == "avatar":
        svg_size = min(w, h) - 4
        return (
            f'<svg width="{svg_size}" height="{svg_size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="1.5" style="opacity:0.4">'
            f'<circle cx="12" cy="8" r="4"/>'
            f'<path d="M4 20c0-4 4-7 8-7s8 3 8 7"/>'
            f'</svg>'
        )
    elif ct == "icon" or ct == "icon_button":
        return (
            '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="2" style="opacity:0.5">'
            '<circle cx="12" cy="12" r="10"/>'
            '</svg>'
        )
    elif ct == "sidebar":
        nav_items = ["Dashboard", "Analytics", "Transactions", "Settings"]
        items = "".join(
            f'<div style="padding:10px 16px;font-size:14px;opacity:0.7;cursor:pointer">{item}</div>'
            for item in nav_items
        )
        return f'<div style="padding:20px 0;font-size:18px;font-weight:600;padding-left:16px;margin-bottom:16px">Menu</div>{items}'
    elif ct == "navbar":
        return (
            '<div style="display:flex;align-items:center;justify-content:space-between;height:100%;padding:0 24px">'
            '<div style="font-weight:600">Logo</div>'
            '<div style="display:flex;gap:16px;font-size:14px;opacity:0.7">'
            '<span>Home</span><span>About</span><span>Contact</span>'
            '</div></div>'
        )
    elif ct == "text":
        if h > 20:
            return "Heading Text"
        return "Body text content"
    elif ct == "card":
        return (
            '<div style="font-size:14px;font-weight:500;margin-bottom:8px">Card Title</div>'
            '<div style="font-size:13px;opacity:0.6">Card description or content area</div>'
        )
    elif ct == "image":
        return (
            f'<svg width="{max(40, w//2)}" height="{max(30, h//2)}" viewBox="0 0 48 36" '
            f'fill="none" stroke="currentColor" stroke-width="1" style="opacity:0.15">'
            f'<rect x="2" y="2" width="44" height="32" rx="4"/>'
            f'<circle cx="16" cy="14" r="4"/>'
            f'<path d="M2 28l12-8 8 6 10-12 14 14"/>'
            f'</svg>'
        )
    else:
        return ""
