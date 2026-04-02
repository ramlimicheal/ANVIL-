"""
ANVIL Structural Decomposition — Extracts layout hierarchy from screenshots.
Builds a component tree from pixels: Page → Sections → Containers → Elements.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

try:
    import cv2
    import numpy as np
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


@dataclass
class LayoutNode:
    """A node in the structural layout tree."""
    id: int
    bounds: Tuple[int, int, int, int]  # x, y, w, h
    children: List["LayoutNode"] = field(default_factory=list)
    node_type: str = "container"  # container, text, image, icon, component
    depth: int = 0
    is_repeated: bool = False  # part of a repeating pattern
    repeat_group: int = -1

    @property
    def x(self) -> int: return self.bounds[0]
    @property
    def y(self) -> int: return self.bounds[1]
    @property
    def w(self) -> int: return self.bounds[2]
    @property
    def h(self) -> int: return self.bounds[3]
    @property
    def area(self) -> int: return self.w * self.h
    @property
    def cx(self) -> float: return self.x + self.w / 2
    @property
    def cy(self) -> float: return self.y + self.h / 2

    def contains(self, other: "LayoutNode") -> bool:
        return (self.x <= other.x and self.y <= other.y
                and self.x + self.w >= other.x + other.w
                and self.y + self.h >= other.y + other.h
                and self.area > other.area)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bounds": self.bounds,
            "type": self.node_type,
            "depth": self.depth,
            "children": [c.to_dict() for c in self.children],
            "is_repeated": self.is_repeated,
        }


@dataclass
class GridSpec:
    """Detected grid specification."""
    columns: int = 1
    gutter: int = 0
    margin_left: int = 0
    margin_right: int = 0
    column_width: int = 0


@dataclass
class StructuralTree:
    """Complete structural decomposition result."""
    root: LayoutNode
    grid: GridSpec
    total_nodes: int = 0
    max_depth: int = 0
    repeat_groups: Dict[int, List[int]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "tree": self.root.to_dict(),
            "grid": {
                "columns": self.grid.columns,
                "gutter": self.grid.gutter,
                "margin_left": self.grid.margin_left,
                "margin_right": self.grid.margin_right,
                "column_width": self.grid.column_width,
            },
            "total_nodes": self.total_nodes,
            "max_depth": self.max_depth,
            "repeat_groups": self.repeat_groups,
        }


def extract_structure(
    image_path: str,
    min_area: int = 400,
    min_dimension: int = 10,
) -> StructuralTree:
    """Extract structural layout tree from a screenshot.

    Args:
        image_path: Path to screenshot
        min_area: Minimum rectangle area to detect (filters noise)
        min_dimension: Minimum width or height

    Returns:
        StructuralTree with hierarchical layout
    """
    if not HAS_DEPS:
        raise ImportError("opencv-python and numpy required")

    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not read: {image_path}")

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Detect rectangular regions
    rects = _detect_rectangles(gray, w, h, min_area, min_dimension)

    # Build hierarchy
    root = LayoutNode(id=0, bounds=(0, 0, w, h), node_type="page", depth=0)
    nodes = [root] + rects

    _build_hierarchy(root, rects)

    # Classify node types
    _classify_nodes(gray, root)

    # Detect grid
    grid = _detect_grid(root, w)

    # Detect repeating patterns
    repeat_groups = _detect_repeats(root)

    # Count stats
    total, max_depth = _count_tree(root)

    return StructuralTree(
        root=root,
        grid=grid,
        total_nodes=total,
        max_depth=max_depth,
        repeat_groups=repeat_groups,
    )


def _detect_rectangles(
    gray: "np.ndarray", w: int, h: int,
    min_area: int, min_dim: int,
) -> List[LayoutNode]:
    """Detect rectangular regions using edge detection and contour finding."""
    # Adaptive threshold for better edge detection on varying backgrounds
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 30, 100)

    # Dilate to close small gaps in edges
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilated = cv2.dilate(edges, kernel, iterations=2)

    contours, _ = cv2.findContours(dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    rects = []
    seen = set()
    node_id = 1

    for contour in contours:
        # Approximate to polygon
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)

        # Get bounding rectangle
        x, y, rw, rh = cv2.boundingRect(contour)

        # Filter
        if rw * rh < min_area or rw < min_dim or rh < min_dim:
            continue
        if rw > w * 0.98 and rh > h * 0.98:  # skip full-page rect
            continue

        # Deduplicate (within 5px tolerance)
        key = (round(x / 5), round(y / 5), round(rw / 5), round(rh / 5))
        if key in seen:
            continue
        seen.add(key)

        node = LayoutNode(id=node_id, bounds=(x, y, rw, rh), depth=1)
        rects.append(node)
        node_id += 1

    # Sort by area descending (larger containers first)
    rects.sort(key=lambda n: n.area, reverse=True)

    return rects


def _build_hierarchy(root: LayoutNode, nodes: List[LayoutNode]):
    """Build parent-child relationships based on containment."""
    # Sort by area descending so we process containers before children
    sorted_nodes = sorted(nodes, key=lambda n: n.area, reverse=True)

    for node in sorted_nodes:
        _insert_into_tree(root, node)


def _insert_into_tree(parent: LayoutNode, node: LayoutNode):
    """Insert a node into the tree under the smallest containing parent."""
    # Try to insert into existing children first (find tightest fit)
    for child in parent.children:
        if child.contains(node):
            _insert_into_tree(child, node)
            return

    # Check if this node should become parent of existing children
    adopted = []
    remaining = []
    for child in parent.children:
        if node.contains(child):
            adopted.append(child)
        else:
            remaining.append(child)

    node.children = adopted
    node.depth = parent.depth + 1
    for child in adopted:
        _update_depth(child, node.depth + 1)

    parent.children = remaining + [node]


def _update_depth(node: LayoutNode, depth: int):
    """Recursively update depth of a node and its children."""
    node.depth = depth
    for child in node.children:
        _update_depth(child, depth + 1)


def _classify_nodes(gray: "np.ndarray", node: LayoutNode):
    """Classify node types based on visual properties."""
    for child in node.children:
        x, y, w, h = child.bounds

        # Safe crop
        region = gray[max(0, y):min(gray.shape[0], y + h),
                       max(0, x):min(gray.shape[1], x + w)]
        if region.size == 0:
            continue

        # Small square → icon
        if w < 50 and h < 50 and 0.7 < w / max(h, 1) < 1.4:
            child.node_type = "icon"
        # Wide thin → text line
        elif w > h * 3 and h < 40:
            child.node_type = "text"
        # Very wide full-width → section
        elif w > gray.shape[1] * 0.8:
            child.node_type = "section"
        # Has many children → container
        elif len(child.children) > 0:
            child.node_type = "container"
        # Medium with low edge density → image/placeholder
        elif w > 80 and h > 80:
            edges = cv2.Canny(region, 50, 150)
            density = edges.mean()
            if density < 2.0:
                child.node_type = "image"
            else:
                child.node_type = "container"

        _classify_nodes(gray, child)


def _detect_grid(root: LayoutNode, page_width: int) -> GridSpec:
    """Detect grid system from direct children of the root."""
    # Look at depth-1 and depth-2 children for column patterns
    candidates = []
    for child in root.children:
        if len(child.children) >= 2:
            candidates.append(child)

    best_grid = GridSpec(columns=1)

    for parent in candidates:
        kids = sorted(parent.children, key=lambda n: n.x)
        if len(kids) < 2:
            continue

        # Check if children have similar widths
        widths = [k.w for k in kids]
        mean_w = sum(widths) / len(widths)
        if mean_w == 0:
            continue

        width_variance = sum((w - mean_w) ** 2 for w in widths) / len(widths)
        relative_variance = width_variance / (mean_w ** 2)

        if relative_variance < 0.05:  # within 5% → grid
            # Compute gutters
            gutters = []
            for i in range(len(kids) - 1):
                gap = kids[i + 1].x - (kids[i].x + kids[i].w)
                if gap > 0:
                    gutters.append(gap)

            gutter = int(sum(gutters) / len(gutters)) if gutters else 0
            margin_left = kids[0].x - parent.x
            margin_right = (parent.x + parent.w) - (kids[-1].x + kids[-1].w)

            grid = GridSpec(
                columns=len(kids),
                gutter=gutter,
                margin_left=margin_left,
                margin_right=margin_right,
                column_width=int(mean_w),
            )

            if grid.columns > best_grid.columns:
                best_grid = grid

    return best_grid


def _detect_repeats(root: LayoutNode) -> Dict[int, List[int]]:
    """Detect repeating patterns among sibling nodes."""
    group_id = 0
    groups: Dict[int, List[int]] = {}

    def _check_siblings(parent: LayoutNode):
        nonlocal group_id
        if len(parent.children) < 2:
            for child in parent.children:
                _check_siblings(child)
            return

        # Group children by similar dimensions (within 10% tolerance)
        used = set()
        for i, a in enumerate(parent.children):
            if i in used:
                continue
            group = [a]
            for j, b in enumerate(parent.children):
                if j <= i or j in used:
                    continue
                if _similar_size(a, b, tolerance=0.1):
                    group.append(b)
                    used.add(j)

            if len(group) >= 2:
                gid = group_id
                group_id += 1
                groups[gid] = [n.id for n in group]
                for n in group:
                    n.is_repeated = True
                    n.repeat_group = gid

        for child in parent.children:
            _check_siblings(child)

    _check_siblings(root)
    return groups


def _similar_size(a: LayoutNode, b: LayoutNode, tolerance: float = 0.1) -> bool:
    """Check if two nodes have similar dimensions."""
    if a.w == 0 or a.h == 0:
        return False
    w_ratio = abs(a.w - b.w) / max(a.w, 1)
    h_ratio = abs(a.h - b.h) / max(a.h, 1)
    return w_ratio < tolerance and h_ratio < tolerance


def _count_tree(node: LayoutNode) -> Tuple[int, int]:
    """Count total nodes and max depth."""
    total = 1
    max_d = node.depth
    for child in node.children:
        ct, cd = _count_tree(child)
        total += ct
        max_d = max(max_d, cd)
    return total, max_d
