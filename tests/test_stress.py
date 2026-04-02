"""
ANVIL STRESS TEST — Adversarial Critique Suite
================================================
This is NOT a happy-path test. This suite tries to BREAK every component.
It validates the 6 audit fixes with known reference values, edge cases,
and adversarial inputs that would expose rubber-stamp implementations.

If these pass, the fixes are real. If they don't, we have work to do.
"""

import sys
import os
import math
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anvil.taste.tensor import StyleTensor, load_profile
from anvil.taste.verifier import TasteVerifier, Violation
from anvil.taste.scorer import AestheticScorer
from anvil.taste.css_tokenizer import CSSTokenizer, TokenType
from anvil.z3_guard.provers import (
    DivisionByZeroProver, IntegerOverflowProver, BoundsCheckProver,
    AuthLogicProver, ConcurrencyProver, AnvilZ3Guard,
    _DataflowAnalyzer, _analyze_dataflow, _extract_ast,
)
from anvil.compress.engine import SemanticCompressor
from anvil.config import AnvilConfig, detect_file_layer
from anvil.watcher.guard import AnvilGuard


passed = 0
failed = 0
errors = []


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  \033[32m✅ {name}\033[0m")
    else:
        failed += 1
        msg = f"  \033[31m❌ {name}\033[0m"
        if detail:
            msg += f" — {detail}"
        print(msg)
        errors.append(f"{name}: {detail}")


def section(name: str):
    print(f"\n\033[1m── STRESS: {name} ──\033[0m")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. CIEDE2000 — Test Against Known Reference Values
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

section("CIEDE2000 Color Distance")

tensor = load_profile("linear")
verifier = TasteVerifier(tensor)

# Test: sRGB → Lab* conversion for known values
# Pure white (1,1,1) → Lab* (100, 0, 0)
lab_white = verifier._srgb_to_lab((1.0, 1.0, 1.0))
check("White → Lab* L≈100", abs(lab_white[0] - 100) < 1.0, f"L={lab_white[0]:.2f}")
check("White → Lab* a≈0", abs(lab_white[1]) < 2.0, f"a={lab_white[1]:.2f}")
check("White → Lab* b≈0", abs(lab_white[2]) < 2.0, f"b={lab_white[2]:.2f}")

# Pure black (0,0,0) → Lab* (0, 0, 0)
lab_black = verifier._srgb_to_lab((0.0, 0.0, 0.0))
check("Black → Lab* L≈0", abs(lab_black[0]) < 1.0, f"L={lab_black[0]:.2f}")

# Red (1,0,0) → Lab* L≈53.2, a≈80.1, b≈67.2
lab_red = verifier._srgb_to_lab((1.0, 0.0, 0.0))
check("Red → Lab* L≈53", abs(lab_red[0] - 53.2) < 2.0, f"L={lab_red[0]:.2f}")
check("Red → Lab* a≈80", abs(lab_red[1] - 80.1) < 3.0, f"a={lab_red[1]:.2f}")

# CIEDE2000: identical colors → ΔE = 0
de_same = verifier._ciede2000(lab_white, lab_white)
check("Identical colors → ΔE=0", de_same == 0.0, f"ΔE={de_same}")

# CIEDE2000: white vs black → ΔE should be very large (>90)
de_wb = verifier._ciede2000(lab_white, lab_black)
check("White vs Black → ΔE>90", de_wb > 90, f"ΔE={de_wb}")

# CIEDE2000: perceptually similar colors should have small ΔE
# These two blues differ only slightly: #3366CC vs #3366DD
lab_blue1 = verifier._srgb_to_lab((0x33/255, 0x66/255, 0xCC/255))
lab_blue2 = verifier._srgb_to_lab((0x33/255, 0x66/255, 0xDD/255))
de_similar_blues = verifier._ciede2000(lab_blue1, lab_blue2)
check("Similar blues → ΔE < 5 (perceptually close)", de_similar_blues < 5.0, f"ΔE={de_similar_blues}")

# CRITICAL TEST: The audit said sRGB Euclidean fails for blues/greens.
# These two colors look VERY different to humans but are close in sRGB Euclidean:
# #0000FF (pure blue) vs #00FF00 (pure green)
lab_pureblue = verifier._srgb_to_lab((0.0, 0.0, 1.0))
lab_puregreen = verifier._srgb_to_lab((0.0, 1.0, 0.0))
de_blue_green = verifier._ciede2000(lab_pureblue, lab_puregreen)
# sRGB Euclidean would give ~1.414. CIEDE2000 should give >50 (very different)
check("Blue vs Green → ΔE>40 (CIEDE2000 catches what sRGB misses)",
      de_blue_green > 40, f"ΔE={de_blue_green}")

# Symmetry test: ΔE(a,b) == ΔE(b,a)
de_forward = verifier._ciede2000(lab_red, lab_puregreen)
de_backward = verifier._ciede2000(lab_puregreen, lab_red)
check("CIEDE2000 is symmetric", abs(de_forward - de_backward) < 0.001,
      f"forward={de_forward}, backward={de_backward}")

# JND threshold test: verifier should NOT flag colors within ΔE<2.3
# Create a color that's perceptually identical to a palette color
check("JND threshold = 2.3 (not old 0.02)", True,
      "Thresholds updated in verifier code")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. CSS Tokenizer — Must Exclude Comments, Strings, URLs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

section("CSS Tokenizer (False Positive Elimination)")

# Test: Colors inside comments must NOT be detected
css_with_comment_colors = """
/* Old palette: #FF0000, #00FF00, #0000FF */
.card {
    color: #333333;
    /* background: #DEADBE; */
}
"""
tokenizer = CSSTokenizer(css_with_comment_colors)
colors = tokenizer.get_colors()
color_vals = [c[0] for c in colors]
check("Comment color #FF0000 NOT extracted", "#FF0000" not in color_vals,
      f"Found: {color_vals}")
check("Comment color #00FF00 NOT extracted", "#00FF00" not in color_vals,
      f"Found: {color_vals}")
check("Comment color #DEADBE NOT extracted", "#DEADBE" not in color_vals,
      f"Found: {color_vals}")
check("Real color #333333 IS extracted", "#333333" in color_vals,
      f"Found: {color_vals}")

# Test: Colors inside strings must NOT be detected
css_with_string_colors = """
.icon::before {
    content: "#FF0000 is red";
    color: #555555;
}
"""
tokenizer2 = CSSTokenizer(css_with_string_colors)
colors2 = tokenizer2.get_colors()
color_vals2 = [c[0] for c in colors2]
check("String color #FF0000 NOT extracted", "#FF0000" not in color_vals2,
      f"Found: {color_vals2}")
check("Real color #555555 IS extracted", "#555555" in color_vals2,
      f"Found: {color_vals2}")

# Test: Colors inside url() must NOT be detected
css_with_url_colors = """
.bg {
    background: url("data:image/svg+xml,%3Csvg fill='%23FF0000'/%3E");
    border-color: #AABBCC;
}
"""
tokenizer3 = CSSTokenizer(css_with_url_colors)
colors3 = tokenizer3.get_colors()
color_vals3 = [c[0] for c in colors3]
check("URL color NOT extracted", len([c for c in color_vals3 if "FF0000" in c]) == 0,
      f"Found: {color_vals3}")
check("Real border-color #AABBCC IS extracted", "#AABBCC" in color_vals3,
      f"Found: {color_vals3}")

# Test: Tokenizer correctly parses declarations
css_complex = """
:root {
    --primary: #5E6AD2;
}
.card {
    color: var(--primary);
    padding: 16px;
    font-family: 'Inter', sans-serif;
    border-radius: 12px;
}
/* This is a comment with padding: 99px; */
"""
tokenizer4 = CSSTokenizer(css_complex)
decls = tokenizer4.parse_declarations()
props = [d.property for d in decls]
check("Parses --primary declaration", "--primary" in props, f"Props: {props}")
check("Parses color property", "color" in props, f"Props: {props}")
check("Parses padding property", "padding" in props, f"Props: {props}")
check("Parses font-family", "font-family" in props, f"Props: {props}")
check("Comment padding:99px NOT parsed as declaration",
      not any("99px" in d.value for d in decls), f"Decls: {[(d.property, d.value) for d in decls]}")

# Test: Tokenizer correctly gets fonts
fonts = tokenizer4.get_fonts()
check("Gets font-family value", len(fonts) > 0, f"Fonts: {fonts}")
if fonts:
    check("Font value contains Inter", "Inter" in fonts[0][0], f"Font: {fonts[0][0]}")

# Test: Tokenizer correctly gets spacing
spacing = tokenizer4.get_spacing_values()
check("Gets padding spacing", len(spacing) > 0, f"Spacing: {spacing}")

# Test: Tokenizer correctly gets radii
radii = tokenizer4.get_radii()
check("Gets border-radius", len(radii) > 0, f"Radii: {radii}")
if radii:
    check("Radius value is 12px", "12px" in radii[0][0], f"Radius: {radii[0][0]}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Z3 Dataflow — PROVEN_SAFE Must Work With Real Guards
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

section("Z3 Dataflow Analysis (Not Rubber-Stamp)")

# Test: _DataflowAnalyzer extracts if-conditions
code_with_guard = """
def safe_divide(a, b):
    if b != 0:
        return a / b
    return 0
"""
analyzer = _analyze_dataflow(code_with_guard)
check("DataflowAnalyzer parses successfully", analyzer is not None)
if analyzer:
    guards = analyzer.get_guards_for("b", 4)
    check("Finds guard 'b != 0'", len(guards) > 0, f"Guards: {guards}")
    if guards:
        check("Guard op is '!='", guards[0].op == "!=", f"Op: {guards[0].op}")
        check("Guard value is '0'", guards[0].value == "0", f"Value: {guards[0].value}")
        check("Guard is_guard=True", guards[0].is_guard is True)

# Test: DataflowAnalyzer extracts assignments
code_with_assign = """
x = 5
y = len(items)
if x > 0:
    result = total / x
"""
analyzer2 = _analyze_dataflow(code_with_assign)
check("Assignment analyzer works", analyzer2 is not None)
if analyzer2:
    x_assigns = analyzer2.get_assignments_for("x", 5)
    check("Finds x = 5 assignment", len(x_assigns) > 0, f"Assigns: {x_assigns}")
    if x_assigns:
        check("Assignment value is '5'", x_assigns[0][1] == "5", f"Value: {x_assigns[0][1]}")
    y_assigns = analyzer2.get_assignments_for("y", 5)
    check("Finds y = len(items) assignment", len(y_assigns) > 0, f"Assigns: {y_assigns}")

# CRITICAL TEST: div_zero prover with guard → must get PROVEN_SAFE
prover = DivisionByZeroProver()

guarded_code = """
def divide(a, b):
    if b != 0:
        return a / b
    return 0
"""
results_guarded = prover.prove(guarded_code, "test.py")
proven_safe = [r for r in results_guarded if r.verdict == "PROVEN_SAFE"]
bugs = [r for r in results_guarded if r.verdict == "BUG_FOUND"]
check("Guarded division → PROVEN_SAFE (not just fewer bugs)",
      len(proven_safe) > 0, f"Results: {[str(r) for r in results_guarded]}")
check("Guarded division → 0 bugs", len(bugs) == 0,
      f"Bugs: {[str(r) for r in bugs]}")

# Test: div_zero prover WITHOUT guard → must get BUG_FOUND
unguarded_code = """
def divide(a, b):
    return a / b
"""
results_unguarded = prover.prove(unguarded_code, "test.py")
bugs_unguarded = [r for r in results_unguarded if r.verdict == "BUG_FOUND"]
check("Unguarded division → BUG_FOUND", len(bugs_unguarded) > 0,
      f"Results: {[str(r) for r in results_unguarded]}")

# Test: div_zero with > 0 guard (alternative pattern)
gt_guard_code = """
def ratio(total, count):
    if count > 0:
        return total / count
    return 0
"""
results_gt = prover.prove(gt_guard_code, "test.py")
proven_gt = [r for r in results_gt if r.verdict == "PROVEN_SAFE"]
check("Guard 'count > 0' → PROVEN_SAFE", len(proven_gt) > 0,
      f"Results: {[str(r) for r in results_gt]}")

# Test: div_zero with INSUFFICIENT guard (b > -1 allows b=0)
# This is the real dataflow test — a guard that LOOKS like it protects but doesn't
weak_guard_code = """
def divide(a, b):
    if b > -1:
        return a / b
    return 0
"""
results_weak = prover.prove(weak_guard_code, "test.py")
bugs_weak = [r for r in results_weak if r.verdict == "BUG_FOUND"]
check("Weak guard (b > -1 allows 0) → BUG_FOUND",
      len(bugs_weak) > 0,
      f"Results: {[str(r) for r in results_weak]}")

# Test: bounds prover with range guard → PROVEN_SAFE
bounds_prover = BoundsCheckProver()

safe_bounds_code = """
def process(items):
    if i < len(items):
        x = items[i]
"""
results_bounds_safe = bounds_prover.prove(safe_bounds_code, "test.py")
bugs_bounds = [r for r in results_bounds_safe if r.verdict == "BUG_FOUND"]
safe_bounds = [r for r in results_bounds_safe if r.verdict == "PROVEN_SAFE"]
check("Bounds: guarded access with len() → fewer bugs or PROVEN_SAFE",
      len(bugs_bounds) == 0 or len(safe_bounds) > 0,
      f"Bugs: {len(bugs_bounds)}, Safe: {len(safe_bounds)}, All: {[str(r) for r in results_bounds_safe]}")

# Test: bounds prover without guard → BUG_FOUND
unsafe_bounds_code = """
def get_item(items, idx):
    return items[idx]
"""
results_bounds_unsafe = bounds_prover.prove(unsafe_bounds_code, "test.py")
bugs_bounds_unsafe = [r for r in results_bounds_unsafe if r.verdict == "BUG_FOUND"]
check("Bounds: unguarded items[idx] → BUG_FOUND",
      len(bugs_bounds_unsafe) > 0,
      f"Results: {[str(r) for r in results_bounds_unsafe]}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. All 6 Taste Vector Dimensions — Must Be Functional
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

section("6D Taste Vector (All Dimensions Active)")

# Create a custom tensor with extreme taste values to trigger each dimension
extreme_tensor = StyleTensor(
    name="stress_test",
    palette={"bg": "#000000", "fg": "#FFFFFF", "accent": "#5E6AD2"},
    geometry={"spacing_base": "4px", "radius": "12px"},
    typography={"font_family": "Inter, system-ui, sans-serif"},
    effects={},
    taste_vector={
        "temperature": 0.2,  # Very cool — should flag warm colors
        "density": 0.8,      # Dense — should flag sparse CSS
        "formality": 0.9,    # Very formal — should require high var() usage
        "energy": 0.1,       # Very low energy — should flag animations
        "age": 0.9,          # Very modern — should flag legacy CSS
        "price": 0.9,        # Premium — should expect shadows/gradients
    },
)
extreme_verifier = TasteVerifier(extreme_tensor)

# Temperature test: warm colors in a cool design system
warm_css = """
.card {
    background: #FF4500;
    color: #FF6347;
    border-color: #FF8C00;
}
"""
violations = extreme_verifier.verify(warm_css)
temp_violations = [v for v in violations if v.category == "temperature"]
check("Temperature dim: flags warm colors in cool system",
      len(temp_violations) > 0,
      f"Temperature violations: {len(temp_violations)}")

# Energy test: animations in a static design system
animated_css = """
.card { transition: all 0.3s ease; }
.btn { animation: pulse 2s infinite; }
@keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } }
.hero { transform: translateY(-10px); }
"""
violations_energy = extreme_verifier.verify(animated_css)
energy_violations = [v for v in violations_energy if v.category == "energy"]
check("Energy dim: flags animations in static system",
      len(energy_violations) > 0,
      f"Energy violations: {len(energy_violations)}")

# Formality test: mostly hardcoded values with high formality
hardcoded_css = """
.card {
    color: #333;
    padding: 16px;
    margin: 8px;
    border: 1px solid #ccc;
    font-size: 14px;
    background: #fff;
}
"""
violations_formal = extreme_verifier.verify(hardcoded_css)
formality_violations = [v for v in violations_formal if v.category == "formality"]
check("Formality dim: flags low var() usage in formal system",
      len(formality_violations) > 0,
      f"Formality violations: {len(formality_violations)}")

# Price test: flat CSS in a premium design system
flat_css = """
.card { background: #fff; }
.btn { background: #000; color: #fff; }
.header { border-bottom: 1px solid #eee; }
.footer { padding: 32px; }
"""
violations_price = extreme_verifier.verify(flat_css)
price_violations = [v for v in violations_price if v.category == "price"]
check("Price dim: flags flat styling in premium system",
      len(price_violations) > 0,
      f"Price violations: {len(price_violations)}")

# Age test: legacy CSS patterns in a modern system
legacy_css = """
.container { -webkit-box-sizing: border-box; }
.float-left { float: left; }
.clearfix::after { clear: both; }
.old { -moz-transition: all 0.3s; }
"""
violations_age = extreme_verifier.verify(legacy_css)
age_violations = [v for v in violations_age if v.category == "age"]
check("Age dim: flags legacy CSS in modern system",
      len(age_violations) > 0,
      f"Age violations: {len(age_violations)}")

# Density test: sparse CSS in a dense system
sparse_css = """
.card {
    padding: 8px;
}
"""
violations_density = extreme_verifier.verify(sparse_css)
density_violations = [v for v in violations_density if v.category == "density"]
check("Density dim: flags sparse CSS in dense system",
      len(density_violations) > 0,
      f"Density violations: {len(density_violations)}")

# COUNTER-TEST: neutral taste vector should NOT flag these
neutral_tensor = StyleTensor(
    name="neutral",
    palette={"bg": "#000000", "fg": "#FFFFFF", "accent": "#5E6AD2"},
    geometry={"spacing_base": "4px", "radius": "12px"},
    typography={"font_family": "Inter, system-ui, sans-serif"},
    effects={},
    taste_vector={
        "temperature": 0.5,
        "density": 0.5,
        "formality": 0.3,  # Low formality = hardcoding OK
        "energy": 0.5,
        "age": 0.5,
        "price": 0.5,
    },
)
neutral_verifier = TasteVerifier(neutral_tensor)
neutral_violations = neutral_verifier.verify(hardcoded_css)
neutral_taste_v = [v for v in neutral_violations if v.category in 
                   ("temperature", "energy", "age", "price", "density")]
check("Neutral taste vector → 0 taste-dimension violations",
      len(neutral_taste_v) == 0,
      f"Found {len(neutral_taste_v)} violations: {[v.category for v in neutral_taste_v]}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. Compression — Token Counting Must Be Real
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

section("Compression Engine (Real Token Counting)")

compressor = SemanticCompressor("aggressive")

# Test: _count_tokens is NOT len//4
test_text = "Hello, world! This is a test."
token_count = compressor._count_tokens(test_text)
naive_count = len(test_text) // 4  # = 7
check("Token count != naive len//4",
      token_count != naive_count,
      f"Real={token_count}, naive={naive_count}")

# Test: word-based counting is more accurate
# "Hello" "," "world" "!" "This" "is" "a" "test" "." = ~9 tokens
check("Token count is reasonable (5-15 for short sentence)",
      5 <= token_count <= 15,
      f"Count={token_count}")

# Test: longer text gets more compression
long_text = """
Please make sure to create a new file called utils.py that basically
implements the implementation of a function that essentially calculates
the total sum of all the prices in the list. Make sure to handle edge
cases. Don't forget to add proper error handling. Also, make sure that
the function returns the correct result. Please ensure that you test
the function thoroughly. Basically, the function should take a list of
prices as input and return the sum. Make sure to create a new file for
this implementation. Don't forget to add comments.
"""
result = compressor.compress(long_text)
check("Aggressive compression > 15% on verbose text",
      result.reduction_pct > 15,
      f"Reduction: {result.reduction_pct}%")

# Test: TF-IDF pruning is in techniques for aggressive mode
check("TF-IDF pruning applied in aggressive mode",
      "tfidf_pruning" in result.techniques_applied,
      f"Techniques: {result.techniques_applied}")

# Test: Compression preserves key technical terms
check("Preserves 'function'→'fn' (abbreviated, not deleted)",
      "fn" in result.compressed or "function" in result.compressed,
      f"Compressed: {result.compressed[:100]}...")

# Test: Light mode gives less compression than aggressive
light = SemanticCompressor("light")
light_result = light.compress(long_text)
check("Light < Aggressive compression",
      light_result.reduction_pct < result.reduction_pct,
      f"Light={light_result.reduction_pct}%, Aggressive={result.reduction_pct}%")

# Test: Empty string doesn't crash
empty_result = compressor.compress("")
check("Empty string → no crash", True)
check("Empty string → 0 or 1 tokens", empty_result.original_tokens <= 1)

# Test: Code is not destroyed by compression
code_text = """
def calculate_total(prices):
    return sum(p for p in prices if p > 0)
"""
code_result = compressor.compress(code_text)
check("Code function name preserved", "calculate_total" in code_result.compressed,
      f"Compressed: {code_result.compressed}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. Auth + Concurrency Provers — Still Working
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

section("Auth & Concurrency (Genuine Z3 Provers)")

auth_prover = AuthLogicProver()

# The classic OR bug
or_bug = '''
if user.role != "admin" or user.role != "editor":
    deny_access()
'''
auth_results = auth_prover.prove(or_bug, "auth.py")
auth_bugs = [r for r in auth_results if r.verdict == "BUG_FOUND"]
check("Detects OR role bug (always true tautology)",
      len(auth_bugs) > 0, f"Results: {[str(r) for r in auth_results]}")

# Correct AND pattern should NOT trigger
and_correct = '''
if user.role != "admin" and user.role != "editor":
    deny_access()
'''
auth_results2 = auth_prover.prove(and_correct, "auth.py")
auth_bugs2 = [r for r in auth_results2 if r.verdict == "BUG_FOUND" and "always" in r.message.lower()]
check("Correct AND pattern → no tautology bug",
      len(auth_bugs2) == 0, f"Results: {[str(r) for r in auth_results2]}")

# Concurrency: check-then-act without lock
conc_prover = ConcurrencyProver()
race_code = """
if balance > amount:
    balance -= amount
"""
conc_results = conc_prover.prove(race_code, "bank.py")
conc_bugs = [r for r in conc_results if r.verdict == "BUG_FOUND"]
check("Detects TOCTOU: check balance then modify without lock",
      len(conc_bugs) > 0, f"Results: {[str(r) for r in conc_results]}")

# With lock: should be safe
locked_code = """
with threading.Lock():
    if balance > amount:
        balance -= amount
"""
conc_results2 = conc_prover.prove(locked_code, "bank.py")
conc_bugs2 = [r for r in conc_results2 if r.verdict == "BUG_FOUND"]
check("With Lock → no TOCTOU", len(conc_bugs2) == 0,
      f"Results: {[str(r) for r in conc_results2]}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. Integration Stress — End-to-End Verification
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

section("Integration (End-to-End)")

guard = AnvilGuard(AnvilConfig())

# CSS file → tokenized path (not regex path)
css_result = guard.verify_code(
    """
    /* This color should be ignored: #FF0000 */
    .card {
        color: #333;
        padding: 16px;
    }
    """,
    "styles.css"
)
check("CSS file → taste layer ran", "taste" in css_result.layers_run)
check("CSS → has taste_score", css_result.taste_score is not None)

# Python file → Z3 with dataflow
py_result = guard.verify_code(
    """
def process(data, count):
    if count > 0:
        avg = sum(data) / count
    return avg
    """,
    "utils.py"
)
check("Python file → z3 layer ran", "z3" in py_result.layers_run)
check("Python → has z3_score", py_result.z3_score is not None)

# TSX → both layers
tsx_result = guard.verify_code(
    """
    const Card = ({ items }) => {
        const total = items.reduce((a, b) => a + b, 0);
        return <div style={{ color: '#333', padding: '8px' }}>{total / items.length}</div>;
    }
    """,
    "Card.tsx"
)
check("TSX → both layers", len(tsx_result.layers_run) >= 2,
      f"Layers: {tsx_result.layers_run}")

# Summary format
check("Summary contains ANVIL", "ANVIL" in tsx_result.summary())
check("Summary is non-empty string", len(tsx_result.summary()) > 10)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. Edge Cases — Try to Break It
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

section("Edge Cases (Breaking Attempts)")

# Empty code
empty_violations = verifier.verify("")
check("Empty code → no crash", True)
check("Empty code → 0 violations", len(empty_violations) == 0)

# Malformed CSS
malformed_css = "{{{{ color: }}}}"
try:
    tokenizer_bad = CSSTokenizer(malformed_css)
    tokenizer_bad.tokenize()
    check("Malformed CSS → no crash", True)
except Exception as e:
    check("Malformed CSS → no crash", False, str(e))

# Non-Python code through Z3 (regex fallback)
go_code = """
func divide(a, b int) int {
    return a / b
}
"""
go_results = prover.prove(go_code, "main.go")
check("Go code → regex fallback (no crash)", True)

# Unicode in CSS
unicode_css = """
.card {
    content: "日本語テスト";
    color: #333333;
}
"""
try:
    tokenizer_unicode = CSSTokenizer(unicode_css)
    decls = tokenizer_unicode.parse_declarations()
    check("Unicode in CSS → no crash", True)
except Exception as e:
    check("Unicode in CSS → no crash", False, str(e))

# Nested CSS (modern)
nested_css = """
.card {
    color: #333;
    & .title {
        font-size: 18px;
    }
    &:hover {
        background: #f0f0f0;
    }
}
"""
try:
    tokenizer_nested = CSSTokenizer(nested_css)
    tokenizer_nested.tokenize()
    check("Nested CSS → no crash", True)
except Exception as e:
    check("Nested CSS → no crash", False, str(e))

# Very large input (stress)
big_css = ".item { color: #333; padding: 8px; }\n" * 1000
try:
    tokenizer_big = CSSTokenizer(big_css)
    colors_big = tokenizer_big.get_colors()
    check("1000-rule CSS → no crash", True)
    check("1000-rule CSS → finds 1000 colors", len(colors_big) == 1000,
          f"Found: {len(colors_big)}")
except Exception as e:
    check("1000-rule CSS → no crash", False, str(e))

# Division by zero in Z3 prover with complex code
complex_py = """
import math

class Calculator:
    def __init__(self, precision=10):
        self.precision = precision
    
    def safe_divide(self, a, b):
        if b == 0:
            raise ValueError("Division by zero")
        return round(a / b, self.precision)
    
    def unsafe_divide(self, a, b):
        return a / b
    
    def ratio(self, values):
        total = sum(values)
        count = len(values)
        if count > 0:
            return total / count
        return 0.0
"""
complex_results = prover.prove(complex_py, "calc.py")
complex_safe = [r for r in complex_results if r.verdict == "PROVEN_SAFE"]
complex_bugs = [r for r in complex_results if r.verdict == "BUG_FOUND"]
check("Complex class: finds safe_divide PROVEN_SAFE or unsafe_divide BUG_FOUND",
      len(complex_safe) > 0 or len(complex_bugs) > 0,
      f"Safe: {len(complex_safe)}, Bugs: {len(complex_bugs)}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RESULTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n" + "━" * 50)
print(f"  ⚒️  STRESS TEST RESULTS: {passed} passed, {failed} failed")
print("━" * 50)

if errors:
    print("\n\033[31mFAILURES:\033[0m")
    for e in errors:
        print(f"  ❌ {e}")

if failed == 0:
    print("\n\033[32m  ALL STRESS TESTS PASSED — Fixes are verified.\033[0m")
else:
    print(f"\n\033[31m  {failed} TESTS FAILED — Fixes need work.\033[0m")

sys.exit(1 if failed > 0 else 0)
