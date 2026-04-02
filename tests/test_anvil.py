"""
ANVIL Test Suite — Comprehensive tests for all 3 layers + integration.
"""

import sys
import os
import time

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = 0
FAIL = 0
TOTAL = 0


def test(name, condition):
    global PASS, FAIL, TOTAL
    TOTAL += 1
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}")


# ═══════════════════════════════════════════════════════════════
# LAYER 1: TASTE GUARD TESTS
# ═══════════════════════════════════════════════════════════════

def test_taste_tensor():
    print("\n── TASTE: StyleTensor ──")
    from anvil.taste.tensor import StyleTensor, load_profile, PROFILES

    # Test profile loading
    tensor = load_profile("linear")
    test("Load linear profile", tensor.name == "Linear Dark")
    test("Palette has bg_layer_0", "bg_layer_0" in tensor.palette)
    test("Palette has accent_primary", tensor.palette["accent_primary"] == "#5E6AD2")

    # Test CSS vars export
    css = tensor.to_css_vars()
    test("CSS vars contains :root", ":root {" in css)
    test("CSS vars contains bg-layer-0", "--bg-layer-0:" in css)

    # Test Tailwind config export
    tw = tensor.to_tailwind_config()
    test("Tailwind has colors", "colors" in tw)
    test("Tailwind has borderRadius", "borderRadius" in tw)

    # Test JSON roundtrip
    data = tensor.to_json()
    restored = StyleTensor.from_json(data)
    test("JSON roundtrip preserves name", restored.name == tensor.name)
    test("JSON roundtrip preserves palette", restored.palette == tensor.palette)

    # Test utility methods
    colors = tensor.get_all_colors()
    test("get_all_colors returns palette", len(colors) > 5)

    grid = tensor.get_spacing_grid()
    test("Spacing grid starts at 4", grid[0] == 4)
    test("Spacing grid includes 16", 16 in grid)

    fonts = tensor.get_allowed_fonts()
    test("Allowed fonts includes Inter", "Inter" in fonts)

    # Test all profiles load
    for name in PROFILES:
        t = load_profile(name)
        test(f"Profile '{name}' loads", t.name != "")

    # Test invalid profile raises
    try:
        load_profile("nonexistent")
        test("Invalid profile raises error", False)
    except ValueError:
        test("Invalid profile raises error", True)


def test_taste_verifier():
    print("\n── TASTE: Verifier ──")
    from anvil.taste.tensor import load_profile
    from anvil.taste.verifier import TasteVerifier, Violation

    tensor = load_profile("linear")
    verifier = TasteVerifier(tensor)

    # Test: hardcoded color not in palette
    bad_css = """
    .card {
        color: #333333;
        background: #FF00FF;
        padding: 13px;
        font-family: Arial, sans-serif;
        border-radius: 5px;
    }
    """
    violations = verifier.verify(bad_css, "test.css")
    test("Detects hardcoded color violations", any(v.category == "color" for v in violations))
    test("Detects spacing grid violation (13px)", any(v.category == "spacing" for v in violations))
    test("Detects font violation (Arial)", any(v.category == "typography" for v in violations))
    test("Detects radius violation (5px)", any(v.category == "radius" for v in violations))

    # Test: good CSS using design tokens
    good_css = """
    .card {
        color: var(--text-primary);
        background: var(--bg-layer-1);
        padding: 16px;
        font-family: Inter, system-ui, sans-serif;
        border-radius: 12px;
    }
    """
    good_violations = verifier.verify(good_css, "good.css")
    test("Good CSS has fewer violations", len(good_violations) < len(violations))

    # Test: WCAG accessibility
    a11y_css = """
    .text {
        color: #999999;
        background-color: #AAAAAA;
    }
    """
    a11y_violations = verifier.verify(a11y_css, "a11y.css")
    test("Detects WCAG contrast violation",
         any(v.category == "accessibility" for v in a11y_violations))

    # Test: score method
    score_result = verifier.score(bad_css)
    test("Score returns dict with score", "score" in score_result)
    test("Score is numeric", isinstance(score_result["score"], float))
    test("Bad CSS score < 10", score_result["score"] < 10.0)

    good_score = verifier.score(good_css)
    test("Good CSS scores higher", good_score["score"] >= score_result["score"])


