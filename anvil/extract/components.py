"""
ANVIL Component Detector — Finds repeating UI patterns and classifies them.
Detects cards, buttons, avatars, badges, list items, inputs, navbars from structure.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from .structure import StructuralTree, LayoutNode


COMPONENT_TYPES = [
    "card", "button", "avatar", "badge", "tag", "list_item",
    "input", "navbar", "footer", "sidebar", "stat_card",
    "table_row", "chip", "icon_button", "divider",
]


@dataclass
class DetectedComponent:
    """A classified UI component pattern."""
    type: str
    instances: List[Tuple[int, int, int, int]]  # list of bounds
    count: int = 0
    avg_width: int = 0
    avg_height: int = 0
    tokens_used: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "count": self.count,
            "avg_size": f"{self.avg_width}x{self.avg_height}",
            "instances": self.instances,
        }


@dataclass
class ComponentCatalog:
    """Complete component detection result."""
    components: List[DetectedComponent]
    total_instances: int = 0

    def to_dict(self) -> dict:
        return {
            "components": [c.to_dict() for c in self.components],
            "total_instances": self.total_instances,
            "types_found": [c.type for c in self.components],
        }


def detect_components(tree: StructuralTree) -> ComponentCatalog:
    """Detect UI component patterns from the structural tree.

    Args:
        tree: StructuralTree from structure.py

    Returns:
        ComponentCatalog with classified components
    """
    components = []

    # Find repeat groups and classify them
    _classify_repeat_groups(tree.root, tree.repeat_groups, components)

    # Detect singleton components by shape/size heuristics
    _detect_singletons(tree.root, components)

    # Deduplicate
    seen_types = set()
    unique = []
    for c in components:
        if c.type not in seen_types or c.type in ("card", "list_item"):
            unique.append(c)
            seen_types.add(c.type)

    total = sum(c.count for c in unique)

    return ComponentCatalog(
        components=unique,
        total_instances=total,
    )


def _classify_repeat_groups(
    root: LayoutNode,
    groups: Dict[int, List[int]],
    components: List[DetectedComponent],
):
    """Classify repeat groups into component types."""
    # Build id → node map
    node_map: Dict[int, LayoutNode] = {}
    _build_node_map(root, node_map)

    for group_id, node_ids in groups.items():
        nodes = [node_map[nid] for nid in node_ids if nid in node_map]
        if len(nodes) < 2:
            continue

        # Get representative node
        rep = nodes[0]
        comp_type = _classify_by_shape(rep)

        instances = [n.bounds for n in nodes]
        avg_w = sum(n.w for n in nodes) // len(nodes)
        avg_h = sum(n.h for n in nodes) // len(nodes)

        components.append(DetectedComponent(
            type=comp_type,
            instances=instances,
            count=len(nodes),
            avg_width=avg_w,
            avg_height=avg_h,
        ))


def _detect_singletons(root: LayoutNode, components: List[DetectedComponent]):
    """Detect non-repeating components by shape heuristics."""
    existing_bounds = set()
    for c in components:
        for b in c.instances:
            existing_bounds.add(b)

    def _walk(node: LayoutNode):
        if node.bounds in existing_bounds or node.depth < 1:
            for child in node.children:
                _walk(child)
            return

        comp_type = _classify_by_shape(node)
        if comp_type != "container":
            components.append(DetectedComponent(
                type=comp_type,
                instances=[node.bounds],
                count=1,
                avg_width=node.w,
                avg_height=node.h,
            ))

        for child in node.children:
            _walk(child)

    _walk(root)


def _classify_by_shape(node: LayoutNode) -> str:
    """Classify a node into a component type based on dimensions and structure."""
    w, h = node.w, node.h
    aspect = w / max(h, 1)
    child_count = len(node.children)
    area = w * h

    # Avatar: small circle-ish (24-56px)
    if 16 <= w <= 56 and 16 <= h <= 56 and 0.7 < aspect < 1.4:
        return "avatar"

    # Icon button: small square with icon child
    if 24 <= w <= 48 and 24 <= h <= 48 and child_count <= 1:
        return "icon_button"

    # Badge/Tag: very small, wide
    if w < 80 and h < 32 and aspect > 1.5:
        return "badge"

    # Button: small-medium, wide, few children
    if 60 <= w <= 300 and 24 <= h <= 56 and aspect > 2 and child_count <= 3:
        return "button"

    # Input: medium width, short height, wide aspect
    if w > 150 and 28 <= h <= 52 and aspect > 3:
        return "input"

    # Divider: very wide, very thin
    if aspect > 10 and h <= 4:
        return "divider"

    # Navbar: full-width, short
    if w > 500 and h < 80:
        return "navbar"

    # Stat card: medium rectangle with few children
    if 100 <= w <= 350 and 60 <= h <= 200 and child_count <= 5:
        return "stat_card"

    # List item: wide, short, with children
    if aspect > 3 and 30 <= h <= 60 and child_count >= 1:
        return "list_item"

    # Card: medium-large rectangle with children
    if w > 150 and h > 100 and child_count >= 2:
        return "card"

    # Table row: very wide, short
    if aspect > 5 and 25 <= h <= 50:
        return "table_row"

    # Chip: small pill-shaped
    if 60 <= w <= 200 and 24 <= h <= 40:
        return "chip"

    return "container"


def _build_node_map(node: LayoutNode, node_map: Dict[int, LayoutNode]):
    """Build flat id → node lookup."""
    node_map[node.id] = node
    for child in node.children:
        _build_node_map(child, node_map)
