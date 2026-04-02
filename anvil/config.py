"""
ANVIL Configuration — Project-level settings and design system loader.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path

ANVIL_DIR = Path(__file__).parent.parent
DEFAULT_CONFIG_NAME = "anvil.json"

# File extension routing
FRONTEND_EXTENSIONS = {".css", ".scss", ".less", ".jsx", ".tsx", ".vue", ".svelte", ".html"}
BACKEND_EXTENSIONS = {".py", ".js", ".ts", ".go", ".sol", ".rs", ".java"}
STYLE_EXTENSIONS = {".css", ".scss", ".less"}

LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".go": "go",
    ".sol": "solidity",
    ".rs": "rust",
    ".java": "java",
    ".vue": "vue",
    ".svelte": "svelte",
}


@dataclass
class TasteConfig:
    """Design system configuration for TASTE Guard."""
    profile: str = "linear"
    spacing_base: int = 4
    allowed_fonts: List[str] = field(default_factory=lambda: ["Inter", "system-ui", "sans-serif"])
    allowed_colors: Dict[str, str] = field(default_factory=dict)
    border_radii: Dict[str, str] = field(default_factory=dict)
    wcag_level: str = "AA"
    custom_tensor_path: Optional[str] = None


@dataclass
class Z3Config:
    """Z3 Guard configuration."""
    enabled_provers: List[str] = field(default_factory=lambda: [
        "math", "auth", "bounds", "concurrency", "nullcheck"
    ])
    timeout_ms: int = 5000
    bitvec_width: int = 256
    strict_mode: bool = False


@dataclass
class CompressionConfig:
    """Semantic Compression configuration."""
    level: str = "medium"  # light, medium, aggressive
    preserve_comments: bool = True
    preserve_docstrings: bool = True
    target_reduction: float = 0.30


@dataclass
class AnvilConfig:
    """Root ANVIL configuration."""
    project_name: str = "untitled"
    project_path: str = "."
    taste: TasteConfig = field(default_factory=TasteConfig)
    z3: Z3Config = field(default_factory=Z3Config)
    compression: CompressionConfig = field(default_factory=CompressionConfig)
    watch_paths: List[str] = field(default_factory=lambda: ["src/", "app/", "lib/", "pages/"])
    ignore_patterns: List[str] = field(default_factory=lambda: [
        "node_modules", "__pycache__", ".git", "dist", "build", ".next", "venv"
    ])

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "AnvilConfig":
        """Load config from anvil.json or return defaults."""
        if config_path is None:
            config_path = os.path.join(os.getcwd(), DEFAULT_CONFIG_NAME)

        if not os.path.exists(config_path):
            return cls()

        with open(config_path, "r") as f:
            data = json.load(f)

        taste_data = data.get("taste", {})
        z3_data = data.get("z3", {})
        comp_data = data.get("compression", {})

        return cls(
            project_name=data.get("project_name", "untitled"),
            project_path=data.get("project_path", "."),
            taste=TasteConfig(**taste_data) if taste_data else TasteConfig(),
            z3=Z3Config(**z3_data) if z3_data else Z3Config(),
            compression=CompressionConfig(**comp_data) if comp_data else CompressionConfig(),
            watch_paths=data.get("watch_paths", ["src/", "app/", "lib/", "pages/"]),
            ignore_patterns=data.get("ignore_patterns", [
                "node_modules", "__pycache__", ".git", "dist", "build", ".next", "venv"
            ]),
        )

    def save(self, config_path: Optional[str] = None):
        """Save config to anvil.json."""
        if config_path is None:
            config_path = os.path.join(os.getcwd(), DEFAULT_CONFIG_NAME)

        data = {
            "project_name": self.project_name,
            "project_path": self.project_path,
            "taste": {
                "profile": self.taste.profile,
                "spacing_base": self.taste.spacing_base,
                "allowed_fonts": self.taste.allowed_fonts,
                "allowed_colors": self.taste.allowed_colors,
                "border_radii": self.taste.border_radii,
                "wcag_level": self.taste.wcag_level,
            },
            "z3": {
                "enabled_provers": self.z3.enabled_provers,
                "timeout_ms": self.z3.timeout_ms,
                "strict_mode": self.z3.strict_mode,
            },
            "compression": {
                "level": self.compression.level,
                "preserve_comments": self.compression.preserve_comments,
                "target_reduction": self.compression.target_reduction,
            },
            "watch_paths": self.watch_paths,
            "ignore_patterns": self.ignore_patterns,
        }

        os.makedirs(os.path.dirname(config_path) or ".", exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)


def detect_file_layer(filepath: str) -> str:
    """Route a file to the correct ANVIL layer based on extension."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext in STYLE_EXTENSIONS:
        return "taste"
    elif ext in FRONTEND_EXTENSIONS:
        return "both"  # Frontend files need TASTE + Z3
    elif ext in BACKEND_EXTENSIONS:
        return "z3"
    return "unknown"
