"""Test the V2 layout engine + generation pipeline."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anvil.extract.compiler import extract_design_system
from anvil.generate.layout_engine import build_layout
from anvil.generate.engine import generate_html

image = os.path.join(os.path.dirname(__file__), "test_dashboard.png")
if not os.path.exists(image):
    print("No test image. Run generate_test_dashboard.py first.")
    sys.exit(1)

print("=== EXTRACTING ===")
ds = extract_design_system(image)

print("\n=== LAYOUT ENGINE ===")
specs = build_layout(ds)
print(f"Top-level specs: {len(specs)}")
for s in specs:
    print(f"  [{s.id}] {s.component_type} tag={s.tag} layout={s.layout_direction} "
          f"children={len(s.children)} bounds={s.bounds}")
    for c in s.children[:8]:
        print(f"    [{c.id}] {c.component_type} tag={c.tag} layout={c.layout_direction} "
              f"ch={len(c.children)}")

print("\n=== GENERATING HTML ===")
output_dir = os.path.join(os.path.dirname(__file__), "output_v2")
html_path = generate_html(ds, output_dir)
size = os.path.getsize(html_path)
print(f"Output: {html_path} ({size} bytes)")

# Quick stats
import re
with open(html_path) as f:
    content = f.read()
anvil_classes = re.findall(r'anvil-\d+', content)
print(f"ANVIL components in HTML: {len(set(anvil_classes))}")
css_vars = re.findall(r'var\(--[^)]+\)', content)
print(f"CSS var() references: {len(css_vars)}")
print("\nDone.")
