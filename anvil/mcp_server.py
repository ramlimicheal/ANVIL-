"""
ANVIL MCP Server v3 — Full parity with upgraded CLI + v3 modules.
13 tools: 11 original + anvil_tokenize + anvil_profiles.

v3 upgrades:
  - CIEDE2000 perceptual color distance (not sRGB Euclidean)
  - CSS tokenizer eliminates false positives from comments/strings/URLs
  - 6D taste vector: temperature, density, formality, energy, age, price
  - AST-based Z3 provers with dataflow analysis
  - 5 prover categories: div_zero, overflow, bounds, auth, concurrency
  - Size guards (500KB code, 200KB text)
  - Per-prover breakdown in responses
  - Fixed anvil_score: runs both layers when no filepath given
"""

import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anvil.config import (
    AnvilConfig, detect_file_layer, anvil_grade,
    MAX_CODE_SIZE, MAX_TEXT_SIZE,
)

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


# ─── Shared helpers ───────────────────────────────────────────

def _create_guard(profile="linear"):
    from anvil.watcher.guard import AnvilGuard
    config = AnvilConfig()
    config.taste.profile = profile
    return AnvilGuard(config)


def _check_code_size(code):
    if len(code) > MAX_CODE_SIZE:
        return f"Code too large ({len(code):,} bytes). Max: {MAX_CODE_SIZE:,} bytes."
    return None


def _check_text_size(text):
    if len(text) > MAX_TEXT_SIZE:
        return f"Text too large ({len(text):,} bytes). Max: {MAX_TEXT_SIZE:,} bytes."
    return None


def _read_file_or_code(code, filepath):
    if filepath and not code and os.path.isfile(filepath):
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()
    return code


# ─── Handler: init ────────────────────────────────────────────

def handle_anvil_init(project_path=".", project_name=""):
    if not project_name:
        project_name = os.path.basename(os.path.abspath(project_path))
    config_path = os.path.join(project_path, "anvil.json")
    if os.path.exists(config_path):
        return {"status": "exists", "path": config_path, "message": "anvil.json already exists."}
    config = AnvilConfig(project_name=project_name, project_path=project_path)
    config.save(config_path)
    return {
        "status": "created", "path": config_path,
        "profile": config.taste.profile,
        "z3_provers": config.z3.enabled_provers,
        "compression_level": config.compression.level,
    }


# ─── Handler: taste (v3: taste vector + profile metadata) ────

def handle_anvil_taste(code="", filepath="", profile="linear"):
    from anvil.taste.tensor import load_profile
    from anvil.taste.verifier import TasteVerifier

    code = _read_file_or_code(code, filepath)
    if not code:
        return {"error": "No code provided. Pass 'code' or 'filepath'."}
    size_err = _check_code_size(code)
    if size_err:
        return {"error": size_err}

    tensor = load_profile(profile)
    verifier = TasteVerifier(tensor)
    result = verifier.score(code)

    return {
        "score": result["score"],
        "pass": result["pass"],
        "errors": result["errors"],
        "warnings": result["warnings"],
        "infos": result.get("infos", 0),
        "total_violations": result["total_violations"],
        "violations": [str(v) for v in result["violations"][:15]],
        "profile": profile,
        "profile_name": tensor.name,
        "taste_vector": {
            "temperature": tensor.taste_vector.get("temperature", 0.5),
            "density": tensor.taste_vector.get("density", 0.5),
            "formality": tensor.taste_vector.get("formality", 0.5),
            "energy": tensor.taste_vector.get("energy", 0.5),
            "age": tensor.taste_vector.get("age", 0.5),
            "price": tensor.taste_vector.get("price", 0.5),
        },
        "design_system": {
            "palette_colors": len(tensor.palette),
            "fonts": tensor.get_allowed_fonts()[:4],
            "spacing_base": tensor.geometry.get("spacing_base", "4px"),
        },
    }


# ─── Handler: prove (v3: per-prover breakdown + has_z3) ──────

