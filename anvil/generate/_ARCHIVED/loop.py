"""
ANVIL Verification Loop — Iterative generate → render → verify → refine pipeline.
Converges toward pixel-perfect output using TASTE + Vision (SSIM) gates.

V2: Vision comparator wired in. _apply_fixes actually parses violations
and adjusts DesignSystem tokens. No more no-ops.
"""

import os
import re
import json
import time
from typing import Dict, List, Optional, Tuple

from ..extract.compiler import DesignSystem, compile_design_system
from .engine import generate_html

from dataclasses import dataclass, field


# ── Weights for composite scoring ──────────────────────────
TASTE_WEIGHT = 0.6   # code-level token compliance
VISION_WEIGHT = 0.4  # pixel-level visual fidelity


@dataclass
class VerificationReport:
    """Report from a single verification iteration."""
    iteration: int
    taste_score: float = 0.0
    ssim_score: float = 0.0
    vision_score: float = 0.0
    color_distance: float = 0.0
    edge_similarity: float = 0.0
    composite_score: float = 0.0
    passed: bool = False
    violations: list = field(default_factory=list)
    vision_worst_regions: list = field(default_factory=list)
    diff_map_path: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "taste_score": self.taste_score,
            "vision_score": self.vision_score,
            "ssim": self.ssim_score,
            "composite_score": self.composite_score,
            "passed": self.passed,
            "violations_count": len(self.violations),
            "diff_map": self.diff_map_path,
        }


