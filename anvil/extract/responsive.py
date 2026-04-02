"""
ANVIL Responsive Framework — Generates responsive rules based on page type.
Maps page classifications to known responsive patterns and breakpoints.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from .classifier import PageClassification


STANDARD_BREAKPOINTS = {
    "sm": 640,
    "md": 768,
    "lg": 1024,
    "xl": 1280,
    "2xl": 1536,
}


@dataclass
class ResponsiveRule:
    """A single responsive behavior rule."""
    breakpoint: str       # e.g., "md" (768px)
    max_width: int        # px value
    selector: str         # CSS selector target
    behavior: str         # human-readable description
    css: str              # actual CSS to apply

    def to_dict(self) -> dict:
        return {
            "breakpoint": self.breakpoint,
            "max_width": self.max_width,
            "selector": self.selector,
            "behavior": self.behavior,
            "css": self.css,
        }


@dataclass
class ResponsiveFramework:
    """Complete responsive framework for a page type."""
    page_type: str
    breakpoints: Dict[str, int]
    rules: List[ResponsiveRule]
    container_max_width: int = 1280
    mobile_first: bool = True

    def to_dict(self) -> dict:
        return {
            "page_type": self.page_type,
            "breakpoints": self.breakpoints,
            "container_max_width": f"{self.container_max_width}px",
            "rules": [r.to_dict() for r in self.rules],
        }

    def to_css(self) -> str:
        """Generate CSS media queries."""
        lines = []
        # Group by breakpoint
        by_bp: Dict[int, List[ResponsiveRule]] = {}
        for rule in self.rules:
            by_bp.setdefault(rule.max_width, []).append(rule)

        for max_w in sorted(by_bp.keys(), reverse=True):
            lines.append(f"@media (max-width: {max_w}px) {{")
            for rule in by_bp[max_w]:
                lines.append(f"  /* {rule.behavior} */")
                lines.append(f"  {rule.selector} {{ {rule.css} }}")
            lines.append("}")
            lines.append("")

        return "\n".join(lines)


def generate_responsive(classification: PageClassification) -> ResponsiveFramework:
    """Generate responsive framework from page classification.

    Args:
        classification: PageClassification from classifier.py

    Returns:
        ResponsiveFramework with breakpoints and rules
    """
    page_type = classification.page_type
    w, h = classification.image_size

    # Determine container width
    container = min(classification.content_width or 1280, 1440)

    # Select breakpoints based on content width
    breakpoints = dict(STANDARD_BREAKPOINTS)

    # Generate rules by page type
    rules_fn = _PAGE_RULES.get(page_type, _rules_generic)
    rules = rules_fn(classification)

    return ResponsiveFramework(
        page_type=page_type,
        breakpoints=breakpoints,
        rules=rules,
        container_max_width=container,
    )


def _rules_landing(cls: PageClassification) -> List[ResponsiveRule]:
    """Responsive rules for landing pages."""
    rules = [
        # Navbar → hamburger
        ResponsiveRule("md", 768, ".navbar", "Collapse nav to hamburger menu",
                       "flex-direction: column; gap: 0;"),
        ResponsiveRule("md", 768, ".nav-links", "Hide desktop nav links",
                       "display: none;"),
        ResponsiveRule("md", 768, ".hamburger", "Show mobile menu button",
                       "display: flex;"),
        # Hero
        ResponsiveRule("lg", 1024, ".hero", "Stack hero content vertically",
                       "flex-direction: column; text-align: center; padding: 48px 24px;"),
        ResponsiveRule("sm", 640, ".hero h1", "Reduce hero heading size",
                       "font-size: 28px; line-height: 1.2;"),
        # Features grid
        ResponsiveRule("lg", 1024, ".features-grid", "Features 3-col → 2-col",
                       "grid-template-columns: repeat(2, 1fr);"),
        ResponsiveRule("sm", 640, ".features-grid", "Features → single column",
                       "grid-template-columns: 1fr;"),
        # Pricing
        ResponsiveRule("lg", 1024, ".pricing-grid", "Pricing cards 3 → 1 col",
                       "grid-template-columns: 1fr; max-width: 400px; margin: 0 auto;"),
        # CTA
        ResponsiveRule("sm", 640, ".cta", "CTA full width",
                       "padding: 32px 16px;"),
        ResponsiveRule("sm", 640, ".cta .button", "CTA button full width",
                       "width: 100%;"),
        # Footer
        ResponsiveRule("md", 768, ".footer-grid", "Footer columns stack",
                       "grid-template-columns: 1fr;"),
    ]
    return rules


def _rules_dashboard(cls: PageClassification) -> List[ResponsiveRule]:
    """Responsive rules for dashboards."""
    rules = [
        # Sidebar
        ResponsiveRule("lg", 1024, ".sidebar", "Collapse sidebar to icons only",
                       "width: 64px; overflow: hidden;"),
        ResponsiveRule("lg", 1024, ".sidebar .nav-text", "Hide sidebar labels",
                       "display: none;"),
        ResponsiveRule("md", 768, ".sidebar", "Hide sidebar completely",
                       "display: none;"),
        ResponsiveRule("md", 768, ".mobile-nav", "Show mobile bottom nav",
                       "display: flex;"),
        # Stat cards
        ResponsiveRule("lg", 1024, ".stats-grid", "Stat cards 4 → 2 col",
                       "grid-template-columns: repeat(2, 1fr);"),
        ResponsiveRule("sm", 640, ".stats-grid", "Stat cards → single column",
                       "grid-template-columns: 1fr;"),
        # Charts
        ResponsiveRule("md", 768, ".chart-grid", "Charts stack vertically",
                       "grid-template-columns: 1fr;"),
        # Tables
        ResponsiveRule("md", 768, ".data-table", "Table → card list on mobile",
                       "display: flex; flex-direction: column;"),
        ResponsiveRule("md", 768, ".data-table thead", "Hide table header",
                       "display: none;"),
        # Main content
        ResponsiveRule("md", 768, ".main-content", "Full width without sidebar",
                       "margin-left: 0; width: 100%;"),
    ]
    return rules


def _rules_login(cls: PageClassification) -> List[ResponsiveRule]:
    """Responsive rules for login/signup pages."""
    rules = [
        ResponsiveRule("sm", 640, ".auth-card", "Auth card full width on mobile",
                       "max-width: 100%; margin: 16px; border-radius: 16px;"),
        ResponsiveRule("sm", 640, ".auth-card input", "Full width inputs",
                       "width: 100%;"),
        ResponsiveRule("sm", 640, ".auth-card", "Reduce card padding",
                       "padding: 24px 16px;"),
    ]
    return rules


def _rules_modal(cls: PageClassification) -> List[ResponsiveRule]:
    """Responsive rules for modals/cards."""
    rules = [
        ResponsiveRule("sm", 640, ".modal-card", "Modal scales down",
                       "max-width: calc(100vw - 32px); margin: 16px;"),
        ResponsiveRule("sm", 640, ".modal-card .wizard", "Stack wizard columns",
                       "grid-template-columns: 1fr;"),
        ResponsiveRule("sm", 640, ".modal-card", "Reduce modal padding",
                       "padding: 16px;"),
    ]
    return rules


def _rules_settings(cls: PageClassification) -> List[ResponsiveRule]:
    """Responsive rules for settings pages."""
    rules = [
        ResponsiveRule("md", 768, ".settings-sidebar", "Settings nav → top tabs",
                       "flex-direction: row; overflow-x: auto; width: 100%;"),
        ResponsiveRule("md", 768, ".settings-content", "Full width content",
                       "width: 100%; padding: 16px;"),
        ResponsiveRule("sm", 640, "input, select, textarea", "Full width form fields",
                       "width: 100%;"),
    ]
    return rules


def _rules_pricing(cls: PageClassification) -> List[ResponsiveRule]:
    """Responsive rules for pricing pages."""
    rules = [
        ResponsiveRule("lg", 1024, ".pricing-grid", "Pricing 3-col → stacked",
                       "grid-template-columns: 1fr; max-width: 500px; margin: 0 auto;"),
        ResponsiveRule("sm", 640, ".pricing-card", "Compact pricing cards",
                       "padding: 24px 16px;"),
    ]
    return rules


def _rules_generic(cls: PageClassification) -> List[ResponsiveRule]:
    """Generic responsive rules for unclassified pages."""
    cols = cls.estimated_columns
    rules = [
        ResponsiveRule("md", 768, ".container", "Reduce container padding",
                       "padding-left: 16px; padding-right: 16px;"),
    ]
    if cols >= 3:
        rules.append(ResponsiveRule(
            "lg", 1024, ".grid", f"{cols}-col → 2-col grid",
            "grid-template-columns: repeat(2, 1fr);"))
        rules.append(ResponsiveRule(
            "sm", 640, ".grid", "Grid → single column",
            "grid-template-columns: 1fr;"))
    return rules


_PAGE_RULES = {
    "landing": _rules_landing,
    "dashboard": _rules_dashboard,
    "login": _rules_login,
    "signup": _rules_login,
    "modal": _rules_modal,
    "settings": _rules_settings,
    "pricing": _rules_pricing,
}