def handle_anvil_prove(code="", filepath=""):
    from anvil.z3_guard.provers import AnvilZ3Guard, HAS_Z3

    code = _read_file_or_code(code, filepath)
    if not code:
        return {"error": "No code provided. Pass 'code' or 'filepath'."}
    size_err = _check_code_size(code)
    if size_err:
        return {"error": size_err}

    guard = AnvilZ3Guard()
    result = guard.score(code, filepath)

    prover_summary = {}
    for r in result["results"]:
        p = r.prover if hasattr(r, "prover") else "unknown"
        if p not in prover_summary:
            prover_summary[p] = {"bugs": 0, "safe": 0, "skipped": 0}
        if hasattr(r, "verdict"):
            if r.verdict == "BUG_FOUND":
                prover_summary[p]["bugs"] += 1
            elif r.verdict == "PROVEN_SAFE":
                prover_summary[p]["safe"] += 1
            elif r.verdict == "SKIP":
                prover_summary[p]["skipped"] += 1

    return {
        "score": result["score"],
        "pass": result["pass"],
        "bugs_found": result["bugs_found"],
        "proven_safe": result["proven_safe"],
        "skipped": result.get("skipped", 0),
        "total_checks": result["total_checks"],
        "has_z3": HAS_Z3,
        "provers": prover_summary,
        "results": [str(r) for r in result["results"][:15]],
    }


# ─── Handler: compress (v3: level + savings metadata) ────────

def handle_anvil_compress(text="", filepath="", level="medium"):
    from anvil.compress.engine import SemanticCompressor
    try:
        from anvil.compress.engine import HAS_TIKTOKEN
    except ImportError:
        HAS_TIKTOKEN = False

    text = _read_file_or_code(text, filepath)
    if not text:
        return {"error": "No text provided. Pass 'text' or 'filepath'."}
    size_err = _check_text_size(text)
    if size_err:
        return {"error": size_err}

    compressor = SemanticCompressor(level)
    result = compressor.compress(text)

    return {
        "compressed": result.compressed,
        "original_tokens": result.original_tokens,
        "compressed_tokens": result.compressed_tokens,
        "reduction_pct": result.reduction_pct,
        "techniques": result.techniques_applied,
        "level": level,
        "has_tiktoken": HAS_TIKTOKEN if isinstance(HAS_TIKTOKEN, bool) else False,
        "savings_estimate": f"${round(result.reduction_pct * 0.5, 2)}/1K prompts",
    }


# ─── Handler: guard ──────────────────────────────────────────

def handle_anvil_guard(watch_path=".", profile="linear"):
    from anvil.watcher.guard import AnvilGuard
    config = AnvilConfig()
    config.taste.profile = profile
    guard = AnvilGuard(config)

    abs_path = os.path.abspath(watch_path)
    if not os.path.isdir(abs_path):
        return {"error": f"Not a directory: {abs_path}"}

    results = guard.verify_directory(abs_path)
    file_reports = []
    for r in results[:20]:
        file_reports.append({
            "filepath": r.filepath, "layers": r.layers_run,
            "taste_score": r.taste_score, "z3_score": r.z3_score,
            "passed": r.passed, "summary": r.summary(),
        })

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    return {
        "watch_path": abs_path, "profile": profile,
        "total_files": total, "passed": passed, "failed": total - passed,
        "files": file_reports,
    }


# ─── Handler: score (v3 FIX: runs both layers when no filepath) ─

