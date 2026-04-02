"""
ANVIL Code Generator — Generates production HTML/CSS from structural tree + design system.
All values use CSS custom properties from the extracted design system — never hardcoded.
"""

import os
from typing import Dict, List, Optional
from ..extract.compiler import DesignSystem
from ..extract.structure import LayoutNode


def generate_html(ds: DesignSystem, output_dir: str) -> str:
    """Generate complete HTML/CSS from design system.

    Args:
        ds: Complete DesignSystem from compiler
        output_dir: Directory to write output files

    Returns:
        Path to generated HTML file
    """
    os.makedirs(output_dir, exist_ok=True)

    meta = ds.to_dict()["meta"]
    page_type = meta["page_type"]
    is_dark = meta["is_dark_mode"]

    # Generate CSS from tokens
    css = _generate_css(ds)

    # Generate HTML from structural tree
    html_body = _generate_body(ds.structure.root, ds, depth=0)

    # Responsive CSS
    responsive_css = ds.responsive.to_css()

    # Assemble full HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ANVIL Generated — {page_type.replace('_', ' ').title()}</title>
<style>
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


def _generate_css(ds: DesignSystem) -> str:
    """Generate CSS including tokens and base styles."""
    tokens = []
    tokens.append("/* ANVIL Auto-Generated Styles */")
    tokens.append("*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }")
    tokens.append("")

    # CSS custom properties
    tokens.append(":root {")
    for role, hex_val in sorted(ds.palette.roles.items()):
        tokens.append(f"  --{role.replace('_', '-')}: {hex_val};")

    typo = ds.typography.to_dict()
    tokens.append(f"  --font-sans: {typo['family_sans']};")
    tokens.append(f"  --font-mono: {typo['family_mono']};")

    for val in ds.spacing.scale[:12]:
        tokens.append(f"  --spacing-{val}: {val}px;")

    radii = ds._extract_radii()
    for name, val in radii.items():
        tokens.append(f"  --radius-{name}: {val};")

    for key, val in ds.effects.to_dict().items():
        tokens.append(f"  --{key.replace('_', '-')}: {val};")

    tokens.append("}")
    tokens.append("")

    # Base styles
    bg_color = ds.palette.roles.get("bg_layer_0", "#FFFFFF")
    text_color = ds.palette.roles.get("text_primary", "#000000")

    tokens.append("body {")
    tokens.append("  font-family: var(--font-sans);")
    tokens.append(f"  background: var(--bg-layer-0, {bg_color});")
    tokens.append(f"  color: var(--text-primary, {text_color});")
    tokens.append("  min-height: 100vh;")
    tokens.append("  -webkit-font-smoothing: antialiased;")
    tokens.append("}")
    tokens.append("")

    # Grid system
    grid = ds.structure.grid
    if grid.columns > 1:
        tokens.append(f".grid {{ display: grid; grid-template-columns: repeat({grid.columns}, 1fr); gap: {grid.gutter}px; }}")
        tokens.append("")

    # Component base styles
    tokens.append(".section { padding: var(--spacing-48, 48px) var(--spacing-24, 24px); }")
    tokens.append(".container { max-width: 1280px; margin: 0 auto; padding: 0 var(--spacing-24, 24px); }")
    tokens.append(".card { background: var(--bg-layer-1, #121214); border-radius: var(--radius-surface); "
                   "border: 1px solid var(--border-subtle, transparent); }")

    if ds.effects.shadows:
        tokens.append(f".card {{ box-shadow: {ds.effects.shadows[0].to_css()}; }}")

    if ds.effects.has_glassmorphism:
        tokens.append(f".glass {{ backdrop-filter: blur({ds.effects.glassmorphism_blur}px); "
                       "-webkit-backdrop-filter: blur({ds.effects.glassmorphism_blur}px); }}")

    return "\n".join(tokens)


def _generate_body(node: LayoutNode, ds: DesignSystem, depth: int) -> str:
    """Recursively generate HTML from layout tree."""
    indent = "  " * (depth + 1)

    if depth == 0:
        # Root: just render children
        children_html = "\n".join(
            _generate_body(child, ds, depth + 1)
            for child in sorted(node.children, key=lambda n: (n.y, n.x))
        )
        return children_html

    # Determine HTML element and class
    tag, classes, attrs = _node_to_element(node, ds)

    if not node.children:
        # Leaf node
        content = _placeholder_content(node, ds)
        cls_attr = f' class="{" ".join(classes)}"' if classes else ""
        extra = f" {attrs}" if attrs else ""
        return f"{indent}<{tag}{cls_attr}{extra}>{content}</{tag}>"

    # Container with children
    children_html = "\n".join(
        _generate_body(child, ds, depth + 1)
        for child in sorted(node.children, key=lambda n: (n.y, n.x))
    )

    cls_attr = f' class="{" ".join(classes)}"' if classes else ""
    extra = f" {attrs}" if attrs else ""
    return f"""{indent}<{tag}{cls_attr}{extra}>
{children_html}
{indent}</{tag}>"""


def _node_to_element(node: LayoutNode, ds: DesignSystem):
    """Map a layout node to HTML element, classes, and attributes."""
    classes = []
    attrs = ""
    tag = "div"

    node_type = node.node_type

    if node_type == "section":
        tag = "section"
        classes.append("section")
    elif node_type == "text":
        # Determine heading level by height
        if node.h > 28:
            tag = "h1"
        elif node.h > 22:
            tag = "h2"
        elif node.h > 18:
            tag = "h3"
        else:
            tag = "p"
    elif node_type == "image":
        tag = "div"
        classes.append("image-placeholder")
        attrs = f'style="width: {node.w}px; height: {node.h}px; background: var(--bg-layer-2); border-radius: var(--radius-inner);"'
    elif node_type == "icon":
        tag = "span"
        classes.append("icon")
    elif node_type == "container":
        if node.is_repeated:
            classes.append("card")
        if len(node.children) >= 2:
            # Determine layout direction
            kids = sorted(node.children, key=lambda n: n.x)
            is_horizontal = all(
                kids[i + 1].x > kids[i].x + kids[i].w * 0.5
                for i in range(min(2, len(kids) - 1))
            )
            if is_horizontal:
                classes.append("flex-row")
                attrs = 'style="display: flex; gap: var(--spacing-8, 8px); align-items: center;"'
            else:
                classes.append("flex-col")
                attrs = 'style="display: flex; flex-direction: column; gap: var(--spacing-8, 8px);"'

    return tag, classes, attrs


def _placeholder_content(node: LayoutNode, ds: DesignSystem) -> str:
    """Generate placeholder content for leaf nodes."""
    if node.node_type == "text":
        if node.h > 24:
            return "Heading Text"
        elif node.h > 16:
            return "Subheading text goes here"
        return "Body text content"
    elif node.node_type == "icon":
        return "◆"
    elif node.node_type == "image":
        return ""
    return ""
