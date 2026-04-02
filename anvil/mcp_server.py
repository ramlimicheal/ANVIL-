"""
ANVIL MCP Server — Full parity with CLI. All 11 commands exposed as MCP tools.
Antigravity/Windsurf/Cursor can call these natively.

CLI → MCP mapping:
  anvil init          → anvil_init
  anvil taste         → anvil_taste
  anvil prove         → anvil_prove
  anvil compress      → anvil_compress
  anvil guard         → anvil_guard
  anvil score         → anvil_score
  anvil vision        → anvil_vision
  anvil extract       → anvil_extract
  anvil replicate     → anvil_replicate
  anvil generate      → anvil_generate
  anvil verify        → anvil_verify  (MCP-only: combined routing)
  anvil daemon        → (not exposed — MCP IS the daemon)

Usage:
  python3 /Users/apple/Desktop/Alpha/ANVIL/anvil/mcp_server.py
"""

import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anvil.config import AnvilConfig, detect_file_layer, anvil_grade

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


# ─── Shared helpers ───────────────────────────────────────────

def _create_guard(profile: str = "linear"):
    from anvil.watcher.guard import AnvilGuard
    config = AnvilConfig()
    config.taste.profile = profile
    return AnvilGuard(config)


# ─── Handler: init ────────────────────────────────────────────

def handle_anvil_init(project_path: str = ".", project_name: str = "") -> dict:
    """Initialize ANVIL config in a directory."""
    if not project_name:
        project_name = os.path.basename(os.path.abspath(project_path))

    config_path = os.path.join(project_path, "anvil.json")
    if os.path.exists(config_path):
        return {"status": "exists", "path": config_path, "message": "anvil.json already exists."}

    config = AnvilConfig(project_name=project_name, project_path=project_path)
    config.save(config_path)
    return {
        "status": "created",
        "path": config_path,
        "profile": config.taste.profile,
        "z3_provers": config.z3.enabled_provers,
        "compression_level": config.compression.level,
    }


# ─── Handler: taste ───────────────────────────────────────────

def handle_anvil_taste(code: str = "", filepath: str = "", profile: str = "linear") -> dict:
    """TASTE Guard — frontend design verification."""
    from anvil.taste.tensor import load_profile
    from anvil.taste.verifier import TasteVerifier

    # If filepath given and no code, read from file
    if filepath and not code and os.path.isfile(filepath):
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

    if not code:
        return {"error": "No code provided. Pass 'code' or 'filepath'."}

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
    }


# ─── Handler: prove ──────────────────────────────────────────

def handle_anvil_prove(code: str = "", filepath: str = "") -> dict:
    """Z3 Guard — backend logic proof."""
    from anvil.z3_guard.provers import AnvilZ3Guard

    if filepath and not code and os.path.isfile(filepath):
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

    if not code:
        return {"error": "No code provided. Pass 'code' or 'filepath'."}

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


# ─── Handler: compress ───────────────────────────────────────

def handle_anvil_compress(text: str = "", filepath: str = "", level: str = "medium") -> dict:
    """Semantic compression — reduce tokens."""
    from anvil.compress.engine import SemanticCompressor

    if filepath and not text and os.path.isfile(filepath):
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()

    if not text:
        return {"error": "No text provided. Pass 'text' or 'filepath'."}

    compressor = SemanticCompressor(level)
    result = compressor.compress(text)
    return {
        "compressed": result.compressed,
        "original_tokens": result.original_tokens,
        "compressed_tokens": result.compressed_tokens,
        "reduction_pct": result.reduction_pct,
        "techniques": result.techniques_applied,
    }


# ─── Handler: guard ──────────────────────────────────────────

def handle_anvil_guard(watch_path: str = ".", profile: str = "linear") -> dict:
    """Start file watcher. Returns immediately with status (watcher runs in background)."""
    # MCP tools are request-response, not long-running. So we verify the
    # directory once and return the results instead of blocking.
    from anvil.watcher.guard import AnvilGuard

    config = AnvilConfig()
    config.taste.profile = profile
    guard = AnvilGuard(config)

    abs_path = os.path.abspath(watch_path)
    if not os.path.isdir(abs_path):
        return {"error": f"Not a directory: {abs_path}"}

    results = guard.verify_directory(abs_path)

    file_reports = []
    for r in results[:20]:  # Cap at 20 files
        file_reports.append({
            "filepath": r.filepath,
            "layers": r.layers_run,
            "taste_score": r.taste_score,
            "z3_score": r.z3_score,
            "passed": r.passed,
            "summary": r.summary(),
        })

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    return {
        "watch_path": abs_path,
        "profile": profile,
        "total_files": total,
        "passed": passed,
        "failed": total - passed,
        "files": file_reports,
    }


