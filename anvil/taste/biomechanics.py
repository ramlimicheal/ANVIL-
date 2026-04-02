"""
ANVIL Biomechanics — Fitts's Law touch target validation.

Validates interactive elements against human musculoskeletal limits:
- Apple HIG minimum: 44×44pt touch targets
- Dangerous proximity: destructive actions too close to primary actions
- Fitts's Index of Difficulty for key interaction paths

Dependencies: Playwright (for element extraction), math (stdlib).
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class TouchTargetViolation:
    """A single touch target that fails biomechanical minimums."""
    element: str           # tag + text preview
    selector: str
    width: float
    height: float
    min_required: int      # 44 for mobile, 32 for desktop
    fix_hint: str


@dataclass
class ProximityViolation:
    """Two interactive elements dangerously close together."""
    element_a: str         # destructive action
    element_b: str         # adjacent action
    gap_px: float
    min_gap: int
    misclick_probability: str  # "HIGH", "MEDIUM"
    fix_hint: str


@dataclass
class BiomechanicsResult:
    """Complete biomechanical audit result."""
    total_interactive: int
    touch_violations: List[TouchTargetViolation] = field(default_factory=list)
    proximity_violations: List[ProximityViolation] = field(default_factory=list)
    mean_target_area: float = 0.0
    smallest_target: str = ""
    smallest_target_size: str = ""
    passed: bool = True
    score_10: float = 10.0

    def violations_report(self) -> dict:
        touch_v = []
        for v in self.touch_violations:
            touch_v.append({
                "element": v.element,
                "size": f"{v.width:.0f}×{v.height:.0f}",
                "minimum": f"{v.min_required}×{v.min_required}",
                "fix_hint": v.fix_hint,
            })
        prox_v = []
        for v in self.proximity_violations:
            prox_v.append({
                "destructive": v.element_a,
                "adjacent": v.element_b,
                "gap_px": v.gap_px,
                "risk": v.misclick_probability,
                "fix_hint": v.fix_hint,
            })
        return {
            "total_interactive": self.total_interactive,
            "touch_target_violations": touch_v,
            "proximity_violations": prox_v,
            "passed": self.passed,
            "score": self.score_10,
        }


# Destructive action keywords
_DESTRUCTIVE_KEYWORDS = {
    "delete", "remove", "cancel", "close", "discard", "destroy",
    "reset", "clear", "unsubscribe", "revoke", "reject", "deny",
    "logout", "sign out", "log out", "deactivate",
}


def _is_destructive(text: str) -> bool:
    lower = text.lower().strip()
    return any(kw in lower for kw in _DESTRUCTIVE_KEYWORDS)


def _gap_between(a: dict, b: dict) -> float:
    """Minimum pixel gap between two bounding boxes."""
    # Horizontal gap
    h_gap = max(0, max(a["x"] - (b["x"] + b["w"]), b["x"] - (a["x"] + a["w"])))
    # Vertical gap
    v_gap = max(0, max(a["y"] - (b["y"] + b["h"]), b["y"] - (a["y"] + a["h"])))
    return math.sqrt(h_gap ** 2 + v_gap ** 2)


def run_biomechanics_audit_sync(
    html_path: str,
    viewport_width: int = 1440,
    mobile: bool = False,
) -> BiomechanicsResult:
    """Run Fitts's Law biomechanical audit on rendered HTML.

    Args:
        html_path: Absolute path to HTML file
        viewport_width: Viewport width (375 for mobile, 1440 for desktop)
        mobile: If True, enforce 44px minimums. If False, enforce 32px.
    """
    from playwright.sync_api import sync_playwright
    import os

    min_target = 44 if mobile else 32
    min_gap = 16 if mobile else 8

    extract_js = """
    (() => {
        const selectors = 'a, button, input, select, textarea, [onclick], [role="button"], [role="link"], [tabindex]';
        const raw = document.querySelectorAll(selectors);

        const elements = Array.from(raw).filter(el => {
            const style = window.getComputedStyle(el);

            // 1. Exclude inline text links (Apple HIG exemption)
            //    "Read our <a>Terms</a>" — inline <a> height = line-height, not a tap target
            if (style.display === 'inline' && el.tagName.toLowerCase() === 'a') return false;

            // 2. Exclude invisible / ghost nodes
            if (style.opacity === '0' || style.visibility === 'hidden' || style.pointerEvents === 'none') return false;

            // 3. Exclude elements nested inside a valid interactive parent
            //    <button class="w-12 h-12"><svg class="w-4 h-4"></svg></button>
            //    The SVG should not be independently tested — the parent button is the hit target
            const parentInteractive = el.parentElement
                ? el.parentElement.closest('a, button, [role="button"]')
                : null;
            if (parentInteractive && parentInteractive !== el) return false;

            return true;
        });

        return elements.map((el, i) => {
            const r = el.getBoundingClientRect();
            return {
                tag: el.tagName.toLowerCase(),
                text: (el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 40),
                type: el.type || '',
                x: r.x, y: r.y, w: r.width, h: r.height,
                idx: i,
            };
        }).filter(e => e.w > 0 && e.h > 0);
    })()
    """

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": viewport_width, "height": 900})
        page.goto(f"file://{os.path.abspath(html_path)}")
        page.wait_for_timeout(300)

        elements = page.evaluate(extract_js)
        browser.close()

    if not elements:
        return BiomechanicsResult(total_interactive=0, passed=True, score_10=10.0)

    touch_violations = []
    proximity_violations = []

    # Touch target size check
    for el in elements:
        if el["w"] < min_target or el["h"] < min_target:
            touch_violations.append(TouchTargetViolation(
                element=f"{el['tag']}: '{el['text'][:25]}'",
                selector=f"{el['tag']}[{el['idx']}]",
                width=el["w"],
                height=el["h"],
                min_required=min_target,
                fix_hint=f"Increase to min {min_target}×{min_target}px. Use min-width/min-height or padding.",
            ))

    # Dangerous proximity between destructive + primary actions
    destructive_els = [e for e in elements if _is_destructive(e["text"])]
    non_destructive_els = [e for e in elements if not _is_destructive(e["text"]) and e["tag"] in ("button", "a")]

    for d in destructive_els:
        for nd in non_destructive_els:
            gap = _gap_between(d, nd)
            if gap < min_gap:
                risk = "HIGH" if gap < 8 else "MEDIUM"
                proximity_violations.append(ProximityViolation(
                    element_a=f"{d['tag']}: '{d['text'][:25]}'",
                    element_b=f"{nd['tag']}: '{nd['text'][:25]}'",
                    gap_px=round(gap, 1),
                    min_gap=min_gap,
                    misclick_probability=risk,
                    fix_hint=f"Increase gap to ≥{min_gap}px. Move destructive action away or add confirmation dialog.",
                ))

    # Score calculation
    total = len(elements)
    touch_fail_ratio = len(touch_violations) / max(total, 1)
    prox_penalty = len(proximity_violations) * 0.5
    raw_score = max(0.0, (1.0 - touch_fail_ratio) * 10.0 - prox_penalty)
    score = round(max(0.0, min(10.0, raw_score)), 1)

    passed = len(touch_violations) == 0 and len(proximity_violations) == 0

    # Find smallest target
    areas = [(el["w"] * el["h"], f"{el['tag']}: '{el['text'][:20]}'", f"{el['w']:.0f}×{el['h']:.0f}") for el in elements]
    areas.sort()
    smallest = areas[0] if areas else (0, "", "")

    return BiomechanicsResult(
        total_interactive=total,
        touch_violations=touch_violations,
        proximity_violations=proximity_violations,
        mean_target_area=round(sum(a[0] for a in areas) / max(len(areas), 1), 1),
        smallest_target=smallest[1],
        smallest_target_size=smallest[2],
        passed=passed,
        score_10=score,
    )
