"""
StyleTensor — The mathematical encoding of design taste.
Captures palette, geometry, typography, effects as a verifiable data structure.
"""

import json
import colorsys
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from pathlib import Path


@dataclass
class StyleTensor:
    """Complete aesthetic DNA in a single verifiable object."""
    name: str
    palette: Dict[str, str]
    geometry: Dict[str, str]
    typography: Dict[str, str]
    effects: Dict[str, str]
    taste_vector: Dict[str, float] = field(default_factory=dict)
    vibe: str = ""

    def to_css_vars(self) -> str:
        lines = [":root {"]
        for section in [self.palette, self.geometry, self.typography, self.effects]:
            for k, v in section.items():
                lines.append(f"  --{k.replace('_', '-')}: {v};")
        lines.append("}")
        return "\n".join(lines)

    def to_tailwind_config(self) -> dict:
        return {
            "colors": {
                "bg": {
                    "0": self.palette.get("bg_layer_0", "#09090B"),
                    "1": self.palette.get("bg_layer_1", "#121214"),
                    "2": self.palette.get("bg_layer_2", "#1A1A1C"),
                },
                "text": {
                    "primary": self.palette.get("text_primary", "#FAFAFA"),
                    "secondary": self.palette.get("text_secondary", "#71717A"),
                },
                "accent": {
                    "primary": self.palette.get("accent_primary", "#5E6AD2"),
                    "secondary": self.palette.get("accent_secondary", "#8B5CF6"),
                },
                "success": self.palette.get("success", "#22C55E"),
                "warning": self.palette.get("warning", "#F59E0B"),
                "error": self.palette.get("error", "#EF4444"),
            },
            "borderRadius": {k: v for k, v in self.geometry.items() if "radius" in k},
            "fontFamily": {k: [v] for k, v in self.typography.items() if "family" in k},
        }

    def to_json(self) -> dict:
        return {
            "meta": {"name": self.name, "vibe": self.vibe},
            "palette": self.palette,
            "geometry": self.geometry,
            "typography": self.typography,
            "effects": self.effects,
            "taste_vector": self.taste_vector,
        }

    def get_all_colors(self) -> Dict[str, str]:
        """Return all color values from palette for verification."""
        return {k: v for k, v in self.palette.items()}

    def get_spacing_grid(self) -> List[int]:
        """Generate valid spacing values from base."""
        base = int(self.geometry.get("spacing_base", "4").replace("px", ""))
        return [base * i for i in range(1, 25)]  # 4, 8, 12, ... 96

    def get_allowed_radii(self) -> List[str]:
        """Return all valid border-radius values."""
        return [v for k, v in self.geometry.items() if "radius" in k]

    def get_allowed_fonts(self) -> List[str]:
        """Return all valid font families."""
        fonts = []
        for k, v in self.typography.items():
            if "family" in k:
                for font in v.split(","):
                    fonts.append(font.strip().strip("'\""))
        return fonts

    @classmethod
    def from_json(cls, data: dict) -> "StyleTensor":
        meta = data.get("meta", {})
        return cls(
            name=meta.get("name", data.get("name", "Unknown")),
            palette=data.get("palette", {}),
            geometry=data.get("geometry", {}),
            typography=data.get("typography", {}),
            effects=data.get("effects", {}),
            taste_vector=data.get("taste_vector", {}),
            vibe=meta.get("vibe", data.get("vibe", "")),
        )

    @classmethod
    def from_file(cls, path: str) -> "StyleTensor":
        with open(path, "r") as f:
            return cls.from_json(json.load(f))


# ─── Built-in Profiles ───────────────────────────────────────────