# ─── Handler: score ──────────────────────────────────────────

def handle_anvil_score(code: str = "", filepath: str = "", profile: str = "linear") -> dict:
    """Combined ANVIL score with grade."""
    if filepath and not code and os.path.isfile(filepath):
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

    if not code:
        return {"error": "No code provided. Pass 'code' or 'filepath'."}

    guard = _create_guard(profile)
    result = guard.verify_code(code, filepath)
    scores = []
    if result.taste_score is not None:
        scores.append(result.taste_score)
    if result.z3_score is not None:
        scores.append(result.z3_score)

    combined = round(sum(scores) / max(len(scores), 1), 1) if scores else 0

    return {
        "anvil_score": combined,
        "grade": anvil_grade(combined),
        "taste_score": result.taste_score,
        "z3_score": result.z3_score,
        "passed": result.passed,
        "summary": result.summary(),
    }


# ─── Handler: vision ─────────────────────────────────────────

def handle_anvil_vision(reference_path: str, generated_path: str, diff_output: str = "") -> dict:
    """Visual fidelity comparison — SSIM, color distance, physics score."""
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
        "score": result.score,
        "passed": result.passed,
        "overall_ssim": result.overall_ssim,
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

def handle_anvil_extract(image_path: str, output_dir: str = "") -> dict:
    """Extract design system from screenshot."""
    if not os.path.exists(image_path):
        return {"error": f"Image not found: {image_path}"}

    if not output_dir:
        base = os.path.splitext(image_path)[0]
        output_dir = f"{base}_anvil_ds"

    from anvil.extract.compiler import extract_design_system, compile_design_system

    ds = extract_design_system(image_path)
    compile_design_system(ds, output_dir)

    ds_dict = ds.to_dict()
    return {
        "status": "success",
        "output_dir": output_dir,
        "files": [
            os.path.join(output_dir, "design_system.json"),
            os.path.join(output_dir, "tokens.css"),
            os.path.join(output_dir, "tailwind.config.js"),
            os.path.join(output_dir, "responsive.css"),
        ],
        "design_system": {
            "meta": ds_dict["meta"],
            "palette": ds_dict["palette"],
            "taste_vector": ds_dict["taste_vector"],
            "typography": {
                k: v for k, v in ds_dict["typography"].items()
                if not isinstance(v, (list, dict))
            },
            "components_found": ds_dict["components"]["types_found"],
            "total_icons": ds_dict["icons"]["total"],
        },
    }


# ─── Handler: replicate ──────────────────────────────────────

def handle_anvil_replicate(image_path: str, output_dir: str = "", max_iterations: int = 5) -> dict:
    """Full pipeline: screenshot → design system → verified code."""
    if not os.path.exists(image_path):
        return {"error": f"Image not found: {image_path}"}

    if not output_dir:
        base = os.path.splitext(image_path)[0]
        output_dir = f"{base}_replicated"

    from anvil.generate.loop import replicate

    result = replicate(image_path, output_dir, max_iterations=max_iterations)

    return {
        "status": "success" if result.verification.passed else "needs_refinement",
        "design_system_path": result.design_system_path,
        "html_path": result.html_path,
        "taste_score": result.verification.taste_score,
        "composite_score": result.verification.composite_score,
        "passed": result.verification.passed,
        "iterations": result.iterations,
        "total_time": result.total_time,
        "violations": result.verification.violations[:10],
        "output_dir": output_dir,
        "summary": result.summary(),
    }


# ─── Handler: generate ───────────────────────────────────────

def handle_anvil_generate(design_system_path: str, output_dir: str = "") -> dict:
    """Generate code from an existing design system JSON."""
    if not os.path.exists(design_system_path):
        return {"error": f"Design system not found: {design_system_path}"}

    if not output_dir:
        output_dir = os.path.dirname(design_system_path) or "."

    # Load the design system JSON and reconstruct the DesignSystem object
    with open(design_system_path, "r") as f:
        ds_json = json.load(f)

    from anvil.generate.engine import generate_html
    from anvil.extract.compiler import DesignSystem, extract_design_system

    # We need the full DesignSystem object, but generate from JSON is limited.
    # Check if there's a source image reference to re-extract from.
    # Otherwise, inform the user to use 'replicate' instead.
    return {
        "status": "info",
        "message": "Code generation from JSON requires the full DesignSystem object. "
                   "Use 'anvil_replicate' with the original screenshot for the full pipeline, "
                   "or 'anvil_extract' to create the design system first.",
        "design_system": ds_json.get("meta", {}),
        "taste_vector": ds_json.get("taste_vector", {}),
    }


