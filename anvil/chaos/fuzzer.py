"""
ANVIL Chaos Gate — Topological data fuzzing for layout resilience.

Injects extreme data mutations (inflated text, multiplied children,
empty content, RTL strings, extreme-length inputs) via Playwright,
then validates that zero layout breakages occur.

A layout that breaks under mutation is structurally brittle —
the AI hardcoded for happy-path data instead of engineering
defensive CSS (overflow, flex-wrap, min-width, text-overflow).

Tier 1 Boolean Gate: ANY mutation causing overflow = HARD FAIL.

Dependencies: Playwright (already used in validate_output).
"""

from dataclasses import dataclass, field
from typing import Dict, List


# JS mutation scripts injected into the rendered page
CHAOS_MUTATIONS: Dict[str, str] = {
    "inflate_text_3x": """
        document.querySelectorAll('*').forEach(el => {
            for (const node of el.childNodes) {
                if (node.nodeType === 3 && node.textContent.trim().length > 0) {
                    node.textContent = node.textContent.repeat(3);
                }
            }
        });
    """,

    "extreme_word": """
        document.querySelectorAll('h1,h2,h3,h4,h5,h6,p,span,a,button,label,li,td,th').forEach(el => {
            if (el.children.length === 0 && el.textContent.trim().length > 0) {
                el.textContent = 'Rechtsschutzversicherungsgesellschaften_' + el.textContent;
            }
        });
    """,

    "multiply_children_15x": """
        const targets = document.querySelectorAll('[class*="card"],[class*="item"],[class*="col"],li,.grid>*,.flex>*');
        const seen = new Set();
        targets.forEach(el => {
            const parent = el.parentNode;
            if (seen.has(parent)) return;
            seen.add(parent);
            for (let i = 0; i < 15; i++) parent.appendChild(el.cloneNode(true));
        });
    """,

    "empty_all_text": """
        document.querySelectorAll('p,span,h1,h2,h3,h4,h5,h6,a,button,label,li,td,th').forEach(el => {
            if (el.children.length === 0) el.textContent = '';
        });
    """,

    "rtl_arabic": """
        document.querySelectorAll('*').forEach(el => {
            for (const node of el.childNodes) {
                if (node.nodeType === 3 && node.textContent.trim().length > 1) {
                    node.textContent = '\\u0645\\u0631\\u062D\\u0628\\u0627 \\u0628\\u0627\\u0644\\u0639\\u0627\\u0644\\u0645 \\u0627\\u0644\\u0639\\u0631\\u0628\\u064A';
                }
            }
        });
    """,

    "extreme_input_values": """
        document.querySelectorAll('input,textarea').forEach(el => {
            el.value = 'A'.repeat(500);
            el.dispatchEvent(new Event('input', {bubbles: true}));
        });
    """,

    "single_char_content": """
        document.querySelectorAll('h1,h2,h3,p,span,a,button,label').forEach(el => {
            if (el.children.length === 0 && el.textContent.trim().length > 0) {
                el.textContent = 'X';
            }
        });
    """,
}

# JS to detect layout breakage
# FIX: Filters out absolute/fixed positioned elements and negative-margin
# intentional overlaps (avatar face-piles, notification badges, tooltips)
BREAKAGE_CHECK_JS = """
(() => {
    const docEl = document.documentElement;
    const viewportW = window.innerWidth;

    // Horizontal scroll detection
    const hasHScroll = docEl.scrollWidth > viewportW + 2;

    // Count elements overflowing viewport (skip absolute/fixed)
    let overflowCount = 0;
    const all = document.querySelectorAll('*');
    for (const el of all) {
        const style = window.getComputedStyle(el);
        // Skip elements that intentionally escape document flow
        if (style.position === 'absolute' || style.position === 'fixed') continue;
        // Skip elements with intentional overflow (carousels, sliders)
        if (style.overflowX === 'scroll' || style.overflowX === 'auto') continue;
        const r = el.getBoundingClientRect();
        if (r.width > 0 && (r.right > viewportW + 5 || r.left < -5)) {
            overflowCount++;
        }
    }

    // Check for overlapping siblings (bounding box intersection)
    let overlapCount = 0;
    const containers = document.querySelectorAll('.grid, .flex, [style*="flex"], [style*="grid"], ul, ol, nav');
    for (const container of containers) {
        const children = Array.from(container.children);
        for (let i = 0; i < children.length; i++) {
            const styleA = window.getComputedStyle(children[i]);
            // Skip absolute/fixed elements (badges, tooltips, modals)
            if (styleA.position === 'absolute' || styleA.position === 'fixed') continue;
            // Skip intentional negative margins (avatar stacks)
            if (parseFloat(styleA.marginLeft) < -2 || parseFloat(styleA.marginRight) < -2) continue;

            const a = children[i].getBoundingClientRect();
            if (a.width === 0 || a.height === 0) continue;
            for (let j = i + 1; j < Math.min(children.length, i + 5); j++) {
                const styleB = window.getComputedStyle(children[j]);
                if (styleB.position === 'absolute' || styleB.position === 'fixed') continue;
                if (parseFloat(styleB.marginLeft) < -2 || parseFloat(styleB.marginRight) < -2) continue;

                const b = children[j].getBoundingClientRect();
                if (b.width === 0 || b.height === 0) continue;
                const xOverlap = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
                const yOverlap = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
                if (xOverlap > 3 && yOverlap > 3) overlapCount++;
            }
        }
    }

    return { hasHScroll, overflowCount, overlapCount };
})()
"""