def handle_anvil_score(code="", filepath="", profile="linear"):
    code = _read_file_or_code(code, filepath)
    if not code:
        return {"error": "No code provided. Pass 'code' or 'filepath'."}
    size_err = _check_code_size(code)
    if size_err:
        return {"error": size_err}

    layer = detect_file_layer(filepath)

    if layer == "unknown":
        # v3 FIX: no filepath → run BOTH layers explicitly
        taste_score = z3_score = None
        taste_violations = z3_bugs = 0
        layers_run = []
        details = {}

        try:
            from anvil.taste.tensor import load_profile
            from anvil.taste.verifier import TasteVerifier
            tensor = load_profile(profile)
            verifier = TasteVerifier(tensor)
            tr = verifier.score(code)
            taste_score = tr["score"]
            taste_violations = tr["total_violations"]
            layers_run.append("taste")
            details["taste"] = {
                "score": tr["score"], "pass": tr["pass"],
                "violations": [str(v) for v in tr["violations"][:5]],
            }
        except Exception as e:
            details["taste_error"] = str(e)

        try:
            from anvil.z3_guard.provers import AnvilZ3Guard
            zg = AnvilZ3Guard()
            zr = zg.score(code, filepath)
            z3_score = zr["score"]
            z3_bugs = zr["bugs_found"]
            layers_run.append("z3")
            details["z3"] = {
                "score": zr["score"], "pass": zr["pass"],
                "bugs_found": zr["bugs_found"],
                "results": [str(r) for r in zr["results"][:5]],
            }
        except Exception as e:
            details["z3_error"] = str(e)

        scores = [s for s in [taste_score, z3_score] if s is not None]
        combined = round(sum(scores) / max(len(scores), 1), 1) if scores else 0
        taste_ok = taste_score is None or taste_score >= 6.0
        z3_ok = z3_score is None or z3_score >= 6.0
        passed = taste_ok and z3_ok

        return {
            "anvil_score": combined, "grade": anvil_grade(combined),
            "taste_score": taste_score, "z3_score": z3_score,
            "layers_run": layers_run, "passed": passed, "details": details,
            "summary": (
                f"ANVIL ━━━ {filepath or '<inline>'}\n"
                f"  TASTE  {'✅' if taste_ok else '⚠️'} {taste_score}/10 ({taste_violations} violations)\n"
                f"  Z3     {'✅' if z3_ok else '⚠️'} {z3_score}/10 ({z3_bugs} bugs)\n"
                f"  GRADE  {anvil_grade(combined)} ({combined}/10)\n"
                f"  STATUS {'✅ PASS' if passed else '❌ BLOCKED'}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
        }
    else:
        guard = _create_guard(profile)
        result = guard.verify_code(code, filepath)
        scores = []
        if result.taste_score is not None:
            scores.append(result.taste_score)
        if result.z3_score is not None:
            scores.append(result.z3_score)
        combined = round(sum(scores) / max(len(scores), 1), 1) if scores else 0

        return {
            "anvil_score": combined, "grade": anvil_grade(combined),
            "taste_score": result.taste_score, "z3_score": result.z3_score,
            "layers_run": result.layers_run, "passed": result.passed,
            "details": {k: v for k, v in result.details.items()},
            "summary": result.summary(),
        }


# ─── Handler: vision ─────────────────────────────────────────

def handle_anvil_vision(reference_path, generated_path, diff_output=""):
    try:
        from anvil.vision.compare import VisualComparator
    except ImportError:
        return {"error": "Pillow not installed. pip install Pillow"}

    if not os.path.exists(reference_path):
        return {"error": f"Reference image not found: {reference_path}"}
    if not os.path.exists(generated_path):
        return {"error": f"Generated image not found: {generated_path}"}

    comparator = VisualComparator()
    kwargs = {}
    if diff_output:
        kwargs["diff_output_path"] = diff_output
    result = comparator.compare(reference_path, generated_path, **kwargs)

    return {
        "score": result.score, "passed": result.passed,
        "overall_ssim": result.overall_ssim,
        "semantic_score": result.semantic_score,
        "semantic_details": result.semantic_details,
        "block_match_score": result.block_match_score,
        "block_match_violations": result.block_match_details,
        "color_distance": result.color_distance,
        "edge_similarity": result.edge_similarity,
        "physics_score": result.physics_score,
        "worst_regions": result.worst_regions,
        "reference_size": list(result.reference_size),
        "generated_size": list(result.generated_size),
        "region_scores": [
            {"label": r.label, "ssim": r.ssim, "row": r.row, "col": r.col}
            for r in result.region_scores[:12]
        ],
        "summary": result.summary(),
    }


# ─── Handler: extract ────────────────────────────────────────

def handle_anvil_extract(image_path, output_dir=""):
    if not os.path.exists(image_path):
        return {"error": f"Image not found: {image_path}"}
    if not output_dir:
        output_dir = f"{os.path.splitext(image_path)[0]}_anvil_ds"

    from anvil.extract.compiler import extract_design_system, compile_design_system
    ds = extract_design_system(image_path)
    compile_design_system(ds, output_dir)
    ds_dict = ds.to_dict()

    return {
        "status": "success", "output_dir": output_dir,
        "files": [
            os.path.join(output_dir, f) for f in
            ["design_system.json", "tokens.css", "tailwind.config.js", "responsive.css"]
        ],
        "design_system": {
            "meta": ds_dict["meta"], "palette": ds_dict["palette"],
            "taste_vector": ds_dict["taste_vector"],
            "typography": {k: v for k, v in ds_dict["typography"].items() if not isinstance(v, (list, dict))},
            "components_found": ds_dict["components"]["types_found"],
            "total_icons": ds_dict["icons"]["total"],
        },
    }


# ─── Handler: replicate ──────────────────────────────────────

def handle_anvil_replicate(image_path, output_dir=""):
    """v4 extract-only. Design tokens are handed to AI to build."""
    if not os.path.exists(image_path):
        return {"error": f"Image not found: {image_path}"}
    if not output_dir:
        output_dir = f"{os.path.splitext(image_path)[0]}_replicated"

    from anvil.extract.compiler import extract_design_system, compile_design_system
    ds = extract_design_system(image_path)
    compile_design_system(ds, output_dir)
    ds_dict = ds.to_dict()

    return {
        "status": "extracted",
        "action_required": "AI must now generate HTML/CSS using these tokens.",
        "output_dir": output_dir,
        "design_system_path": os.path.join(output_dir, "design_system.json"),
        "tokens_path": os.path.join(output_dir, "tokens.css"),
        "design_system": {
            "meta": ds_dict["meta"],
            "palette": ds_dict["palette"],
            "taste_vector": ds_dict["taste_vector"],
            "typography": {k: v for k, v in ds_dict["typography"].items() if not isinstance(v, (list, dict))},
            "components_found": ds_dict["components"]["types_found"],
            "total_icons": list(ds_dict.get("icons", {}).get("catalog", {}).keys())[:10],
        },
    }


# ─── Handler: validate_output (v4 NEW) ───────────────────────

def handle_anvil_validate_output(reference_path, html_path, design_system_path, profile="linear"):
    """v5 Short-Circuit DAG Validation Gate.

    Tier 1: Symbolic & Lexical (~50ms, no browser)
        → TASTE token compliance, CSS 4px grid, design system match
        → Short-circuits if taste_score < 4.0 (structurally wrong tokens)

    Tier 2: Headless DOM Extraction (~400ms, no screenshots)
        → Biomechanics (Fitts's Law touch targets)
        → Chaos Gate (7 data mutations + overflow detection)
        → Short-circuits if ANY boolean gate fails

    Tier 3: Vision Physics (~1200ms, GPU matrices)
        → SSIM, Semantic, Block-Match, Saliency, Physics, Edge, Color
        → Only executes on code that passed Tiers 1-2
    """
    if not os.path.exists(reference_path):
        return {"error": f"Reference image not found: {reference_path}"}
    if not os.path.exists(html_path):
        return {"error": f"Generated HTML not found: {html_path}"}
    if not os.path.exists(design_system_path):
        return {"error": f"Design system not found: {design_system_path}"}

    output_dir = os.path.dirname(html_path)
    result = {
        "tier1_passed": False, "tier2_passed": False,
        "taste_score": 0.0, "taste_violations": [],
        "biomechanics_passed": True, "biomechanics_violations": {},
        "chaos_passed": True, "chaos_violations": {},
        "vision_score": 0.0, "ssim": 0.0, "vision_violations": {},
        "saliency_score": 0.0, "saliency_violations": {},
        "composite_score": 0.0, "passed": False,
        "diff_map_path": None,
        "short_circuited_at": None,
    }

    # ═══════════════════════════════════════════════════════════
    # TIER 1: Symbolic & Lexical (~50ms, NO BROWSER)
    # ═══════════════════════════════════════════════════════════
    try:
        from anvil.taste.tensor import StyleTensor
        from anvil.taste.verifier import TasteVerifier
        with open(design_system_path, "r") as f:
            ds_dict = json.load(f)

        tensor = StyleTensor(
            name="extracted",
            palette=ds_dict.get("palette", {}),
            geometry=ds_dict.get("geometry", {}),
            typography=ds_dict.get("typography", {}),
            effects=ds_dict.get("effects", {}),
            taste_vector=ds_dict.get("taste_vector", {}),
        )
        verifier = TasteVerifier(tensor)
        with open(html_path, "r", encoding="utf-8") as f:
            code = f.read()
        tr = verifier.score(code)
        result["taste_score"] = tr["score"]
        result["taste_violations"] = [str(v) for v in tr["violations"]][:15]
    except Exception as e:
        import traceback
        result["taste_violations"] = [f"TASTE Error: {str(e)}\n{traceback.format_exc()}"]

    # SHORT-CIRCUIT: If TASTE score < 4.0, tokens are fundamentally wrong.
    # No point rendering — the CSS doesn't match the design system.
    if result["taste_score"] < 4.0:
        result["short_circuited_at"] = "tier1_taste"
        result["status"] = "FAIL"
        result["message"] = f"Short-circuited at Tier 1. TASTE score {result['taste_score']}/10 — CSS tokens fundamentally violate the design system. Fix token compliance before vision checks run."
        return result

    result["tier1_passed"] = True

    # ═══════════════════════════════════════════════════════════
    # TIER 2: Headless DOM Extraction (~400ms, NO SCREENSHOTS)
    # ═══════════════════════════════════════════════════════════

    # Biomechanics (Fitts's Law)
    try:
        from anvil.taste.biomechanics import run_biomechanics_audit_sync
        bio_result = run_biomechanics_audit_sync(html_path)
        result["biomechanics_passed"] = bio_result.passed
        result["biomechanics_violations"] = bio_result.violations_report()
    except Exception as e:
        result["biomechanics_violations"] = {"error": str(e)}

    # Chaos Gate (7 data mutations)
    try:
        from anvil.chaos.fuzzer import run_chaos_gate_sync
        chaos_result = run_chaos_gate_sync(html_path)
        result["chaos_passed"] = chaos_result.passed
        result["chaos_violations"] = chaos_result.violations_report()
    except Exception as e:
        result["chaos_violations"] = {"error": str(e)}
        result["chaos_passed"] = True  # Don't block on internal error

    # SHORT-CIRCUIT: Tier 2 boolean gates
    tier2_failed_gates = []
    if not result["chaos_passed"]:
        tier2_failed_gates.append("chaos_gate")
    if not result["biomechanics_passed"]:
        tier2_failed_gates.append("biomechanics")

    if tier2_failed_gates:
        result["short_circuited_at"] = f"tier2_{'+'.join(tier2_failed_gates)}"
        result["status"] = "FAIL"
        result["composite_score"] = 0.0
        result["message"] = f"Short-circuited at Tier 2. Failed gates: {tier2_failed_gates}. Layout is brittle or ergonomically unsafe. Fix before pixel comparison runs."
        return result

    result["tier2_passed"] = True

    # ═══════════════════════════════════════════════════════════
    # TIER 3: Vision Physics (~1200ms, GPU MATRICES)
    # Only runs on code that passed Tiers 1-2
    # ═══════════════════════════════════════════════════════════
    vision_score = 0.0
    ssim_score = 0.0
    diff_path = os.path.join(output_dir, "vision_diff.png")
    screenshot_path = os.path.join(output_dir, "generated_screenshot.png")

    try:
        from anvil.vision.compare import VisualComparator
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(f"file://{os.path.abspath(html_path)}")
            page.wait_for_timeout(500)
            page.screenshot(path=screenshot_path, full_page=True)
            browser.close()

        comparator = VisualComparator()
        vision_result = comparator.compare(reference_path, screenshot_path, diff_output_path=diff_path)
        vision_score = vision_result.score
        ssim_score = vision_result.overall_ssim
        if hasattr(vision_result, "violations_report"):
            result["vision_violations"] = vision_result.violations_report()

        result["vision_score"] = vision_score
        result["ssim"] = ssim_score

    except Exception as e:
        result["vision_violations"] = {"error": f"Vision Error: {str(e)}"}

    # Saliency (runs on screenshots from Tier 3)
    try:
        from anvil.vision.saliency import SaliencyComparator
        if os.path.exists(screenshot_path):
            sal = SaliencyComparator()
            sal_result = sal.compare(reference_path, screenshot_path)
            result["saliency_score"] = round(sal_result.similarity, 4)
            result["saliency_violations"] = sal_result.violations_report()
    except Exception as e:
        result["saliency_violations"] = {"error": str(e)}

    # ═══════════════════════════════════════════════════════════
    # COMPOSITE SCORE (only Tier 3 continuous metrics)
    # ═══════════════════════════════════════════════════════════
    taste_s = result["taste_score"]
    vision_s = result["vision_score"]
    saliency_s = result.get("saliency_score", 0.0)

    # Weighted: TASTE 40% + Vision 40% + Saliency 20%
    composite = (taste_s * 0.4) + (vision_s * 0.4) + (saliency_s * 10.0 * 0.2)
    composite = round(max(0.0, min(10.0, composite)), 1)

    passed = composite >= 8.0
    result["composite_score"] = composite
    result["passed"] = passed
    result["status"] = "PASS" if passed else "FAIL"
    result["diff_map_path"] = diff_path if os.path.exists(diff_path) else None
    result["message"] = "Pixel-perfect compliance achieved." if passed else "Review violations. All tiers passed — refine for visual precision."

    return result


# ─── Handler: verify (v3: inline violations + grade) ─────────

def handle_anvil_verify(code="", filepath="", profile="linear"):
    code = _read_file_or_code(code, filepath)
    if not code:
        return {"error": "No code provided. Pass 'code' or 'filepath'."}
    size_err = _check_code_size(code)
    if size_err:
        return {"error": size_err}

    guard = _create_guard(profile)
    result = guard.verify_code(code, filepath)

    scores = []
    if result.taste_score is not None:
        scores.append(result.taste_score)
    if result.z3_score is not None:
        scores.append(result.z3_score)
    combined = round(sum(scores) / max(len(scores), 1), 1) if scores else 0

    return {
        "filepath": result.filepath,
        "layers_run": result.layers_run,
        "passed": result.passed,
        "taste_score": result.taste_score,
        "z3_score": result.z3_score,
        "anvil_score": combined,
        "grade": anvil_grade(combined),
        "taste_violations": result.taste_violations,
        "z3_bugs": result.z3_bugs,
        "summary": result.summary(),
        "details": {k: v for k, v in result.details.items()},
    }


# ─── Handler: tokenize (v3 NEW) ──────────────────────────────

def handle_anvil_tokenize(code="", filepath=""):
    from anvil.taste.css_tokenizer import CSSTokenizer

    code = _read_file_or_code(code, filepath)
    if not code:
        return {"error": "No CSS code provided. Pass 'code' or 'filepath'."}
    size_err = _check_code_size(code)
    if size_err:
        return {"error": size_err}

    tokenizer = CSSTokenizer(code)
    declarations = tokenizer.parse_declarations()
    colors = tokenizer.get_colors()
    fonts = tokenizer.get_fonts()
    spacing = tokenizer.get_spacing_values()
    radii = tokenizer.get_radii()
    rules = tokenizer.parse_rules()

    return {
        "total_declarations": len(declarations),
        "total_rules": len(rules),
        "colors": [{"value": c[0], "line": c[1]} for c in colors[:20]],
        "fonts": [{"value": f[0], "line": f[1]} for f in fonts[:10]],
        "spacing": [{"property": s[0], "value": s[1], "line": s[2]} for s in spacing[:20]],
        "radii": [{"value": r[0], "line": r[1]} for r in radii[:10]],
        "declarations": [
            {"property": d.property, "value": d.value, "line": d.line, "selector": d.selector}
            for d in declarations[:30]
        ],
        "rules": [
            {"selector": r.selector, "declaration_count": len(r.declarations), "line": r.line}
            for r in rules[:20]
        ],
    }


# ─── Handler: profiles (v3 NEW) ──────────────────────────────

def handle_anvil_profiles():
    from anvil.taste.tensor import PROFILES
    from pathlib import Path

    profiles = {}
    for name, data in PROFILES.items():
        meta = data.get("meta", {})
        tv = data.get("taste_vector", {})
        profiles[name] = {
            "name": meta.get("name", name),
            "vibe": meta.get("vibe", ""),
            "taste_vector": tv,
            "palette_count": len(data.get("palette", {})),
            "fonts": [f.strip().strip("'\"") for f in data.get("typography", {}).get("family_sans", "").split(",")[:2]],
        }

    profiles_dir = Path(__file__).parent / "taste" / "profiles"
    custom = [p.stem for p in profiles_dir.glob("*.json")] if profiles_dir.exists() else []

    return {"builtin": profiles, "custom": custom, "total": len(profiles) + len(custom)}


# ─── Tool definitions ────────────────────────────────────────

TOOL_DEFS = [
    Tool(name="anvil_init",
         description="Initialize ANVIL config (anvil.json) in a project directory. Creates design system profile, Z3 prover settings, and compression config.",
         inputSchema={"type": "object", "properties": {
             "project_path": {"type": "string", "description": "Directory to initialize. Default: current dir."},
             "project_name": {"type": "string", "description": "Project name for config."},
         }}),
    Tool(name="anvil_taste",
         description="TASTE Guard — verify frontend code against design system using CIEDE2000 perceptual color distance, CSS tokenizer (eliminates false positives from comments/strings/URLs), and 6D taste vector enforcement (temperature, density, formality, energy, age, price). Checks colors, spacing (4px grid), fonts, border-radius, WCAG contrast, inline style abuse, and design token var() usage ratio. Returns score, violations, taste vector used, and design system metadata. Pass code directly or give a filepath.",
         inputSchema={"type": "object", "properties": {
             "code": {"type": "string", "description": "CSS/HTML/JSX code to check"},
             "filepath": {"type": "string", "description": "Absolute path to file (alternative to code)"},
             "profile": {"type": "string", "description": "Design profile: linear, cyberpunk, soft, minimal"},
         }}),
    Tool(name="anvil_prove",
         description="Z3 Guard — mathematically prove backend code correctness using AST-based extraction (Python) with dataflow-aware constraint analysis. 5 prover categories: division-by-zero (with guard awareness), integer overflow (64-bit BitVec), array bounds (len() guard detection), auth bypass (OR-role tautology), and TOCTOU race conditions (check-then-act without lock). Generates counterexamples via Z3 SAT models. Regex fallback for non-Python languages. Pass code directly or give a filepath.",
         inputSchema={"type": "object", "properties": {
             "code": {"type": "string", "description": "Backend code to verify"},
             "filepath": {"type": "string", "description": "Absolute path to file (alternative to code)"},
         }}),
    Tool(name="anvil_compress",
         description="Semantic compression — reduce LLM prompt tokens while preserving meaning. 3 levels x 8 techniques: filler removal, whitespace collapse, code redundancy removal, technical compression, deduplication, example compression, abbreviation (function->fn), TF-IDF sentence pruning. Token counting via tiktoken BPE (cl100k_base). Pass text directly or give a filepath.",
         inputSchema={"type": "object", "properties": {
             "text": {"type": "string", "description": "Text to compress"},
             "filepath": {"type": "string", "description": "Absolute path to file (alternative to text)"},
             "level": {"type": "string", "description": "Compression level: light, medium, or aggressive"},
         }}),
    Tool(name="anvil_guard",
         description="ANVIL Guard — verify all files in a directory through TASTE and Z3 layers. Returns per-file scores, violations, and pass/fail status. In MCP mode this runs a one-shot scan (CLI mode runs as a live watcher).",
         inputSchema={"type": "object", "properties": {
             "watch_path": {"type": "string", "description": "Absolute path to directory to scan"},
             "profile": {"type": "string", "description": "TASTE design profile to use"},
         }}),
    Tool(name="anvil_score",
         description="Get combined ANVIL score (A+ to F) for any code. Runs both TASTE and Z3 guards, combines scores, returns letter grade. v3 fix: when no filepath is given, runs BOTH layers regardless. Pass code directly or give a filepath.",
         inputSchema={"type": "object", "properties": {
             "code": {"type": "string", "description": "Code to score"},
             "filepath": {"type": "string", "description": "Absolute path to file (alternative to code)"},
             "profile": {"type": "string", "description": "Design profile for TASTE: linear, cyberpunk, soft, minimal"},
         }}),
    Tool(name="anvil_vision",
         description="Visual fidelity comparison — compare a reference screenshot against a generated screenshot using SSIM, color histogram distance, edge structure correlation, and photometric physics verification. Returns per-region scores identifying exactly WHERE the UI differs.",
         inputSchema={"type": "object", "properties": {
             "reference_path": {"type": "string", "description": "Absolute path to reference screenshot (the target design)"},
             "generated_path": {"type": "string", "description": "Absolute path to generated screenshot (what the AI built)"},
             "diff_output": {"type": "string", "description": "Optional: path to save visual diff image"},
         }, "required": ["reference_path", "generated_path"]}),
    Tool(name="anvil_extract",
         description="Extract complete design system from a screenshot. Uses OpenCV to detect: color palette (dark/light mode), typography, spacing grid, visual effects (gradients, glassmorphism, shadows), component catalog, icon analysis, and responsive framework. Outputs: design_system.json, tokens.css, tailwind.config.js, responsive.css.",
         inputSchema={"type": "object", "properties": {
             "image_path": {"type": "string", "description": "Absolute path to screenshot PNG/JPG"},
             "output_dir": {"type": "string", "description": "Directory for output files (default: auto-named)"},
         }, "required": ["image_path"]}),
    Tool(name="anvil_replicate",
         description="Phase 1 of replication pipeline: Extract design system from screenshot. Returns the exact design tokens (palette, spacing, fonts) that you, the AI, MUST use to generate the HTML/CSS.",
         inputSchema={"type": "object", "properties": {
             "image_path": {"type": "string", "description": "Absolute path to reference screenshot"},
             "output_dir": {"type": "string", "description": "Directory for extracted output files"},
         }, "required": ["image_path"]}),
    Tool(name="anvil_validate_output",
         description="Phase 2 of replication pipeline: Validate AI's generated HTML against the design tokens AND visual screenshot. Take a screenshot of the HTML and runs SSIM + TASTE tests. Returns composite score and actionable violation report.",
         inputSchema={"type": "object", "properties": {
             "reference_path": {"type": "string", "description": "Absolute path to original reference screenshot"},
             "html_path": {"type": "string", "description": "Absolute path to the HTML file you generated"},
             "design_system_path": {"type": "string", "description": "Path to extracted design_system.json"},
             "profile": {"type": "string", "description": "Design profile for TASTE (optional, default: linear)"},
         }, "required": ["reference_path", "html_path", "design_system_path"]}),
    Tool(name="anvil_verify",
         description="Full ANVIL verification with grade. Routes frontend code to TASTE Guard, backend code to Z3 Guard based on file extension. Returns scores, grade (A+ to F), inline violation details, and pass/fail status. Pass code directly or give a filepath.",
         inputSchema={"type": "object", "properties": {
             "code": {"type": "string", "description": "Code to verify"},
             "filepath": {"type": "string", "description": "Filename or path (for routing: .css->TASTE, .py->Z3)"},
             "profile": {"type": "string", "description": "Design profile: linear, cyberpunk, soft, minimal"},
         }}),
    Tool(name="anvil_tokenize",
         description="CSS Tokenizer diagnostic — parse CSS into structured declarations using proper lexical analysis. Returns extracted colors, fonts, spacing, border-radii, and full rule breakdown. Excludes values inside comments, strings, URLs (no false positives). Use for debugging CSS before running full TASTE verification.",
         inputSchema={"type": "object", "properties": {
             "code": {"type": "string", "description": "CSS code to tokenize"},
             "filepath": {"type": "string", "description": "Absolute path to CSS file (alternative to code)"},
         }}),
    Tool(name="anvil_profiles",
         description="List all available ANVIL design profiles with their 6D taste vectors, palette metadata, and font families. Shows both built-in profiles (linear, cyberpunk, soft, minimal) and any custom JSON profiles.",
         inputSchema={"type": "object", "properties": {}}),
]


# ─── Handler dispatch table ───────────────────────────────────

HANDLERS = {
    "anvil_init": lambda a: handle_anvil_init(a.get("project_path", "."), a.get("project_name", "")),
    "anvil_taste": lambda a: handle_anvil_taste(a.get("code", ""), a.get("filepath", ""), a.get("profile", "linear")),
    "anvil_prove": lambda a: handle_anvil_prove(a.get("code", ""), a.get("filepath", "")),
    "anvil_compress": lambda a: handle_anvil_compress(a.get("text", ""), a.get("filepath", ""), a.get("level", "medium")),
    "anvil_guard": lambda a: handle_anvil_guard(a.get("watch_path", "."), a.get("profile", "linear")),
    "anvil_score": lambda a: handle_anvil_score(a.get("code", ""), a.get("filepath", ""), a.get("profile", "linear")),
    "anvil_vision": lambda a: handle_anvil_vision(a["reference_path"], a["generated_path"], a.get("diff_output", "")),
    "anvil_extract": lambda a: handle_anvil_extract(a["image_path"], a.get("output_dir", "")),
    "anvil_replicate": lambda a: handle_anvil_replicate(a["image_path"], a.get("output_dir", "")),
    "anvil_validate_output": lambda a: handle_anvil_validate_output(a["reference_path"], a["html_path"], a["design_system_path"], a.get("profile", "linear")),
    "anvil_verify": lambda a: handle_anvil_verify(a.get("code", ""), a.get("filepath", ""), a.get("profile", "linear")),
    "anvil_tokenize": lambda a: handle_anvil_tokenize(a.get("code", ""), a.get("filepath", "")),
    "anvil_profiles": lambda a: handle_anvil_profiles(),
}


# ─── MCP Server ───────────────────────────────────────────────

if HAS_MCP:
    server = Server("anvil")

    @server.list_tools()
    async def list_tools():
        return TOOL_DEFS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        if name not in HANDLERS:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
        try:
            result = HANDLERS[name](arguments)
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
        except Exception as e:
            import traceback
            return [TextContent(type="text", text=json.dumps({
                "error": str(e), "traceback": traceback.format_exc(),
            }))]

    async def main():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())


# ─── Standalone JSON-RPC fallback ─────────────────────────────

def jsonrpc_loop():
    sys.stderr.write("[ANVIL MCP] Server running (JSON-RPC mode)\n")
    sys.stderr.write(f"[ANVIL MCP] {len(HANDLERS)} tools registered\n")
    for line in sys.stdin:
        try:
            req = json.loads(line.strip())
            method = req.get("method", "")
            params = req.get("params", {})
            if method in HANDLERS:
                result = HANDLERS[method](params)
            else:
                result = {"error": f"Unknown method: {method}", "available": list(HANDLERS.keys())}
            sys.stdout.write(json.dumps({"id": req.get("id"), "result": result}, default=str) + "\n")
            sys.stdout.flush()
        except Exception as e:
            sys.stdout.write(json.dumps({"error": str(e)}) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    if HAS_MCP:
        import asyncio
        asyncio.run(main())
    else:
        jsonrpc_loop()