# ─── Handler: verify (MCP-only combined routing) ─────────────

def handle_anvil_verify(code: str = "", filepath: str = "", profile: str = "linear") -> dict:
    """Full ANVIL verification — routes to correct layers."""
    if filepath and not code and os.path.isfile(filepath):
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

    if not code:
        return {"error": "No code provided. Pass 'code' or 'filepath'."}

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
        "details": {k: v for k, v in result.details.items()},
    }


# ─── Tool definitions ────────────────────────────────────────

TOOL_DEFS = [
    Tool(
        name="anvil_init",
        description="Initialize ANVIL config (anvil.json) in a project directory. "
                    "Creates design system profile, Z3 prover settings, and compression config.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Directory to initialize. Default: current dir."},
                "project_name": {"type": "string", "description": "Project name for config."},
            },
        },
    ),
    Tool(
        name="anvil_taste",
        description="TASTE Guard — verify frontend code against design system. "
                    "Checks colors, spacing, fonts, border-radius, WCAG accessibility, "
                    "inline style abuse, and 6D taste vector formality gate. "
                    "Pass code directly or give a filepath to read from disk.",
        inputSchema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "CSS/HTML/JSX code to check"},
                "filepath": {"type": "string", "description": "Absolute path to file (alternative to code)"},
                "profile": {"type": "string", "description": "Design profile: linear, cyberpunk, soft, minimal"},
            },
        },
    ),
    Tool(
        name="anvil_prove",
        description="Z3 Guard — mathematically prove backend code correctness. "
                    "Catches division by zero, integer overflow, auth bypass, "
                    "race conditions, null pointer, and bounds violations. "
                    "Pass code directly or give a filepath.",
        inputSchema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Backend code to verify"},
                "filepath": {"type": "string", "description": "Absolute path to file (alternative to code)"},
            },
        },
    ),
    Tool(
        name="anvil_compress",
        description="Semantic compression — reduce LLM prompt tokens while preserving meaning. "
                    "Applies identifier splitting, stop-word removal, whitespace normalization, "
                    "and structural compression. Pass text directly or give a filepath.",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to compress"},
                "filepath": {"type": "string", "description": "Absolute path to file (alternative to text)"},
                "level": {"type": "string", "description": "Compression level: light, medium, or aggressive"},
            },
        },
    ),
    Tool(
        name="anvil_guard",
        description="ANVIL Guard — verify all files in a directory through TASTE and Z3 layers. "
                    "Returns per-file scores, violations, and pass/fail status. "
                    "In MCP mode this runs a one-shot scan (CLI mode runs as a live watcher).",
        inputSchema={
            "type": "object",
            "properties": {
                "watch_path": {"type": "string", "description": "Absolute path to directory to scan"},
                "profile": {"type": "string", "description": "TASTE design profile to use"},
            },
        },
    ),
    Tool(
        name="anvil_score",
        description="Get combined ANVIL score (A+ to F) for any code. "
                    "Runs both TASTE and Z3 guards, combines scores, returns letter grade. "
                    "Pass code directly or give a filepath.",
        inputSchema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to score"},
                "filepath": {"type": "string", "description": "Absolute path to file (alternative to code)"},
            },
        },
    ),
    Tool(
        name="anvil_vision",
        description="Visual fidelity comparison — compare a reference screenshot against "
                    "a generated screenshot using SSIM, color histogram distance, edge "
                    "structure correlation, and photometric physics verification. "
                    "Returns per-region scores identifying exactly WHERE the UI differs.",
        inputSchema={
            "type": "object",
            "properties": {
                "reference_path": {"type": "string", "description": "Absolute path to reference screenshot (the target design)"},
                "generated_path": {"type": "string", "description": "Absolute path to generated screenshot (what the AI built)"},
                "diff_output": {"type": "string", "description": "Optional: path to save visual diff image"},
            },
            "required": ["reference_path", "generated_path"],
        },
    ),
    Tool(
        name="anvil_extract",
        description="Extract complete design system from a screenshot. "
                    "Uses OpenCV computer vision to detect: color palette (with dark/light mode), "
                    "typography classification and scale, spacing grid, visual effects "
                    "(gradients, glassmorphism, shadows), component catalog (cards, buttons, badges), "
                    "icon analysis, and responsive framework. "
                    "Outputs: design_system.json, tokens.css, tailwind.config.js, responsive.css.",
        inputSchema={
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "Absolute path to screenshot PNG/JPG"},
                "output_dir": {"type": "string", "description": "Directory for output files (default: auto-named)"},
            },
            "required": ["image_path"],
        },
    ),
    Tool(
        name="anvil_replicate",
        description="Full replication pipeline: screenshot → design system → verified code. "
                    "Phase 1: Extract design system (palette, typography, spacing, effects, components). "
                    "Phase 2: Compile to tokens (CSS vars, Tailwind config). "
                    "Phase 3: Generate semantic HTML/CSS from extracted structure. "
                    "Phase 4: TASTE verification with iterative refinement (up to N iterations). "
                    "Returns generated HTML path, design system, scores, and violations.",
        inputSchema={
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "Absolute path to reference screenshot"},
                "output_dir": {"type": "string", "description": "Directory for generated output"},
                "max_iterations": {"type": "integer", "description": "Max refinement iterations (default: 5)"},
            },
            "required": ["image_path"],
        },
    ),
    Tool(
        name="anvil_generate",
        description="Generate code from an existing design system JSON. "
                    "Requires a prior 'anvil_extract' or 'anvil_replicate' run. "
                    "For full pipeline from screenshot, use 'anvil_replicate' instead.",
        inputSchema={
            "type": "object",
            "properties": {
                "design_system_path": {"type": "string", "description": "Path to design_system.json"},
                "output_dir": {"type": "string", "description": "Directory for generated code"},
            },
            "required": ["design_system_path"],
        },
    ),
    Tool(
        name="anvil_verify",
        description="Full ANVIL verification. Routes frontend code to TASTE Guard, "
                    "backend code to Z3 Guard based on file extension. Returns scores and violations. "
                    "Pass code directly or give a filepath.",
        inputSchema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to verify"},
                "filepath": {"type": "string", "description": "Filename or path (for routing: .css→TASTE, .py→Z3)"},
                "profile": {"type": "string", "description": "Design profile: linear, cyberpunk, soft, minimal"},
            },
        },
    ),
]


