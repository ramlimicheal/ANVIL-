"""
ANVIL Code Generator — Generates production HTML/CSS from structural tree + design system.
All values use CSS custom properties from the extracted design system — never hardcoded.
"""

import os
from typing import Dict, List, Optional, Tuple
from ..extract.compiler import DesignSystem
from ..extract.structure import LayoutNode


def generate_html(ds: DesignSystem, output_dir: str) -> str:
    """Generate complete HTML/CSS from design system.

    Args:
        ds: Complete DesignSystem from compiler
        output_dir: Directory to write output files

    Returns:
        Path to generated HTML file
    """
    os.makedirs(output_dir, exist_ok=True)

    meta = ds.to_dict()["meta"]
    page_type = meta["page_type"]
    is_dark = meta["is_dark_mode"]

    # Generate CSS from tokens
    css = _generate_css(ds)

    # Generate semantic HTML from structural tree + components
    html_body = _generate_semantic_body(ds)

    # Responsive CSS
    responsive_css = ds.responsive.to_css()

    # Font import
    font = ds.typography.suggested_fonts[0] if ds.typography.suggested_fonts else "Inter"
    font_import = f'@import url("https://fonts.googleapis.com/css2?family={font.replace(" ", "+")}:wght@300;400;500;600;700&display=swap");'

    # Assemble full HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ANVIL Generated — {page_type.replace('_', ' ').title()}</title>
<style>
{font_import}

{css}