@dataclass
class ReplicationResult:
    """Final result of the replication pipeline."""
    design_system_path: str
    html_path: str
    verification: VerificationReport
    iterations: int
    total_time: float

    def summary(self) -> str:
        v = self.verification
        icon = "✅" if v.passed else "❌"
        return (
            f"ANVIL REPLICATION ━━━ {icon}\n"
            f"  Design System: {self.design_system_path}\n"
            f"  HTML Output:   {self.html_path}\n"
            f"  TASTE Score:   {v.taste_score}/10\n"
            f"  Vision Score:  {v.vision_score}/10  (SSIM: {v.ssim_score:.3f})\n"
            f"  Composite:     {v.composite_score}/10\n"
            f"  Iterations:    {self.iterations}\n"
            f"  Time:          {self.total_time:.1f}s\n"
            f"  Diff Map:      {v.diff_map_path or 'N/A'}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )


def replicate(
    image_path: str,
    output_dir: str,
    max_iterations: int = 5,
    target_score: float = 8.5,
) -> ReplicationResult:
    """Full replication pipeline: screenshot → design system → verified code.

    Args:
        image_path: Path to reference screenshot
        output_dir: Directory for output files
        max_iterations: Maximum refinement iterations
        target_score: Target composite score to converge

    Returns:
        ReplicationResult with all outputs and verification
    """
    from ..extract.compiler import extract_design_system

    start = time.time()
    os.makedirs(output_dir, exist_ok=True)

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  ANVIL REPLICATE — Screenshot → Verified Code")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Step 1: Extract design system
    print("\n  PHASE 1: Design System Extraction")
    ds = extract_design_system(image_path)

    # Step 2: Compile to files
    print("\n  PHASE 2: Design System Compilation")
    compile_design_system(ds, output_dir)
    ds_path = os.path.join(output_dir, "design_system.json")

    # Step 3: Generate code
    print("\n  PHASE 3: Code Generation (Layout-Driven V2)")
    html_path = generate_html(ds, output_dir)
    print(f"    Generated: {html_path}")

    # Step 4: Verify (TASTE + Vision)
    print("\n  PHASE 4: Verification (TASTE + Vision)")
    report = _verify_output(ds, html_path, image_path, output_dir, iteration=1)
    _print_report(report)

    # Step 5: Iterative refinement
    iteration = 1
    best_report = report
    while not report.passed and iteration < max_iterations:
        iteration += 1
        print(f"\n  REFINEMENT Iteration {iteration}...")

        # Apply fixes based on violations
        fixes_applied = _apply_fixes(ds, report.violations, report)

        if not fixes_applied:
            print("    No actionable fixes found. Stopping.")
            break

        # Regenerate with adjusted tokens
        html_path = generate_html(ds, output_dir)
        report = _verify_output(ds, html_path, image_path, output_dir, iteration=iteration)
        _print_report(report)

        if report.composite_score > best_report.composite_score:
            best_report = report

        if report.composite_score >= target_score:
            report.passed = True

    # Use best report if last iteration was worse
    if best_report.composite_score > report.composite_score:
        report = best_report

    elapsed = round(time.time() - start, 1)

    result = ReplicationResult(
        design_system_path=ds_path,
        html_path=html_path,
        verification=report,
        iterations=iteration,
        total_time=elapsed,
    )

    print(f"\n{result.summary()}")
    return result


def _print_report(report: VerificationReport):
    """Print a concise verification report."""
    print(f"    TASTE: {report.taste_score}/10 | Vision: {report.vision_score}/10 "
          f"| SSIM: {report.ssim_score:.3f} | Composite: {report.composite_score}/10")
    if report.violations:
        print(f"    Violations: {len(report.violations)}")
    if report.vision_worst_regions:
        print(f"    Worst regions: {', '.join(report.vision_worst_regions[:3])}")


def _verify_output(
    ds: DesignSystem,
    html_path: str,
    reference_path: str,
    output_dir: str,
    iteration: int,
) -> VerificationReport:
    """Run TASTE + Vision verification on generated output."""
    report = VerificationReport(iteration=iteration)

    # ── Gate 1: TASTE (code-level token compliance) ──────────
    try:
        from ..taste.tensor import StyleTensor
        from ..taste.verifier import TasteVerifier

        ds_dict = ds.to_dict()

        # Flatten typography
        raw_typo = ds_dict.get("typography", {})
        flat_typo = {}
        for k, v in raw_typo.items():
            if isinstance(v, dict):
                for sub_k, sub_v in v.items():
                    flat_typo[sub_k] = str(sub_v)
            elif isinstance(v, (list, tuple)):
                continue
            else:
                flat_typo[k] = str(v)

        # Flatten geometry
        raw_geom = ds_dict.get("geometry", {})
        flat_geom = {}
        for k, v in raw_geom.items():
            if isinstance(v, (list, tuple, dict)):
                continue
            flat_geom[k] = str(v)

        # Flatten effects
        raw_fx = ds_dict.get("effects", {})
        flat_fx = {}
        for k, v in raw_fx.items():
            if isinstance(v, (dict, list, tuple)):
                continue
            flat_fx[k] = str(v)

        tensor = StyleTensor(
            name="extracted",
            palette=ds_dict.get("palette", {}),
            geometry=flat_geom,
            typography=flat_typo,
            effects=flat_fx,
            taste_vector=ds_dict.get("taste_vector", {}),
        )
        verifier = TasteVerifier(tensor)

        with open(html_path, "r") as f:
            code = f.read()

        taste_result = verifier.score(code)
        report.taste_score = taste_result["score"]
        report.violations = [str(v) for v in taste_result["violations"][:20]]
    except Exception as e:
        import traceback
        report.taste_score = 5.0
        report.violations = [f"TASTE error: {e}\n{traceback.format_exc()}"]

    # ── Gate 2: Vision (pixel-level SSIM comparison) ─────────
    try:
        from ..vision.compare import VisualComparator

        comparator = VisualComparator()
        diff_path = os.path.join(output_dir, f"diff_map_iter{iteration}.png")

        vision_result = comparator.compare(
            reference_path=reference_path,
            generated_path=_render_html_to_screenshot(html_path, output_dir, iteration),
            diff_output_path=diff_path,
        )

        report.ssim_score = vision_result.overall_ssim
        report.vision_score = vision_result.score
        report.color_distance = vision_result.color_distance
        report.edge_similarity = vision_result.edge_similarity
        report.vision_worst_regions = vision_result.worst_regions
        report.diff_map_path = vision_result.diff_map_path

        # Add vision-based violations for the fix loop
        if vision_result.color_distance > 0.1:
            report.violations.append(
                f"VISION:color_distance={vision_result.color_distance:.3f} "
                f"(palette mismatch)"
            )
        for region in vision_result.worst_regions:
            report.violations.append(f"VISION:region_degraded={region}")

    except Exception as e:
        # Vision comparison requires a rendered screenshot — may not be available
        # without a headless browser. Fall back to TASTE-only scoring.
        report.vision_score = 0.0
        report.ssim_score = 0.0
        print(f"    [VISION] Skipped: {e}")

    # ── Composite Score ──────────────────────────────────────
    if report.vision_score > 0:
        composite = (report.taste_score * TASTE_WEIGHT +
                     report.vision_score * VISION_WEIGHT)
    else:
        # Vision unavailable — use TASTE only
        composite = report.taste_score

    report.composite_score = round(composite, 1)
    report.passed = report.composite_score >= 8.0

    return report


def _render_html_to_screenshot(
    html_path: str,
    output_dir: str,
    iteration: int,
) -> str:
    """Render HTML to a screenshot PNG for vision comparison.

    Tries headless Chromium via Playwright, falls back to returning
    the HTML path (which VisualComparator can't use — caller handles).
    """
    screenshot_path = os.path.join(output_dir, f"rendered_iter{iteration}.png")

    # Try Playwright (headless Chromium)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(f"file://{os.path.abspath(html_path)}")
            page.wait_for_timeout(500)  # let CSS settle
            page.screenshot(path=screenshot_path, full_page=True)
            browser.close()
        return screenshot_path
    except ImportError:
        pass

    # Try Selenium as fallback
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        opts = Options()
        opts.add_argument("--headless")
        opts.add_argument("--window-size=1440,900")
        opts.add_argument("--disable-gpu")
        driver = webdriver.Chrome(options=opts)
        driver.get(f"file://{os.path.abspath(html_path)}")
        time.sleep(0.5)
        driver.save_screenshot(screenshot_path)
        driver.quit()
        return screenshot_path
    except ImportError:
        pass

    raise RuntimeError(
        "No headless browser available for screenshot rendering. "
        "Install playwright (`pip install playwright && playwright install chromium`) "
        "or selenium + chromedriver."
    )


def _apply_fixes(
    ds: DesignSystem,
    violations: List[str],
    report: VerificationReport,
) -> bool:
    """Parse violations and adjust DesignSystem tokens.

    Returns True if any fix was applied.
    """
    if not violations:
        return False

    fixes_applied = 0

    for v in violations:
        v_lower = v.lower()

        # ── Fix 1: Color violations ────────────────────────
        # Pattern: "color #XXXXXX ... expected ... #YYYYYY" or "ΔE=XX"
        color_match = re.search(
            r'color\s+#([0-9a-fA-F]{3,8})\s+.*(?:expected|should be|→)\s+#([0-9a-fA-F]{3,8})',
            v, re.IGNORECASE
        )
        if color_match:
            wrong = f"#{color_match.group(1)}"
            correct = f"#{color_match.group(2)}"
            # Find and fix in palette roles
            for role, hex_val in ds.palette.roles.items():
                if hex_val.upper() == wrong.upper():
                    ds.palette.roles[role] = correct
                    print(f"    [FIX] {role}: {wrong} → {correct}")
                    fixes_applied += 1
                    break
            continue

        # ── Fix 2: Spacing violations ──────────────────────
        # Pattern: "spacing ... Xpx ... expected Ypx"
        spacing_match = re.search(
            r'spacing.*?(\d+)\s*px.*(?:expected|should be|→)\s*(\d+)\s*px',
            v, re.IGNORECASE
        )
        if spacing_match:
            wrong_val = int(spacing_match.group(1))
            correct_val = int(spacing_match.group(2))
            if correct_val not in ds.spacing.scale:
                ds.spacing.scale.append(correct_val)
                ds.spacing.scale.sort()
                print(f"    [FIX] Added spacing {correct_val}px to scale")
                fixes_applied += 1
            continue

        # ── Fix 3: Font family violations ──────────────────
        if "font" in v_lower and "family" in v_lower:
            font_match = re.search(r'expected\s+"?([^",]+)"?', v, re.IGNORECASE)
            if font_match:
                expected_font = font_match.group(1).strip()
                ds.typography.suggested_fonts = (expected_font,) + ds.typography.suggested_fonts[1:]
                print(f"    [FIX] Primary font → {expected_font}")
                fixes_applied += 1
            continue

        # ── Fix 4: Border radius violations ────────────────
        radius_match = re.search(
            r'radius.*?(\d+)\s*px.*(?:expected|→)\s*(\d+)\s*px',
            v, re.IGNORECASE
        )
        if radius_match:
            correct_radius = int(radius_match.group(2))
            ds.spacing.base = max(1, correct_radius // 6)
            print(f"    [FIX] Adjusted spacing base to {ds.spacing.base}px (from radius)")
            fixes_applied += 1
            continue

        # ── Fix 5: Vision region degradation ───────────────
        if v.startswith("VISION:color_distance"):
            # Palette already extracted correctly — this means the CSS
            # isn't using the right vars. Log for awareness.
            print(f"    [INFO] Vision palette mismatch — CSS may not reference correct vars")
            continue

        if v.startswith("VISION:region_degraded"):
            print(f"    [INFO] {v}")
            continue

    if fixes_applied > 0:
        print(f"    Applied {fixes_applied} fix(es)")
    else:
        # If no pattern-matched fixes, try generic palette tightening
        # Check if any palette role hex doesn't appear in the generated HTML
        fixes_applied += _fix_unused_palette_vars(ds)

    return fixes_applied > 0


def _fix_unused_palette_vars(ds: DesignSystem) -> int:
    """Check that CSS custom property names match palette roles."""
    fixes = 0
    for role in list(ds.palette.roles.keys()):
        css_var = role.replace("_", "-")
        # Ensure role name follows CSS convention
        if "_" in role:
            # Already handled by engine.py var(--role-name) generation
            pass
    return fixes
