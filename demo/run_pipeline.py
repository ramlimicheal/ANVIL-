"""Run the full ANVIL extraction pipeline on the test dashboard image."""
import sys
import os
import json

sys.path.insert(0, "/Users/apple/Desktop/Alpha/ANVIL/.venv/lib/python3.14/site-packages")
sys.path.insert(0, "/Users/apple/Desktop/Alpha/ANVIL")

from anvil.extract.compiler import extract_design_system, compile_design_system

IMAGE = "/Users/apple/Desktop/Alpha/ANVIL/demo/test_dashboard.png"
OUTPUT = "/Users/apple/Desktop/Alpha/ANVIL/demo/output"

print("=" * 60)
print("  ANVIL — Screenshot → Design System Extraction")
print("=" * 60)
print()

# Phase 1: Extract
ds = extract_design_system(IMAGE)

print()
print("─" * 60)
print("  Phase 2: Compile to tokens")
print("─" * 60)
compile_design_system(ds, OUTPUT)

# Phase 3: Show results
print()
print("─" * 60)
print("  EXTRACTED DESIGN SYSTEM")
print("─" * 60)

ds_dict = ds.to_dict()
print(json.dumps(ds_dict, indent=2, default=str))

print()
print("─" * 60)
print("  OUTPUT FILES")
print("─" * 60)
for f in os.listdir(OUTPUT):
    fpath = os.path.join(OUTPUT, f)
    size = os.path.getsize(fpath)
    print(f"  ✅ {f} ({size} bytes)")

# Show CSS tokens
print()
print("─" * 60)
print("  CSS TOKENS (tokens.css)")
print("─" * 60)
with open(os.path.join(OUTPUT, "tokens.css")) as f:
    print(f.read())

# Show taste vector
print()
print("─" * 60)
print("  6D TASTE VECTOR")
print("─" * 60)
tv = ds_dict.get("taste_vector", {})
labels = {
    "temperature": ("❄️ Cool", "🔥 Warm"),
    "density": ("Sparse", "Dense"),
    "formality": ("Casual", "Formal"),
    "energy": ("Calm", "Energetic"),
    "age": ("Classic", "Modern"),
    "price": ("Budget", "Premium"),
}
for key, val in tv.items():
    lo, hi = labels.get(key, ("Low", "High"))
    bar_len = int(val * 20)
    bar = "█" * bar_len + "░" * (20 - bar_len)
    side = hi if val > 0.5 else lo
    print(f"  {key:14s} [{bar}] {val:.2f}  → {side}")

print()
print("=" * 60)
print("  ANVIL extraction complete.")
print("=" * 60)