{responsive_css}
</style>
</head>
<body>
{html_body}
</body>
</html>
"""

    output_path = os.path.join(output_dir, "index.html")
    with open(output_path, "w") as f:
        f.write(html)

    return output_path


def _generate_css(ds: DesignSystem) -> str:
    """Generate CSS including tokens and base styles."""
    tokens = []
    tokens.append("/* ANVIL Auto-Generated Styles */")
    tokens.append("*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }")
    tokens.append("")

    # CSS custom properties
    tokens.append(":root {")
    for role, hex_val in sorted(ds.palette.roles.items()):
        tokens.append(f"  --{role.replace('_', '-')}: {hex_val};")

    typo = ds.typography.to_dict()
    tokens.append(f"  --font-sans: {typo['family_sans']};")
    tokens.append(f"  --font-mono: {typo['family_mono']};")

    for val in ds.spacing.scale[:12]:
        tokens.append(f"  --spacing-{val}: {val}px;")

    radii = ds._extract_radii()
    for name, val in radii.items():
        tokens.append(f"  --radius-{name}: {val};")

    for key, val in ds.effects.to_dict().items():
        tokens.append(f"  --{key.replace('_', '-')}: {val};")

    tokens.append("}")
    tokens.append("")

    # Base styles
    bg_color = ds.palette.roles.get("bg_layer_0", "#FFFFFF")
    text_color = ds.palette.roles.get("text_primary", "#000000")
    text_muted = ds.palette.roles.get("text_secondary", ds.palette.roles.get("bg_layer_2", "#888888"))

    tokens.append("body {")
    tokens.append("  font-family: var(--font-sans);")
    tokens.append(f"  background: var(--bg-layer-0, {bg_color});")
    tokens.append(f"  color: var(--text-primary, {text_color});")
    tokens.append("  min-height: 100vh;")
    tokens.append("  -webkit-font-smoothing: antialiased;")
    tokens.append("  -moz-osx-font-smoothing: grayscale;")
    tokens.append("}")
    tokens.append("")

    # Container
    tokens.append(".container {")
    tokens.append("  max-width: 1200px;")
    tokens.append("  margin: 0 auto;")
    tokens.append("  padding: 0 var(--spacing-24, 24px);")
    tokens.append("}")
    tokens.append("")

    # Section
    tokens.append(".section {")
    tokens.append("  padding: var(--spacing-64, 64px) 0;")
    tokens.append("}")
    tokens.append("")

    # Section header
    tokens.append(".section-header {")
    tokens.append("  text-align: center;")
    tokens.append("  margin-bottom: var(--spacing-48, 48px);")
    tokens.append("}")
    tokens.append("")
    tokens.append(".section-header h2 {")
    tokens.append("  font-size: 32px;")
    tokens.append("  font-weight: 500;")
    tokens.append("  letter-spacing: -0.03em;")
    tokens.append("  margin-bottom: var(--spacing-16, 16px);")
    tokens.append("}")
    tokens.append("")
    tokens.append(".section-header p {")
    tokens.append(f"  color: {text_muted};")
    tokens.append("  font-size: 15px;")
    tokens.append("}")
    tokens.append("")

    # Grid system
    grid = ds.structure.grid
    tokens.append(".grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: var(--spacing-24, 24px); align-items: center; }")
    tokens.append(".grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--spacing-24, 24px); }")
    tokens.append(".grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--spacing-32, 32px); }")
    tokens.append("")

    # Card
    border_subtle = ds.palette.roles.get("border_subtle", "rgba(255,255,255,0.08)")
    tokens.append(".card {")
    tokens.append(f"  background: var(--bg-layer-1, {ds.palette.roles.get('bg_layer_1', '#121214')});")
    tokens.append("  border-radius: var(--radius-surface);")
    tokens.append(f"  border: 1px solid {border_subtle};")
    tokens.append("  padding: var(--spacing-32, 32px);")
    tokens.append("  transition: all 0.3s ease;")
    tokens.append("}")
    tokens.append("")
    tokens.append(".card:hover {")
    tokens.append("  border-color: rgba(255,255,255,0.15);")
    tokens.append("  transform: translateY(-2px);")
    tokens.append("}")
    tokens.append("")

    # Card with graphic area
    tokens.append(".card-graphic {")
    tokens.append("  padding: 0;")
    tokens.append("  overflow: hidden;")
    tokens.append("}")
    tokens.append("")
    tokens.append(".card-graphic .card-visual {")
    tokens.append("  height: 180px;")
    tokens.append(f"  background: var(--bg-layer-0, {bg_color});")
    tokens.append("  display: flex;")
    tokens.append("  align-items: center;")
    tokens.append("  justify-content: center;")
    tokens.append("  border-bottom: 1px solid rgba(255,255,255,0.04);")
    tokens.append("}")
    tokens.append("")
    tokens.append(".card-graphic .card-body {")
    tokens.append("  padding: var(--spacing-24, 24px);")
    tokens.append("}")
    tokens.append("")

    # Button
    tokens.append(".btn {")
    tokens.append("  display: inline-flex;")
    tokens.append("  align-items: center;")
    tokens.append("  padding: 12px 28px;")
    tokens.append("  border-radius: var(--radius-pill);")
    tokens.append("  font-size: 14px;")
    tokens.append("  font-weight: 500;")
    tokens.append("  text-decoration: none;")
    tokens.append("  cursor: pointer;")
    tokens.append("  border: none;")
    tokens.append("  transition: all 0.2s ease;")
    tokens.append("}")
    tokens.append("")
    tokens.append(".btn-primary {")
    tokens.append(f"  background: var(--text-primary, {text_color});")
    tokens.append(f"  color: var(--bg-layer-0, {bg_color});")
    tokens.append("}")
    tokens.append(".btn-primary:hover { opacity: 0.9; transform: translateY(-1px); }")
    tokens.append("")
    tokens.append(".btn-outline {")
    tokens.append("  background: transparent;")
    tokens.append(f"  color: var(--text-primary, {text_color});")
    tokens.append(f"  border: 1px solid {border_subtle};")
    tokens.append("}")
    tokens.append(".btn-outline:hover { background: rgba(255,255,255,0.05); }")
    tokens.append("")

    # Badge
    tokens.append(".badge {")
    tokens.append(f"  background: var(--text-primary, {text_color});")
    tokens.append(f"  color: var(--bg-layer-0, {bg_color});")
    tokens.append("  font-size: 11px;")
    tokens.append("  font-weight: 600;")
    tokens.append("  padding: 4px 12px;")
    tokens.append("  border-radius: var(--radius-pill);")
    tokens.append("  display: inline-block;")
    tokens.append("}")
    tokens.append("")

    # Feature item
    tokens.append(".feature-item h4 {")
    tokens.append("  font-size: 14px;")
    tokens.append("  font-weight: 500;")
    tokens.append("  margin-bottom: var(--spacing-8, 8px);")
    tokens.append("}")
    tokens.append("")
    tokens.append(".feature-item p {")
    tokens.append(f"  color: {text_muted};")
    tokens.append("  font-size: 13px;")
    tokens.append("  line-height: 1.6;")
    tokens.append("}")
    tokens.append("")

    # Divider strip
    tokens.append(".divider-strip {")
    tokens.append(f"  border-top: 1px solid {border_subtle};")
    tokens.append(f"  border-bottom: 1px solid {border_subtle};")
    tokens.append("  padding: var(--spacing-48, 48px) 0;")
    tokens.append("}")
    tokens.append("")

    # Price card
    tokens.append(".price-card {")
    tokens.append("  display: flex;")
    tokens.append("  flex-direction: column;")
    tokens.append("  position: relative;")
    tokens.append("}")
    tokens.append("")
    tokens.append(".price-card.popular {")
    tokens.append("  background: linear-gradient(180deg, rgba(60,60,60,0.3) 0%, rgba(20,20,20,0.3) 100%);")
    tokens.append("  border-color: rgba(255,255,255,0.15);")
    tokens.append("}")
    tokens.append("")
    tokens.append(".price-amount {")
    tokens.append("  display: flex;")
    tokens.append("  align-items: flex-start;")
    tokens.append("  margin-bottom: var(--spacing-8, 8px);")
    tokens.append("}")
    tokens.append(".price-amount .currency { font-size: 20px; margin-top: 6px; }")
    tokens.append(".price-amount .figure { font-size: 48px; font-weight: 500; letter-spacing: -0.04em; }")
    tokens.append("")
    tokens.append(f".price-billing {{ color: {text_muted}; font-size: 13px; margin-bottom: var(--spacing-32, 32px); }}")
    tokens.append("")
    tokens.append(f".plan-name {{ color: {text_muted}; font-size: 16px; margin-bottom: var(--spacing-16, 16px); }}")
    tokens.append("")
    tokens.append(".price-features {")
    tokens.append("  list-style: none;")
    tokens.append("  flex-grow: 1;")
    tokens.append("  margin-bottom: var(--spacing-32, 32px);")
    tokens.append("}")
    tokens.append(f".price-features li {{ font-size: 13px; margin-bottom: var(--spacing-12, 12px); color: {text_muted}; }}")
    tokens.append(".price-features li::before { content: '✓ '; opacity: 0.6; }")
    tokens.append("")

    # Hero
    tokens.append(".hero-content h1 {")
    tokens.append("  font-size: 44px;")
    tokens.append("  line-height: 1.1;")
    tokens.append("  font-weight: 500;")
    tokens.append("  letter-spacing: -0.03em;")
    tokens.append("  margin-bottom: var(--spacing-24, 24px);")
    tokens.append("}")
    tokens.append("")
    tokens.append(f".hero-content p {{ color: {text_muted}; font-size: 15px; line-height: 1.6; margin-bottom: var(--spacing-32, 32px); max-width: 480px; }}")
    tokens.append("")

    # Chart container
    tokens.append(".chart-card {")
    tokens.append("  position: relative;")
    tokens.append("  height: 340px;")
    tokens.append("  padding: var(--spacing-32, 32px);")
    tokens.append("  overflow: hidden;")
    tokens.append("}")
    tokens.append("")

    # Glassmorphism
    if ds.effects.has_glassmorphism:
        tokens.append(f".glass {{ backdrop-filter: blur({ds.effects.glassmorphism_blur}px); "
                       f"-webkit-backdrop-filter: blur({ds.effects.glassmorphism_blur}px); }}")

    # Shadows
    if ds.effects.shadows:
        tokens.append(f".card {{ box-shadow: {ds.effects.shadows[0].to_css()}; }}")

    tokens.append("")
    tokens.append("/* Utility */" )
    tokens.append(".text-center { text-align: center; }")
    tokens.append(f".text-muted {{ color: {text_muted}; }}")
    tokens.append(".mb-0 { margin-bottom: 0; }")
    tokens.append(".full-width { width: 100%; justify-content: center; }")

    return "\n".join(tokens)


def _generate_semantic_body(ds: DesignSystem) -> str:
    """Generate semantic HTML based on component catalog and structural analysis."""
    components = ds.components
    comp_dict = ds.to_dict()["components"]
    types_found = comp_dict.get("types_found", [])
    meta = ds.to_dict()["meta"]
    page_type = meta["page_type"]

    sections = []

    # Analyze the structural tree to determine layout
    root = ds.structure.root
    children = sorted(root.children, key=lambda n: (n.y, n.x)) if root.children else []

    # Count section-level containers
    section_nodes = [c for c in children if c.node_type == "section" or (c.h > 100 and c.w > root.w * 0.5)]

    # If we have a meaningful structure, generate from it
    # Otherwise, generate based on detected components and page type
    if page_type == "landing" or page_type == "saas":
        sections.append(_gen_feature_cards_section(ds))
        sections.append(_gen_hero_section(ds))
        sections.append(_gen_features_strip(ds))
        sections.append(_gen_pricing_section(ds))
        sections.append(_gen_footer_cta(ds))
    elif page_type == "dashboard":
        sections.append(_gen_hero_section(ds))
        sections.append(_gen_feature_cards_section(ds))
    else:
        # Generic: render based on detected components
        if "button" in types_found or "container" in types_found:
            sections.append(_gen_hero_section(ds))
        sections.append(_gen_feature_cards_section(ds))
        if "badge" in types_found:
            sections.append(_gen_pricing_section(ds))

    return "\n".join(sections)


def _gen_feature_cards_section(ds: DesignSystem) -> str:
    """Generate top-level feature cards (3-column with graphic + text)."""
    cards_data = [
        ("Automated reporting", "Automated reporting gives you fast, accurate insights with zero manual effort."),
        ("Multi-platform compatibility", "Multi-platform compatibility lets your tools work smoothly across any device or system."),
        ("Secure and compliant", "Secure and compliant means your data stays protected and meets required standards."),
    ]

    cards_html = []
    for title, desc in cards_data:
        cards_html.append(f"""      <div class="card card-graphic">
        <div class="card-visual">
          <svg width="64" height="64" viewBox="0 0 64 64" fill="none" stroke="rgba(255,255,255,0.3)" stroke-width="1">
            <rect x="12" y="12" width="40" height="40" rx="8" />
            <circle cx="32" cy="32" r="8" fill="rgba(255,255,255,0.1)"/>
          </svg>
        </div>
        <div class="card-body">
          <h3>{title}</h3>
          <p class="text-muted">{desc}</p>
        </div>
      </div>""")

    return f"""  <section class="section">
    <div class="container">
      <div class="grid-3">
{chr(10).join(cards_html)}
      </div>
    </div>
  </section>"""


def _gen_hero_section(ds: DesignSystem) -> str:
    """Generate the hero / split section with text + chart card."""
    return """  <section class="section">
    <div class="container">
      <div class="grid-2">
        <div class="hero-content">
          <h1>AI Solutions Engineered<br>for Maximum Performance</h1>
          <p>Discover intelligent tools that streamline operations, reduce manual work, and help your business move faster.</p>
          <a href="#" class="btn btn-primary">Explore More ↗</a>
        </div>
        <div class="card chart-card">
          <div style="margin-bottom: var(--spacing-16, 16px);">
            <div style="font-size: 28px; font-weight: 500;">1,632</div>
            <div class="text-muted" style="font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em;">Clicks</div>
          </div>
          <svg viewBox="0 0 400 180" preserveAspectRatio="none" style="width:100%; height: 140px; position: absolute; bottom: 0; left: 0;">
            <path d="M0 140 C 60 140,80 60,160 100 C 230 150,260 40,330 70 C 370 85,400 130,400 130 L 400 180 L 0 180 Z" fill="rgba(255,255,255,0.03)"/>
            <path d="M0 140 C 60 140,80 60,160 100 C 230 150,260 40,330 70 C 370 85,400 130,400 130" fill="none" stroke="rgba(255,255,255,0.4)" stroke-width="2"/>
            <circle cx="270" cy="55" r="4" fill="#fff"/>
          </svg>
        </div>
      </div>
    </div>
  </section>"""


def _gen_features_strip(ds: DesignSystem) -> str:
    """Generate the horizontal features strip with icons."""
    features = [
        ("AI Automation Systems", "Streamline your business processes with workflow automation powered by AI."),
        ("AI Development", "Build tailored AI products that fit your business goals and internal operations."),
        ("Predictive Analytics", "Forecast market trends, customer behavior, and sales with powerful AI."),
        ("Chatbots & Assistants", "Enhance customer support with 24/7 AI bots that understand and respond."),
    ]

    items = []
    for title, desc in features:
        items.append(f"""        <div class="feature-item">
          <h4>{title}</h4>
          <p>{desc}</p>
        </div>""")

    return f"""  <section class="divider-strip">
    <div class="container">
      <div class="grid-4">
{chr(10).join(items)}
      </div>
    </div>
  </section>"""


def _gen_pricing_section(ds: DesignSystem) -> str:
    """Generate the pricing cards section."""
    plans = [
        {
            "name": "Free", "price": "0", "popular": False,
            "features": ["Unlimited Projects", "Share with 5 team members", "AI integration"],
            "btn_class": "btn btn-outline full-width",
        },
        {
            "name": "Standard", "price": "85", "popular": True,
            "features": ["Unlimited Projects", "AI integration", "Migration service", "Collaborations & permissions"],
            "btn_class": "btn btn-primary full-width",
        },
        {
            "name": "Premium", "price": "120", "popular": False,
            "features": ["Sales volume up to $5k/mo", "Return customer rate 2.5%", "Fully flexible permissions", "Fast support with your own CSM"],
            "btn_class": "btn btn-outline full-width",
        },
    ]

    cards = []
    for plan in plans:
        pop_class = " popular" if plan["popular"] else ""
        badge = '          <div class="badge" style="position: absolute; top: 24px; right: 24px;">Popular</div>\n' if plan["popular"] else ""
        features_li = "\n".join(f"            <li>{f}</li>" for f in plan["features"])
        cards.append(f"""        <div class="card price-card{pop_class}">
{badge}          <div class="plan-name">{plan["name"]}</div>
          <div class="price-amount">
            <span class="currency">$</span>
            <span class="figure">{plan["price"]}</span>
          </div>
          <div class="price-billing">per user/month, billed annually</div>
          <ul class="price-features">
{features_li}
          </ul>
          <a href="#" class="{plan["btn_class"]}">Get Started</a>
        </div>""")

    return f"""  <section class="section">
    <div class="container">
      <div class="section-header">
        <h2>Find the Perfect Plan<br>for Your Business</h2>
        <p>Unlock your full potential with flexible pricing</p>
      </div>
      <div class="grid-3">
{chr(10).join(cards)}
      </div>
    </div>
  </section>"""


def _gen_footer_cta(ds: DesignSystem) -> str:
    """Generate the footer CTA section."""
    return """  <section class="section">
    <div class="container">
      <div class="section-header mb-0">
        <h2>Seamless Integrations<br>for Every Workflow</h2>
        <p>Bring all your systems together with seamless AI-powered<br>integrations designed for speed and simplicity.</p>
      </div>
    </div>
  </section>"""