PROFILES: Dict[str, dict] = {
    "linear": {
        "meta": {"name": "Linear Dark", "vibe": "Minimal, Professional, Calm"},
        "palette": {
            "bg_layer_0": "#09090B", "bg_layer_1": "#121214", "bg_layer_2": "#1A1A1C",
            "border_subtle": "rgba(255,255,255,0.06)", "border_active": "#5E6AD2",
            "text_primary": "#FAFAFA", "text_secondary": "#71717A", "text_tertiary": "#52525B",
            "accent_primary": "#5E6AD2", "accent_secondary": "#8B5CF6",
            "accent_glow": "rgba(94,106,210,0.3)",
            "success": "#22C55E", "warning": "#F59E0B", "error": "#EF4444", "info": "#3B82F6",
        },
        "geometry": {
            "radius_surface": "12px", "radius_inner": "8px",
            "radius_button": "6px", "radius_pill": "99px",
            "spacing_base": "4px",
        },
        "typography": {
            "family_sans": "Inter, system-ui, sans-serif",
            "family_mono": "JetBrains Mono, Menlo, Monaco, monospace",
            "weight_regular": "400", "weight_medium": "500",
            "weight_semibold": "600", "weight_bold": "700",
        },
        "effects": {
            "shadow_sm": "0 1px 2px 0 rgba(0,0,0,0.05)",
            "shadow_md": "0 4px 6px -1px rgba(0,0,0,0.1)",
            "transition": "all 150ms ease",
            "transition_fast": "all 100ms ease",
        },
        "taste_vector": {
            "temperature": 0.25, "density": 0.30, "formality": 0.80,
            "energy": 0.40, "age": 0.90, "price": 0.85,
        },
    },
    "cyberpunk": {
        "meta": {"name": "Cyberpunk", "vibe": "Dark, Neon, Angular"},
        "palette": {
            "bg_layer_0": "#000000", "bg_layer_1": "#0A0A0A", "bg_layer_2": "#141414",
            "border_subtle": "rgba(255,0,64,0.15)", "border_active": "#FF0040",
            "text_primary": "#FFFFFF", "text_secondary": "#888888", "text_tertiary": "#555555",
            "accent_primary": "#FF0040", "accent_secondary": "#00FFFF",
            "accent_glow": "rgba(255,0,64,0.4)",
            "success": "#00FF88", "warning": "#FFD700", "error": "#FF0040", "info": "#00FFFF",
        },
        "geometry": {
            "radius_surface": "0px", "radius_inner": "0px",
            "radius_button": "0px", "radius_pill": "0px",
            "spacing_base": "4px",
        },
        "typography": {
            "family_sans": "JetBrains Mono, Courier New, monospace",
            "family_mono": "JetBrains Mono, monospace",
            "weight_regular": "400", "weight_medium": "500",
            "weight_semibold": "600", "weight_bold": "700",
        },
        "effects": {
            "shadow_sm": "2px 2px 0 #FF0040",
            "shadow_md": "4px 4px 0 #FF0040",
            "transition": "all 100ms linear",
            "transition_fast": "all 50ms linear",
        },
        "taste_vector": {
            "temperature": 0.15, "density": 0.70, "formality": 0.40,
            "energy": 0.95, "age": 0.95, "price": 0.60,
        },
    },
    "soft": {
        "meta": {"name": "Soft Friendly", "vibe": "Warm, Round, Pastel"},
        "palette": {
            "bg_layer_0": "#FFF8F0", "bg_layer_1": "#FFFFFF", "bg_layer_2": "#FFF0E6",
            "border_subtle": "#F0E6DC", "border_active": "#FFB6C1",
            "text_primary": "#2D2D2D", "text_secondary": "#6B6B6B", "text_tertiary": "#999999",
            "accent_primary": "#FFB6C1", "accent_secondary": "#B6D4FF",
            "accent_glow": "rgba(255,182,193,0.2)",
            "success": "#88D4AB", "warning": "#FFD4A3", "error": "#FF9999", "info": "#A3C4FF",
        },
        "geometry": {
            "radius_surface": "24px", "radius_inner": "16px",
            "radius_button": "99px", "radius_pill": "99px",
            "spacing_base": "4px",
        },
        "typography": {
            "family_sans": "Nunito, system-ui, sans-serif",
            "family_mono": "Fira Code, monospace",
            "weight_regular": "400", "weight_medium": "600",
            "weight_semibold": "700", "weight_bold": "800",
        },
        "effects": {
            "shadow_sm": "0 2px 8px rgba(0,0,0,0.04)",
            "shadow_md": "0 8px 24px rgba(0,0,0,0.06)",
            "transition": "all 300ms cubic-bezier(0.34, 1.56, 0.64, 1)",
            "transition_fast": "all 200ms ease",
        },
        "taste_vector": {
            "temperature": 0.80, "density": 0.25, "formality": 0.30,
            "energy": 0.50, "age": 0.70, "price": 0.40,
        },
    },
    "minimal": {
        "meta": {"name": "Minimal", "vibe": "Clean, Sparse, Functional"},
        "palette": {
            "bg_layer_0": "#FFFFFF", "bg_layer_1": "#FAFAFA", "bg_layer_2": "#F5F5F5",
            "border_subtle": "#E5E5E5", "border_active": "#000000",
            "text_primary": "#171717", "text_secondary": "#525252", "text_tertiary": "#A3A3A3",
            "accent_primary": "#000000", "accent_secondary": "#404040",
            "accent_glow": "none",
            "success": "#16A34A", "warning": "#CA8A04", "error": "#DC2626", "info": "#2563EB",
        },
        "geometry": {
            "radius_surface": "8px", "radius_inner": "6px",
            "radius_button": "6px", "radius_pill": "99px",
            "spacing_base": "4px",
        },
        "typography": {
            "family_sans": "Inter, system-ui, sans-serif",
            "family_mono": "SF Mono, Menlo, monospace",
            "weight_regular": "400", "weight_medium": "500",
            "weight_semibold": "600", "weight_bold": "700",
        },
        "effects": {
            "shadow_sm": "0 1px 2px rgba(0,0,0,0.05)",
            "shadow_md": "0 4px 12px rgba(0,0,0,0.08)",
            "transition": "all 150ms ease",
            "transition_fast": "all 100ms ease",
        },
        "taste_vector": {
            "temperature": 0.50, "density": 0.15, "formality": 0.85,
            "energy": 0.20, "age": 0.85, "price": 0.70,
        },
    },
}


def load_profile(name: str) -> StyleTensor:
    """Load a design profile as a StyleTensor.
    
    Resolution order:
    1. Check profiles/ directory for {name}.json
    2. Fall back to built-in PROFILES dict
    """
    # Check for JSON file in profiles/ directory
    profiles_dir = Path(__file__).parent / "profiles"
    json_path = profiles_dir / f"{name}.json"
    if json_path.exists():
        return StyleTensor.from_file(str(json_path))

    # Fall back to built-in profiles
    if name not in PROFILES:
        available = list(PROFILES.keys())
        # Also list JSON profiles
        if profiles_dir.exists():
            for p in profiles_dir.glob("*.json"):
                available.append(p.stem)
        raise ValueError(f"Unknown profile '{name}'. Available: {', '.join(available)}")
    return StyleTensor.from_json(PROFILES[name])