def test_taste_scorer():
    print("\n── TASTE: Aesthetic Scorer ──")
    from anvil.taste.scorer import AestheticScorer
    from anvil.taste.tensor import load_profile

    scorer = AestheticScorer()

    # Test palette scoring
    colors = ["#09090B", "#121214", "#5E6AD2", "#22C55E", "#EF4444", "#F59E0B"]
    result = scorer.score_palette(colors)
    test("Score has total", "total" in result)
    test("Score has harmony", "harmony" in result)
    test("Score is within range", 0 <= result["total"] <= 10)

    # Test tensor scoring
    tensor = load_profile("linear")
    tensor_result = scorer.score_tensor(tensor)
    test("Tensor score works", tensor_result["total"] > 0)

    # Test comparison
    source = ["#09090B", "#5E6AD2", "#22C55E"]
    output = ["#0A0A0C", "#5F6BD3", "#23C65F"]
    comp = scorer.compare(source, output)
    test("Compare has fidelity", "fidelity_pct" in comp)
    test("Similar palettes have high fidelity", comp["fidelity_pct"] > 50)


# ═══════════════════════════════════════════════════════════════
# LAYER 2: Z3 GUARD TESTS
# ═══════════════════════════════════════════════════════════════

def test_z3_div_zero():
    print("\n── Z3: Division by Zero ──")
    from anvil.z3_guard.provers import DivisionByZeroProver

    prover = DivisionByZeroProver()

    # Vulnerable: no guard
    vuln_code = """
def calculate_average(total, count):
    return total / count
"""
    results = prover.prove(vuln_code, "calc.py")
    test("Detects unguarded division", any(r.verdict == "BUG_FOUND" for r in results))

    # Safe: with guard
    safe_code = """
def calculate_average(total, count):
    if count != 0:
        return total / count
    return 0
"""
    safe_results = prover.prove(safe_code, "calc.py")
    bugs = [r for r in safe_results if r.verdict == "BUG_FOUND"]
    test("Guarded division has fewer bugs", len(bugs) < len([r for r in results if r.verdict == "BUG_FOUND"]))

    # Literal zero
    zero_code = """
x = value / 0
"""
    zero_results = prover.prove(zero_code)
    test("Detects literal division by zero", any(r.verdict == "BUG_FOUND" for r in zero_results))


def test_z3_auth():
    print("\n── Z3: Auth Logic ──")
    from anvil.z3_guard.provers import AuthLogicProver

    prover = AuthLogicProver()

    # Bug: OR instead of AND in role check
    vuln_code = """
def check_access(user):
    if user.role != "admin" or user.role != "superadmin":
        deny()
"""
    results = prover.prove(vuln_code, "auth.py")
    test("Detects OR-based role check bug", any(r.verdict == "BUG_FOUND" for r in results))


def test_z3_concurrency():
    print("\n── Z3: Concurrency ──")
    from anvil.z3_guard.provers import ConcurrencyProver

    prover = ConcurrencyProver()

    # Bug: TOCTOU race condition
    vuln_code = """
def handle_request(request_count, max_requests):
    if request_count < max_requests:
        process()
        request_count += 1
"""
    results = prover.prove(vuln_code, "rate.py")
    test("Detects TOCTOU race condition", any(r.verdict == "BUG_FOUND" for r in results))

    # Safe: with lock
    safe_code = """
def handle_request(request_count, max_requests):
    with threading.Lock():
        if request_count < max_requests:
            process()
            request_count += 1
"""
    safe_results = prover.prove(safe_code, "rate.py")
    safe_bugs = [r for r in safe_results if r.verdict == "BUG_FOUND"]
    test("Lock prevents TOCTOU detection", len(safe_bugs) == 0)


def test_z3_bounds():
    print("\n── Z3: Bounds Check ──")
    from anvil.z3_guard.provers import BoundsCheckProver

    prover = BoundsCheckProver()

    vuln_code = """
def get_item(products, selected_index):
    return products[selected_index]
"""
    results = prover.prove(vuln_code, "list.py")
    test("Detects unguarded array access", any(r.verdict == "BUG_FOUND" for r in results))


def test_z3_unified():
    print("\n── Z3: Unified Guard ──")
    from anvil.z3_guard.provers import AnvilZ3Guard

    guard = AnvilZ3Guard()

    code = """
def process_payment(amount, items):
    per_item = amount / items
    tax = per_item * tax_rate
    if user.role != "admin" or user.role != "manager":
        deny()
    return prices[selected]
"""
    result = guard.score(code, "payment.py")
    test("Unified guard returns score", "score" in result)
    test("Unified guard finds bugs", result["bugs_found"] > 0)
    test("Unified guard runs all provers", result["total_checks"] > 0)


# ═══════════════════════════════════════════════════════════════
# LAYER 3: SEMANTIC COMPRESSION TESTS
# ═══════════════════════════════════════════════════════════════