# ─── Handler dispatch table ───────────────────────────────────

HANDLERS = {
    "anvil_init": lambda a: handle_anvil_init(
        a.get("project_path", "."), a.get("project_name", "")),
    "anvil_taste": lambda a: handle_anvil_taste(
        a.get("code", ""), a.get("filepath", ""), a.get("profile", "linear")),
    "anvil_prove": lambda a: handle_anvil_prove(
        a.get("code", ""), a.get("filepath", "")),
    "anvil_compress": lambda a: handle_anvil_compress(
        a.get("text", ""), a.get("filepath", ""), a.get("level", "medium")),
    "anvil_guard": lambda a: handle_anvil_guard(
        a.get("watch_path", "."), a.get("profile", "linear")),
    "anvil_score": lambda a: handle_anvil_score(
        a.get("code", ""), a.get("filepath", ""), a.get("profile", "linear")),
    "anvil_vision": lambda a: handle_anvil_vision(
        a["reference_path"], a["generated_path"], a.get("diff_output", "")),
    "anvil_extract": lambda a: handle_anvil_extract(
        a["image_path"], a.get("output_dir", "")),
    "anvil_replicate": lambda a: handle_anvil_replicate(
        a["image_path"], a.get("output_dir", ""), a.get("max_iterations", 5)),
    "anvil_generate": lambda a: handle_anvil_generate(
        a["design_system_path"], a.get("output_dir", "")),
    "anvil_verify": lambda a: handle_anvil_verify(
        a.get("code", ""), a.get("filepath", ""), a.get("profile", "linear")),
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
                "error": str(e),
                "traceback": traceback.format_exc(),
            }))]

    async def main():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())


# ─── Standalone JSON-RPC fallback ─────────────────────────────

def jsonrpc_loop():
    """Simple JSON-RPC over stdin/stdout for IDEs without MCP package."""
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
                result = {"error": f"Unknown method: {method}",
                          "available": list(HANDLERS.keys())}

            response = json.dumps({"id": req.get("id"), "result": result}, default=str)
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