@dataclass
class MutationResult:
    """Result of a single chaos mutation."""
    name: str
    has_horizontal_scroll: bool
    overflow_elements: int
    overlap_count: int
    passed: bool

    @property
    def issues(self) -> List[str]:
        problems = []
        if self.has_horizontal_scroll:
            problems.append("horizontal scrollbar triggered")
        if self.overflow_elements > 0:
            problems.append(f"{self.overflow_elements} elements overflow viewport")
        if self.overlap_count > 0:
            problems.append(f"{self.overlap_count} element overlaps detected")
        return problems


@dataclass
class ChaosResult:
    """Complete chaos gate result."""
    mutations_run: int
    mutations_passed: int
    mutations_failed: int
    resilience_score: float     # 0.0 - 1.0
    passed: bool                # ALL mutations must pass for Tier 1
    results: List[MutationResult] = field(default_factory=list)
    score_10: float = 0.0

    def violations_report(self) -> dict:
        failures = []
        for r in self.results:
            if not r.passed:
                failures.append({
                    "mutation": r.name,
                    "issues": r.issues,
                    "fix_hint": _fix_hint(r.name),
                })
        return {
            "resilience_score": self.resilience_score,
            "passed": self.passed,
            "mutations_passed": f"{self.mutations_passed}/{self.mutations_run}",
            "failures": failures,
        }


def _fix_hint(mutation_name: str) -> str:
    hints = {
        "inflate_text_3x": "Add text-overflow: ellipsis, overflow: hidden, or flex-wrap: wrap to text containers.",
        "extreme_word": "Add word-break: break-word or overflow-wrap: break-word to text elements.",
        "multiply_children_15x": "Use flex-wrap: wrap on containers. Add overflow-y: auto for bounded lists.",
        "empty_all_text": "Set min-height or min-width on containers to prevent collapse with empty content.",
        "rtl_arabic": "Test with dir='rtl'. Use logical properties (margin-inline-start instead of margin-left).",
        "extreme_input_values": "Set max-width on inputs. Use text-overflow: ellipsis.",
        "single_char_content": "Set min-width on elements to prevent collapse with minimal content.",
    }
    return hints.get(mutation_name, "Review CSS defensive patterns.")


def run_chaos_gate_sync(html_path: str, viewport_width: int = 1440) -> ChaosResult:
    """Run all chaos mutations via Playwright with innerHTML save/restore.

    PERF FIX: Single page load, save innerHTML, mutate, check, restore.
    Eliminates page.goto per mutation (~5s → ~1s total).
    """
    from playwright.sync_api import sync_playwright
    import os

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": viewport_width, "height": 900})
        page.goto(f"file://{os.path.abspath(html_path)}")
        page.wait_for_timeout(400)

        # Save pristine DOM for fast restore (no network I/O)
        clean_dom = page.evaluate("document.body.innerHTML")

        for name, script in CHAOS_MUTATIONS.items():
            try:
                # Inject mutation
                page.evaluate(script)
                page.wait_for_timeout(150)

                # Check breakage
                check = page.evaluate(BREAKAGE_CHECK_JS)

                passed = (
                    not check["hasHScroll"]
                    and check["overflowCount"] == 0
                    and check["overlapCount"] == 0
                )

                results.append(MutationResult(
                    name=name,
                    has_horizontal_scroll=check["hasHScroll"],
                    overflow_elements=check["overflowCount"],
                    overlap_count=check["overlapCount"],
                    passed=passed,
                ))
            except Exception as e:
                results.append(MutationResult(
                    name=name,
                    has_horizontal_scroll=True,
                    overflow_elements=-1,
                    overlap_count=-1,
                    passed=False,
                ))

            # Restore pristine DOM (fast: no page.goto, no network)
            try:
                page.evaluate("document.body.innerHTML = arguments[0]", clean_dom)
                page.wait_for_timeout(100)
            except Exception:
                # If restore fails, reload (fallback)
                page.goto(f"file://{os.path.abspath(html_path)}")
                page.wait_for_timeout(300)
                clean_dom = page.evaluate("document.body.innerHTML")

        page.close()
        browser.close()

    passed_count = sum(1 for r in results if r.passed)
    total = len(results)
    resilience = passed_count / max(total, 1)

    return ChaosResult(
        mutations_run=total,
        mutations_passed=passed_count,
        mutations_failed=total - passed_count,
        resilience_score=round(resilience, 3),
        passed=passed_count == total,
        results=results,
        score_10=round(resilience * 10.0, 1),
    )