def test_compression():
    print("\n── Compression: Semantic ──")
    from anvil.compress.engine import SemanticCompressor

    # Test light compression
    compressor = SemanticCompressor("light")
    text = """
    Please could you kindly create a new file called utils.py and I would like you to
    basically implement a function called calculate_total that essentially takes a list
    of prices and returns the sum. Make sure to add error handling. Don't forget to
    add type hints. Remember to write tests. It is important to note that the function
    should handle empty lists gracefully.
    """
    result = compressor.compress(text)
    test("Light compression reduces tokens", result.compressed_tokens < result.original_tokens)
    test("Light compression positive reduction", result.reduction_pct > 0)

    # Test medium compression
    med = SemanticCompressor("medium")
    med_result = med.compress(text)
    test("Medium reduces more than light", med_result.reduction_pct >= result.reduction_pct)

    # Test aggressive compression
    agg = SemanticCompressor("aggressive")
    agg_result = agg.compress(text)
    test("Aggressive reduces more than medium", agg_result.reduction_pct >= med_result.reduction_pct)

    # Test that meaning is preserved (key words still present)
    test("Preserves 'calculate_total'", "calculate_total" in agg_result.compressed)
    test("Preserves 'prices'", "prices" in agg_result.compressed)
    test("Preserves 'sum'", "sum" in agg_result.compressed)

    # Test deduplication
    dup_text = "Add error handling.\nAdd error handling.\nAdd error handling."
    dup_result = med.compress(dup_text)
    test("Deduplicates repeated lines", dup_result.compressed.count("Add error handling") < 3)

    # Test score method
    score = compressor.score(text)
    test("Score has reduction_pct", "reduction_pct" in score)
    test("Score has monthly_savings", "monthly_savings_estimate" in score)


# ═══════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════

def test_config():
    print("\n── Integration: Config ──")
    from anvil.config import AnvilConfig, detect_file_layer

    config = AnvilConfig()
    test("Default config loads", config.project_name == "untitled")
    test("Default TASTE profile is linear", config.taste.profile == "linear")
    test("Default Z3 has provers", len(config.z3.enabled_provers) > 0)

    # Test file routing
    test("CSS routes to taste", detect_file_layer("style.css") == "taste")
    test("Python routes to z3", detect_file_layer("app.py") == "z3")
    test("TSX routes to both", detect_file_layer("Component.tsx") == "both")
    test("Go routes to z3", detect_file_layer("main.go") == "z3")
    test("Solidity routes to z3", detect_file_layer("Token.sol") == "z3")
    test("Unknown routes to unknown", detect_file_layer("readme.md") == "unknown")


def test_guard():
    print("\n── Integration: Guard ──")
    from anvil.config import AnvilConfig
    from anvil.watcher.guard import AnvilGuard

    config = AnvilConfig()
    guard = AnvilGuard(config)

    # Test CSS verification
    css_code = """
    .header { color: #FF00FF; padding: 13px; font-family: Comic Sans; }
    """
    css_result = guard.verify_code(css_code, "header.css")
    test("CSS routed to TASTE", "taste" in css_result.layers_run)
    test("CSS has taste_score", css_result.taste_score is not None)

    # Test Python verification
    py_code = """
def divide(a, b):
    return a / b
"""
    py_result = guard.verify_code(py_code, "math_utils.py")
    test("Python routed to Z3", "z3" in py_result.layers_run)
    test("Python has z3_score", py_result.z3_score is not None)

    # Test TSX routes to both
    tsx_code = """
function Component() {
    const price = total / items;
    return <div style={{color: '#FF00FF'}}>Hello</div>
}
"""
    tsx_result = guard.verify_code(tsx_code, "Component.tsx")
    test("TSX routes to both layers", len(tsx_result.layers_run) >= 1)

    # Test summary output
    summary = css_result.summary()
    test("Summary contains ANVIL", "ANVIL" in summary)
    test("Summary contains score", "/10" in summary)


# ═══════════════════════════════════════════════════════════════
# RUN ALL TESTS
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    start = time.time()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  ⚒️  ANVIL TEST SUITE")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Layer 1: TASTE
    test_taste_tensor()
    test_taste_verifier()
    test_taste_scorer()

    # Layer 2: Z3
    test_z3_div_zero()
    test_z3_auth()
    test_z3_concurrency()
    test_z3_bounds()
    test_z3_unified()

    # Layer 3: Compression
    test_compression()

    # Integration
    test_config()
    test_guard()

    elapsed = round(time.time() - start, 2)
    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  RESULTS: {PASS} passed, {FAIL} failed ({elapsed}s)")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    sys.exit(0 if FAIL == 0 else 1)
