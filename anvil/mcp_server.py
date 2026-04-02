"""
ANVIL MCP Server — Exposes ANVIL as Model Context Protocol tools.
Antigravity/Windsurf/Cursor can call these natively.

Usage:
  python3 /Users/apple/Desktop/Alpha/ANVIL/anvil/mcp_server.py
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anvil.config import AnvilConfig, detect_file_layer
from anvil.taste.tensor import load_profile, StyleTensor
from anvil.taste.verifier import TasteVerifier
from anvil.taste.scorer import AestheticScorer
from anvil.z3_guard.provers import AnvilZ3Guard
from anvil.compress.engine import SemanticCompressor
from anvil.watcher.guard import AnvilGuard

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


# ─── Fallback: JSON-RPC over stdio if mcp package not installed ───

def _create_guard(profile: str = "linear") -> AnvilGuard:
    config = AnvilConfig()
    config.taste.profile = profile
    return AnvilGuard(config)


def handle_anvil_verify(code: str, filepath: str = "", profile: str = "linear") -> dict:
    """Full ANVIL verification — routes to correct layers."""
    guard = _create_guard(profile)
    result = guard.verify_code(code, filepath)
    return {
        "filepath": result.filepath,
        "layers_run": result.layers_run,
        "passed": result.passed,
        "taste_score": result.taste_score,
        "z3_score": result.z3_score,
        "taste_violations": result.taste_violations,
        "z3_bugs": result.z3_bugs,
        "summary": result.summary(),
        "details": {
            k: v for k, v in result.details.items()
        },
    }


def handle_anvil_taste(code: str, filepath: str = "", profile: str = "linear") -> dict:
    """TASTE Guard only — frontend design verification."""
    tensor = load_profile(profile)
    verifier = TasteVerifier(tensor)
    result = verifier.score(code)
    return {
        "score": result["score"],
        "pass": result["pass"],
        "errors": result["errors"],
        "warnings": result["warnings"],
        "total_violations": result["total_violations"],
        "violations": [str(v) for v in result["violations"][:15]],
        "profile": profile,
    }


def handle_anvil_prove(code: str, filepath: str = "") -> dict:
    """Z3 Guard only — backend logic proof."""
    guard = AnvilZ3Guard()
    result = guard.score(code, filepath)
    return {
        "score": result["score"],
        "pass": result["pass"],
        "bugs_found": result["bugs_found"],
        "proven_safe": result["proven_safe"],
        "total_checks": result["total_checks"],
        "results": [str(r) for r in result["results"][:15]],
    }


def handle_anvil_compress(text: str, level: str = "medium") -> dict:
    """Semantic compression — reduce tokens."""
    compressor = SemanticCompressor(level)
    result = compressor.compress(text)
    return {
        "compressed": result.compressed,
        "original_tokens": result.original_tokens,
        "compressed_tokens": result.compressed_tokens,
        "reduction_pct": result.reduction_pct,
        "techniques": result.techniques_applied,
    }


def handle_anvil_score(code: str, filepath: str = "", profile: str = "linear") -> dict:
    """Combined ANVIL score with grade."""
    guard = _create_guard(profile)
    result = guard.verify_code(code, filepath)
    scores = []
    if result.taste_score is not None:
        scores.append(result.taste_score)
    if result.z3_score is not None:
        scores.append(result.z3_score)

    combined = round(sum(scores) / max(len(scores), 1), 1) if scores else 0

    def grade(s):
        if s >= 9.0: return "A+"
        if s >= 8.0: return "A"
        if s >= 7.0: return "B"
        if s >= 6.0: return "C"
        if s >= 4.0: return "D"
        return "F"

    return {
        "anvil_score": combined,
        "grade": grade(combined),
        "taste_score": result.taste_score,
        "z3_score": result.z3_score,
        "passed": result.passed,
        "summary": result.summary(),
    }


# ─── MCP Server (if mcp package available) ────────────────────

if HAS_MCP:
    server = Server("anvil")

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name="anvil_verify",
                description="Full ANVIL verification. Routes frontend code to TASTE Guard, "
                            "backend code to Z3 Guard. Returns scores and violations.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Code to verify"},
                        "filepath": {"type": "string", "description": "Filename (for routing: .css→TASTE, .py→Z3)"},
                        "profile": {"type": "string", "description": "Design profile: linear, cyberpunk, soft, minimal"},
                    },
                    "required": ["code"],
                },
            ),
            Tool(
                name="anvil_taste",
                description="TASTE Guard — verify frontend code against design system. "
                            "Checks colors, spacing, fonts, WCAG accessibility.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "CSS/HTML/JSX code to check"},
                        "profile": {"type": "string", "description": "Design profile: linear, cyberpunk, soft, minimal"},
                    },
                    "required": ["code"],
                },
            ),
            Tool(
                name="anvil_prove",
                description="Z3 Guard — mathematically prove backend code correctness. "
                            "Catches division by zero, overflow, auth bugs, race conditions.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Backend code to verify"},
                        "filepath": {"type": "string", "description": "Filename for context"},
                    },
                    "required": ["code"],
                },
            ),
            Tool(
                name="anvil_compress",
                description="Semantic compression — reduce LLM prompt tokens while preserving meaning.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to compress"},
                        "level": {"type": "string", "description": "light, medium, or aggressive"},
                    },
                    "required": ["text"],
                },
            ),
            Tool(
                name="anvil_score",
                description="Get combined ANVIL score (A+ to F) for any code.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Code to score"},
                        "filepath": {"type": "string", "description": "Filename"},
                    },
                    "required": ["code"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        handlers = {
            "anvil_verify": lambda a: handle_anvil_verify(
                a["code"], a.get("filepath", ""), a.get("profile", "linear")),
            "anvil_taste": lambda a: handle_anvil_taste(
                a["code"], a.get("filepath", ""), a.get("profile", "linear")),
            "anvil_prove": lambda a: handle_anvil_prove(
                a["code"], a.get("filepath", "")),
            "anvil_compress": lambda a: handle_anvil_compress(
                a["text"], a.get("level", "medium")),
            "anvil_score": lambda a: handle_anvil_score(
                a["code"], a.get("filepath", "")),
        }

        if name not in handlers:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        result = handlers[name](arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    async def main():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())


# ─── Standalone JSON-RPC fallback ──────────────────────────────

def jsonrpc_loop():
    """Simple JSON-RPC over stdin/stdout for IDEs without MCP package."""
    sys.stderr.write("[ANVIL MCP] Server running (JSON-RPC mode)\n")
    for line in sys.stdin:
        try:
            req = json.loads(line.strip())
            method = req.get("method", "")
            params = req.get("params", {})
            result = None

            if method == "anvil_verify":
                result = handle_anvil_verify(**params)
            elif method == "anvil_taste":
                result = handle_anvil_taste(**params)
            elif method == "anvil_prove":
                result = handle_anvil_prove(**params)
            elif method == "anvil_compress":
                result = handle_anvil_compress(**params)
            elif method == "anvil_score":
                result = handle_anvil_score(**params)
            else:
                result = {"error": f"Unknown method: {method}"}

            response = json.dumps({"id": req.get("id"), "result": result})
            sys.stdout.write(response + "\n")
            sys.stdout.flush()
        except Exception as e:
            err = json.dumps({"error": str(e)})
            sys.stdout.write(err + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    if HAS_MCP:
        import asyncio
        asyncio.run(main())
    else:
        jsonrpc_loop()
