"""
ANVIL Layout Engine — Converts StructuralTree + DesignSystem into ComponentSpecs.

This is the algorithmic core: pixel positions → CSS layout (flex/grid).
No hardcoded templates. Every output is derived from the extracted data.

Algorithm:
  1. Walk the tree top-down
  2. For each parent, analyze children positions to determine layout direction
  3. Compute gaps, padding from actual pixel distances
  4. Snap to extracted spacing scale
  5. Assign palette roles based on node depth/type
  6. Output ComponentSpec[] ready for code generation
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from ..extract.compiler import DesignSystem
from ..extract.structure import LayoutNode, StructuralTree
from ..extract.components import ComponentCatalog


@dataclass
class ComponentSpec:
    """A single component specification for code generation."""
    id: int
    tag: str                         # div, nav, aside, section, header, main, button, etc.
    component_type: str              # sidebar, stat_card, button, card, badge, text, etc.
    css_classes: List[str] = field(default_factory=list)
    css_properties: Dict[str, str] = field(default_factory=dict)
    children: List["ComponentSpec"] = field(default_factory=list)
    text_placeholder: str = ""       # placeholder text for LLM to fill
    bounds: Tuple[int, int, int, int] = (0, 0, 0, 0)
    layout_direction: str = "column" # row | column | grid
    grid_columns: int = 0            # if layout_direction == grid
    gap: int = 0
    padding: Tuple[int, int, int, int] = (0, 0, 0, 0)  # top, right, bottom, left
    is_repeated: bool = False
    repeat_count: int = 1
    depth: int = 0
    palette_role: str = ""           # bg_layer_0, bg_layer_1, accent_primary, etc.
    width_pct: float = 0.0           # width as percentage of parent
    height_px: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tag": self.tag,
            "type": self.component_type,
            "layout": self.layout_direction,
            "grid_cols": self.grid_columns,
            "gap": self.gap,
            "padding": self.padding,
            "bounds": self.bounds,
            "palette_role": self.palette_role,
            "width_pct": round(self.width_pct, 1),
            "children": [c.to_dict() for c in self.children],
            "css": self.css_properties,
            "text": self.text_placeholder,
        }


def build_layout(ds: DesignSystem) -> List[ComponentSpec]:
    """Convert a DesignSystem (with structural tree) into ComponentSpecs.

    Args:
        ds: Complete DesignSystem from extraction

    Returns:
        List of top-level ComponentSpecs representing the page layout
    """
    tree = ds.structure
    root = tree.root
    page_w = root.w
    page_h = root.h

    # Build component type lookup from catalog
    comp_lookup = _build_component_lookup(ds.components)

    # Get spacing scale for snapping
    spacing_scale = ds.spacing.scale

    # Build palette role map for depth-based assignment
    palette = ds.palette.roles

    # Spatial grouping: if root has too many direct children (flat tree),
    # cluster them into logical sections by Y-band proximity
    if len(root.children) > 8:
        root = _group_flat_siblings(root, spacing_scale)

    # Convert tree recursively
    root_spec = _convert_node(
        root, page_w, page_h,
        comp_lookup, spacing_scale, palette,
        parent_bounds=(0, 0, page_w, page_h),
    )

    return root_spec.children if root_spec.children else [root_spec]


def _build_component_lookup(catalog: ComponentCatalog) -> Dict[Tuple, str]:
    """Build bounds → component_type lookup from detected components."""
    lookup = {}
    for comp in catalog.components:
        for bounds in comp.instances:
            lookup[tuple(bounds)] = comp.type
    return lookup


def _group_flat_siblings(
    root: LayoutNode,
    spacing_scale: List[int],
) -> LayoutNode:
    """Cluster flat children of root into logical sections by Y-band.

    When structure extraction produces a shallow tree (many direct children of root),
    this groups nearby nodes into synthetic section containers, producing a proper
    hierarchy: root → sections → rows → elements.

    Returns a new root with grouped children.
    """
    import copy
    children = sorted(root.children, key=lambda n: (n.y, n.x))
    if not children:
        return root

    # Step 1: Cluster by Y-band (vertical sections)
    # Two nodes are in the same Y-band if the gap between them is < threshold
    avg_h = sum(c.h for c in children) / len(children)
    y_threshold = max(avg_h * 1.5, 40)  # nodes within 1.5x avg height → same band

    y_bands: List[List[LayoutNode]] = []
    current_band = [children[0]]
    band_bottom = children[0].y + children[0].h

    for child in children[1:]:
        if child.y - band_bottom < y_threshold:
            current_band.append(child)
            band_bottom = max(band_bottom, child.y + child.h)
        else:
            y_bands.append(current_band)
            current_band = [child]
            band_bottom = child.y + child.h
    y_bands.append(current_band)

    # Step 2: Within each Y-band, group into rows by X-proximity
    next_id = max(c.id for c in children) + 100  # synthetic IDs start high
    new_children = []

    for band in y_bands:
        if len(band) == 1:
            # Single element in band — keep as-is
            new_children.append(band[0])
            continue

        # Sort by X to detect row groupings
        band_sorted = sorted(band, key=lambda n: n.x)

        # Check if band elements are on the same horizontal line (row)
        # or stacked vertically within the band
        y_coords = [n.y for n in band_sorted]
        y_spread = max(y_coords) - min(y_coords)
        max_h_in_band = max(n.h for n in band_sorted)

        if y_spread < max_h_in_band * 0.5:
            # All roughly same Y → single row container
            section = _make_container(next_id, band_sorted, root.depth + 1)
            next_id += 1
            new_children.append(section)
        else:
            # Mixed Y within band → sub-group by row lines
            rows = _sub_group_rows(band_sorted)
            if len(rows) == 1 and len(rows[0]) == len(band_sorted):
                section = _make_container(next_id, band_sorted, root.depth + 1)
                next_id += 1
                new_children.append(section)
            else:
                # Create section with row sub-containers
                row_containers = []
                for row_nodes in rows:
                    if len(row_nodes) == 1:
                        row_containers.append(row_nodes[0])
                    else:
                        row_c = _make_container(next_id, row_nodes, root.depth + 2)
                        next_id += 1
                        row_containers.append(row_c)

                section = _make_container(next_id, row_containers, root.depth + 1,
                                          use_nodes_as_children=True)
                next_id += 1
                new_children.append(section)

    # Build new root
    new_root = LayoutNode(
        id=root.id,
        bounds=root.bounds,
        children=new_children,
        node_type=root.node_type,
        depth=root.depth,
    )
    return new_root


def _sub_group_rows(nodes: List[LayoutNode]) -> List[List[LayoutNode]]:
    """Sub-group nodes into rows based on Y alignment."""
    if not nodes:
        return []

    sorted_by_y = sorted(nodes, key=lambda n: n.y)
    rows: List[List[LayoutNode]] = []
    current_row = [sorted_by_y[0]]

    for node in sorted_by_y[1:]:
        ref_y = current_row[0].y
        ref_h = max(n.h for n in current_row)
        if abs(node.y - ref_y) < ref_h * 0.5:
            current_row.append(node)
        else:
            rows.append(sorted(current_row, key=lambda n: n.x))
            current_row = [node]
    rows.append(sorted(current_row, key=lambda n: n.x))
    return rows


def _make_container(
    node_id: int,
    nodes: List[LayoutNode],
    depth: int,
    use_nodes_as_children: bool = False,
) -> LayoutNode:
    """Create a synthetic container LayoutNode enclosing the given nodes."""
    if use_nodes_as_children:
        children = nodes
    else:
        children = list(nodes)

    min_x = min(n.x for n in nodes)
    min_y = min(n.y for n in nodes)
    max_x = max(n.x + n.w for n in nodes)
    max_y = max(n.y + n.h for n in nodes)

    container = LayoutNode(
        id=node_id,
        bounds=(min_x, min_y, max_x - min_x, max_y - min_y),
        children=children,
        node_type="section",
        depth=depth,
    )

    # Update children depths
    for child in children:
        child.depth = depth + 1
        for sub in child.children:
            _update_child_depth(sub, depth + 2)

    return container


def _update_child_depth(node: LayoutNode, depth: int):
    """Recursively update depth."""
    node.depth = depth
    for child in node.children:
        _update_child_depth(child, depth + 1)


def _convert_node(
    node: LayoutNode,
    page_w: int,
    page_h: int,
    comp_lookup: Dict[Tuple, str],
    spacing_scale: List[int],
    palette: Dict[str, str],
    parent_bounds: Tuple[int, int, int, int],
) -> ComponentSpec:
    """Recursively convert a LayoutNode into a ComponentSpec."""

    # Determine component type
    comp_type = comp_lookup.get(node.bounds, node.node_type)

    # Determine HTML tag
    tag = _select_tag(comp_type, node.depth)

    # Determine palette role based on depth and type
    palette_role = _assign_palette_role(node, comp_type, palette)

    # Compute width as percentage of parent
    parent_w = max(parent_bounds[2], 1)
    width_pct = round((node.w / parent_w) * 100, 1)

    # Create spec
    spec = ComponentSpec(
        id=node.id,
        tag=tag,
        component_type=comp_type,
        bounds=node.bounds,
        depth=node.depth,
        is_repeated=node.is_repeated,
        palette_role=palette_role,
        width_pct=width_pct,
        height_px=node.h,
    )

    # Generate CSS properties
    spec.css_properties = _generate_css_props(
        node, comp_type, palette_role, palette, page_w, parent_bounds
    )

    # Add text placeholder based on component type
    spec.text_placeholder = _generate_placeholder(comp_type, node)

    if not node.children:
        return spec

    # Analyze children layout
    children = sorted(node.children, key=lambda n: (n.y, n.x))
    direction, grid_cols = _detect_layout_direction(children, node)
    gap = _compute_gap(children, direction, spacing_scale)
    padding = _compute_padding(node, children, spacing_scale)

    spec.layout_direction = direction
    spec.grid_columns = grid_cols
    spec.gap = gap
    spec.padding = padding

    # Add layout CSS
    if direction == "row":
        spec.css_properties["display"] = "flex"
        spec.css_properties["flex-direction"] = "row"
        spec.css_properties["align-items"] = "stretch"
        if gap > 0:
            spec.css_properties["gap"] = f"{gap}px"
    elif direction == "grid":
        spec.css_properties["display"] = "grid"
        spec.css_properties["grid-template-columns"] = f"repeat({grid_cols}, 1fr)"
        if gap > 0:
            spec.css_properties["gap"] = f"{gap}px"
    else:  # column
        spec.css_properties["display"] = "flex"
        spec.css_properties["flex-direction"] = "column"
        if gap > 0:
            spec.css_properties["gap"] = f"{gap}px"

    # Add padding
    if any(p > 0 for p in padding):
        t, r, b, l = padding
        if t == r == b == l:
            spec.css_properties["padding"] = f"{t}px"
        elif t == b and l == r:
            spec.css_properties["padding"] = f"{t}px {r}px"
        else:
            spec.css_properties["padding"] = f"{t}px {r}px {b}px {l}px"

    # Convert children
    for child in children:
        child_spec = _convert_node(
            child, page_w, page_h,
            comp_lookup, spacing_scale, palette,
            parent_bounds=node.bounds,
        )
        spec.children.append(child_spec)

    return spec


def _detect_layout_direction(
    children: List[LayoutNode],
    parent: LayoutNode,
) -> Tuple[str, int]:
    """Determine if children are arranged as row, column, or grid.

    Returns:
        (direction, grid_columns) where grid_columns > 0 only for grid layout
    """
    if len(children) <= 1:
        return "column", 0

    # Check if children form horizontal rows
    # Group by similar Y positions (within 20% of avg height tolerance)
    avg_h = sum(c.h for c in children) / len(children)
    tolerance = max(avg_h * 0.3, 10)

    rows = []
    current_row = [children[0]]
    for child in children[1:]:
        if abs(child.y - current_row[0].y) < tolerance:
            current_row.append(child)
        else:
            rows.append(current_row)
            current_row = [child]
    rows.append(current_row)

    # Single row with multiple items → flex-row or grid
    if len(rows) == 1 and len(children) > 1:
        # Check if widths are uniform → grid
        widths = [c.w for c in children]
        avg_w = sum(widths) / len(widths)
        if avg_w > 0:
            variance = sum((w - avg_w) ** 2 for w in widths) / len(widths)
            if variance / (avg_w ** 2) < 0.1:  # within 10% → grid
                return "grid", len(children)
        return "row", 0

    # Multiple rows with same column count → grid
    if len(rows) >= 2:
        col_counts = [len(r) for r in rows]
        if len(set(col_counts)) == 1 and col_counts[0] > 1:
            return "grid", col_counts[0]

    # Multiple rows, each with single or varying items → column
    # But check if first row is a sidebar + main layout
    if len(rows) == 1:
        return "row", 0

    return "column", 0


def _compute_gap(
    children: List[LayoutNode],
    direction: str,
    scale: List[int],
) -> int:
    """Compute gap between children and snap to spacing scale."""
    if len(children) < 2:
        return 0

    gaps = []
    if direction == "row" or direction == "grid":
        # Measure horizontal gaps between adjacent children
        sorted_h = sorted(children, key=lambda n: n.x)
        for i in range(len(sorted_h) - 1):
            gap = sorted_h[i + 1].x - (sorted_h[i].x + sorted_h[i].w)
            if gap > 0:
                gaps.append(gap)
    else:
        # Measure vertical gaps
        sorted_v = sorted(children, key=lambda n: n.y)
        for i in range(len(sorted_v) - 1):
            gap = sorted_v[i + 1].y - (sorted_v[i].y + sorted_v[i].h)
            if gap > 0:
                gaps.append(gap)

    if not gaps:
        return 0

    avg_gap = sum(gaps) / len(gaps)
    return _snap_to_scale(int(avg_gap), scale)


def _compute_padding(
    parent: LayoutNode,
    children: List[LayoutNode],
    scale: List[int],
) -> Tuple[int, int, int, int]:
    """Compute padding from parent edges to children and snap to scale."""
    if not children:
        return (0, 0, 0, 0)

    min_x = min(c.x for c in children)
    min_y = min(c.y for c in children)
    max_x = max(c.x + c.w for c in children)
    max_y = max(c.y + c.h for c in children)

    top = max(0, min_y - parent.y)
    right = max(0, (parent.x + parent.w) - max_x)
    bottom = max(0, (parent.y + parent.h) - max_y)
    left = max(0, min_x - parent.x)

    return (
        _snap_to_scale(top, scale),
        _snap_to_scale(right, scale),
        _snap_to_scale(bottom, scale),
        _snap_to_scale(left, scale),
    )


def _snap_to_scale(value: int, scale: List[int]) -> int:
    """Snap a pixel value to the nearest spacing scale value."""
    if value <= 0 or not scale:
        return 0
    return min(scale, key=lambda s: abs(s - value))


def _select_tag(comp_type: str, depth: int) -> str:
    """Select semantic HTML tag based on component type."""
    tag_map = {
        "page": "div",
        "sidebar": "aside",
        "navbar": "nav",
        "section": "section",
        "container": "div",
        "card": "div",
        "stat_card": "div",
        "button": "button",
        "badge": "span",
        "chip": "span",
        "avatar": "div",
        "icon": "div",
        "icon_button": "button",
        "text": "p",
        "image": "div",
        "input": "input",
        "divider": "hr",
        "list_item": "div",
        "table_row": "div",
        "footer": "footer",
    }
    return tag_map.get(comp_type, "div")


def _assign_palette_role(
    node: LayoutNode,
    comp_type: str,
    palette: Dict[str, str],
) -> str:
    """Assign a palette role based on component type and depth."""
    # Page-level background
    if node.depth == 0:
        return "bg_layer_0"

    # Sidebar
    if comp_type == "sidebar":
        return "bg_layer_1" if "bg_layer_1" in palette else "bg_layer_0"

    # Cards and containers at depth 1-2
    if comp_type in ("card", "stat_card", "container") and node.depth <= 2:
        if "bg_layer_1" in palette:
            return "bg_layer_1"

    # Nested containers
    if comp_type == "container" and node.depth > 2:
        if "bg_layer_2" in palette:
            return "bg_layer_2"

    # Buttons → accent
    if comp_type in ("button", "icon_button"):
        return "accent_primary" if "accent_primary" in palette else "text_primary"

    # Badges → accent secondary or text
    if comp_type in ("badge", "chip"):
        return "accent_secondary" if "accent_secondary" in palette else "accent_primary"

    # Text
    if comp_type == "text":
        return "text_primary"

    return ""


def _generate_css_props(
    node: LayoutNode,
    comp_type: str,
    palette_role: str,
    palette: Dict[str, str],
    page_w: int,
    parent_bounds: Tuple[int, int, int, int],
) -> Dict[str, str]:
    """Generate CSS properties for a component."""
    props: Dict[str, str] = {}
    parent_w = max(parent_bounds[2], 1)

    # Background color from palette role
    if palette_role and palette_role in palette:
        css_var = palette_role.replace("_", "-")
        props["background"] = f"var(--{css_var})"

    # Width — use percentage for flex children, fixed for sidebar
    if comp_type == "sidebar":
        props["width"] = f"{node.w}px"
        props["flex-shrink"] = "0"
    elif comp_type in ("card", "stat_card") and node.w < parent_w * 0.9:
        # Let grid/flex handle width
        pass
    elif node.depth == 0:
        props["width"] = "100%"
        props["min-height"] = "100vh"

    # Height for specific components
    if comp_type == "navbar":
        props["height"] = f"{node.h}px"
    elif comp_type == "section" and node.h > 0:
        props["min-height"] = f"{node.h}px"

    # Border radius
    if comp_type in ("card", "stat_card"):
        props["border-radius"] = "var(--radius-surface)"
        props["border"] = "var(--border, 1px solid rgba(255,255,255,0.08))"
    elif comp_type == "button":
        props["border-radius"] = "var(--radius-button)"
    elif comp_type in ("badge", "chip"):
        props["border-radius"] = "var(--radius-pill)"
    elif comp_type == "avatar":
        props["border-radius"] = "50%"
        props["width"] = f"{node.w}px"
        props["height"] = f"{node.h}px"

    # Text colors
    if comp_type == "text":
        if node.h > 20:
            props["font-size"] = f"{min(node.h, 48)}px"
            props["font-weight"] = "600"
            props["color"] = "var(--text-primary)"
        else:
            props["font-size"] = f"{max(node.h, 12)}px"
            props["color"] = "var(--text-secondary, var(--text-primary))"

    # Button styling
    if comp_type == "button":
        props["color"] = "var(--bg-layer-0)"
        props["background"] = "var(--accent-primary)"
        props["border"] = "none"
        props["cursor"] = "pointer"
        props["font-size"] = "14px"
        props["font-weight"] = "500"
        props["padding"] = "8px 20px"

    # Badge styling
    if comp_type in ("badge", "chip"):
        props["font-size"] = "12px"
        props["padding"] = "4px 12px"

    return props


def _generate_placeholder(comp_type: str, node: LayoutNode) -> str:
    """Generate placeholder text for the LLM to replace."""
    placeholders = {
        "button": "[Button Text]",
        "badge": "[Badge]",
        "chip": "[Chip Label]",
        "text": "[Text Content]" if node.h <= 20 else "[Heading]",
        "stat_card": "[Stat Card: Value + Label]",
        "card": "[Card Content]",
        "input": "[Search or Input]",
        "avatar": "[Avatar]",
        "icon": "[Icon]",
        "icon_button": "[Icon Button]",
        "navbar": "[Navigation Bar]",
        "sidebar": "[Sidebar Navigation]",
    }
    return placeholders.get(comp_type, "")


def specs_to_prompt(specs: List[ComponentSpec], ds: DesignSystem) -> str:
    """Convert ComponentSpecs into a structured prompt for LLM code generation.

    This produces a detailed spec that any LLM can follow to generate
    React/Tailwind code matching the extracted layout.
    """
    ds_dict = ds.to_dict()

    lines = [
        "# ANVIL Layout Specification",
        "",
        "Generate a React + Tailwind CSS page that EXACTLY matches this layout.",
        "Use the CSS custom properties defined below. Do NOT hardcode colors.",
        "",
        "## Design Tokens",
        "```css",
    ]

    # Palette
    for role, hex_val in sorted(ds.palette.roles.items()):
        css_var = role.replace("_", "-")
        lines.append(f"  --{css_var}: {hex_val};")

    # Spacing
    lines.append(f"  --spacing-base: {ds.spacing.base}px;")

    # Typography
    typo = ds.typography.to_dict()
    lines.append(f"  --font-sans: {typo['family_sans']};")
    lines.append(f"  --font-mono: {typo['family_mono']};")

    # Radii
    radii = ds._extract_radii()
    for name, val in radii.items():
        lines.append(f"  --radius-{name}: {val};")

    # Effects
    for key, val in ds.effects.to_dict().items():
        lines.append(f"  --{key.replace('_', '-')}: {val};")

    lines.append("```")
    lines.append("")

    # Page metadata
    meta = ds_dict["meta"]
    lines.append(f"## Page: {meta['page_type']} ({'dark' if meta['is_dark_mode'] else 'light'} mode)")
    lines.append(f"## Size: {meta['image_size']}")
    lines.append("")

    # Component tree
    lines.append("## Component Layout Tree")
    lines.append("")
    for spec in specs:
        _spec_to_text(spec, lines, indent=0)

    lines.append("")
    lines.append("## Rules")
    lines.append("- Use `className` with Tailwind utilities where possible")
    lines.append("- Use CSS custom properties (var(--xxx)) for all colors, spacing, radii")
    lines.append("- Match the exact layout direction (flex-row, flex-col, grid)")
    lines.append("- Match the exact gap and padding values")
    lines.append("- Replace [placeholders] with realistic content matching the component type")
    lines.append("- For stat_cards, use realistic metric data")
    lines.append("- For sidebar, use realistic nav items")
    lines.append("- Export as a single React functional component")

    return "\n".join(lines)


def _spec_to_text(spec: ComponentSpec, lines: List[str], indent: int):
    """Recursively convert a ComponentSpec to indented text."""
    prefix = "  " * indent
    bounds_str = f"({spec.bounds[0]},{spec.bounds[1]} {spec.bounds[2]}x{spec.bounds[3]})"

    layout_info = spec.layout_direction
    if spec.grid_columns > 0:
        layout_info = f"grid-{spec.grid_columns}col"
    if spec.gap > 0:
        layout_info += f" gap={spec.gap}px"

    line = f"{prefix}<{spec.tag}> {spec.component_type} {bounds_str} layout={layout_info}"
    if spec.palette_role:
        line += f" bg={spec.palette_role}"
    if spec.text_placeholder:
        line += f' text="{spec.text_placeholder}"'

    # Key CSS props
    key_css = {k: v for k, v in spec.css_properties.items()
               if k in ("border-radius", "width", "height", "min-height")}
    if key_css:
        css_str = "; ".join(f"{k}: {v}" for k, v in key_css.items())
        line += f" style=[{css_str}]"

    if spec.padding and any(p > 0 for p in spec.padding):
        line += f" padding={spec.padding}"

    lines.append(line)

    for child in spec.children:
        _spec_to_text(child, lines, indent + 1)
