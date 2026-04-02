"""
ANVIL CLI — Unified command-line interface.
Commands: taste, prove, compress, guard, score, init, daemon
"""

import sys
import os
import json
import time
from pathlib import Path


def print_banner():
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  ⚒️  ANVIL — Forge AI Code Into Production Steel")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def cmd_init(args):
    """Initialize ANVIL config in current directory."""
    from .config import AnvilConfig
    config = AnvilConfig(project_name=os.path.basename(os.getcwd()))
    config_path = os.path.join(os.getcwd(), "anvil.json")
    if os.path.exists(config_path):
        print(f"[ANVIL] anvil.json already exists at {config_path}")
        return
    config.save(config_path)
    print(f"[ANVIL] Created anvil.json")
    print(f"  Profile: {config.taste.profile}")
    print(f"  Z3 Provers: {', '.join(config.z3.enabled_provers)}")
    print(f"  Compression: {config.compression.level}")


def cmd_taste(args):
    """Run TASTE Guard on a file or directory."""
    if not args:
        print("Usage: anvil taste <file_or_dir> [--profile linear]")
        return

    target = args[0]
    profile = "linear"
    if "--profile" in args:
        idx = args.index("--profile")
        if idx + 1 < len(args):
            profile = args[idx + 1]

    from .taste.tensor import load_profile
    from .taste.verifier import TasteVerifier

    tensor = load_profile(profile)
    verifier = TasteVerifier(tensor)

    if os.path.isfile(target):
        _taste_file(verifier, target, profile)
    elif os.path.isdir(target):
        _taste_dir(verifier, target, profile)
    else:
        print(f"[ANVIL] Not found: {target}")


def _taste_file(verifier, filepath, profile):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        code = f.read()

    result = verifier.score(code)
    _print_taste_result(filepath, result, profile)


def _taste_dir(verifier, dirpath, profile):
    from .config import FRONTEND_EXTENSIONS, STYLE_EXTENSIONS
    extensions = FRONTEND_EXTENSIONS | STYLE_EXTENSIONS
    total_score = 0
    file_count = 0

    for root, dirs, files in os.walk(dirpath):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__", ".git", "dist", "build")]
        for fname in files:
            if os.path.splitext(fname)[1].lower() in extensions:
                fpath = os.path.join(root, fname)
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    code = f.read()
                result = verifier.score(code)
                _print_taste_result(fpath, result, profile)
                total_score += result["score"]
                file_count += 1

    if file_count:
        avg = round(total_score / file_count, 1)
        print(f"\n  AVERAGE TASTE SCORE: {avg}/10 across {file_count} files")


def _print_taste_result(filepath, result, profile):
    icon = "✅" if result["pass"] else "❌"
    print(f"\n  {icon} TASTE [{profile}] {filepath}")
    print(f"    Score: {result['score']}/10")
    print(f"    Errors: {result['errors']} | Warnings: {result['warnings']} | Info: {result['infos']}")
    for v in result["violations"][:5]:
        print(f"    → {v}")
    if result["total_violations"] > 5:
        print(f"    ... and {result['total_violations'] - 5} more")


def cmd_prove(args):
    """Run Z3 Guard on a file or directory."""
    if not args:
        print("Usage: anvil prove <file_or_dir>")
        return

    target = args[0]
    from .z3_guard.provers import AnvilZ3Guard
    guard = AnvilZ3Guard()

    if os.path.isfile(target):
        _prove_file(guard, target)
    elif os.path.isdir(target):
        _prove_dir(guard, target)
    else:
        print(f"[ANVIL] Not found: {target}")


def _prove_file(guard, filepath):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        code = f.read()

    result = guard.score(code, filepath)
    _print_z3_result(filepath, result)


def _prove_dir(guard, dirpath):
    from .config import BACKEND_EXTENSIONS
    total_score = 0
    file_count = 0

    for root, dirs, files in os.walk(dirpath):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__", ".git", "dist", "build", "venv")]
        for fname in files:
            if os.path.splitext(fname)[1].lower() in BACKEND_EXTENSIONS:
                fpath = os.path.join(root, fname)
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    code = f.read()
                result = guard.score(code, fpath)
                _print_z3_result(fpath, result)
                total_score += result["score"]
                file_count += 1

    if file_count:
        avg = round(total_score / file_count, 1)
        print(f"\n  AVERAGE Z3 SCORE: {avg}/10 across {file_count} files")


def _print_z3_result(filepath, result):
    icon = "✅" if result["pass"] else "❌"
    print(f"\n  {icon} Z3 {filepath}")
    print(f"    Score: {result['score']}/10")
    print(f"    Bugs: {result['bugs_found']} | Safe: {result['proven_safe']} | Checks: {result['total_checks']}")
    for r in result["results"][:5]:
        print(f"    → {r}")


def cmd_compress(args):
    """Compress text from file or stdin."""
    from .compress.engine import SemanticCompressor

    level = "medium"
    if "--level" in args:
        idx = args.index("--level")
        if idx + 1 < len(args):
            level = args[idx + 1]
            args = [a for i, a in enumerate(args) if i != idx and i != idx + 1]

    compressor = SemanticCompressor(level)

    if args and os.path.isfile(args[0]):
        with open(args[0], "r") as f:
            text = f.read()
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        print("Usage: anvil compress <file> [--level medium]")
        print("       echo 'text' | anvil compress --level aggressive")
        return

    result = compressor.compress(text)
    print(f"\n  COMPRESSION [{level}]")
    print(f"    Original:   {result.original_tokens} tokens")
    print(f"    Compressed: {result.compressed_tokens} tokens")
    print(f"    Reduction:  {result.reduction_pct}%")
    print(f"    Techniques: {', '.join(result.techniques_applied)}")
    print(f"\n  ─── Compressed Output ───")
    print(result.compressed)


def cmd_guard(args):
    """Start file watcher (ANVIL Guard)."""
    from .config import AnvilConfig
    from .watcher.guard import start_watcher

    watch_path = args[0] if args else "."
    config = AnvilConfig.load()
    start_watcher(config, watch_path)


def cmd_score(args):
    """Get combined ANVIL score for a file."""
    if not args:
        print("Usage: anvil score <file>")
        return

    from .config import AnvilConfig
    from .watcher.guard import AnvilGuard

    config = AnvilConfig.load()
    guard = AnvilGuard(config)
    result = guard.verify_file(args[0])

    scores = []
    if result.taste_score is not None:
        scores.append(result.taste_score)
    if result.z3_score is not None:
        scores.append(result.z3_score)

    combined = round(sum(scores) / max(len(scores), 1), 1) if scores else 0

    from .config import anvil_grade

    print(f"\n  ⚒️  ANVIL SCORE: {combined}/10 ({anvil_grade(combined)})")
    print(result.summary())


def cmd_daemon(args):
    """Start the ANVIL daemon."""
    from .config import AnvilConfig
    from .daemon import run_daemon

    port = 8084
    if "--port" in args:
        idx = args.index("--port")
        if idx + 1 < len(args):
            port = int(args[idx + 1])

    config = AnvilConfig.load()
    run_daemon(port=port, config=config)


def cmd_vision(args):
    """Compare generated HTML against a reference screenshot."""
    import os
    if len(args) < 2:
        print("Usage: anvil vision <reference.png> <generated.html> [--diff output.png]")
        print("       anvil vision <reference.png> <screenshot.png> [--diff output.png]")
        return

    reference = args[0]
    target = args[1]
    diff_path = None
    if "--diff" in args:
        idx = args.index("--diff")
        if idx + 1 < len(args):
            diff_path = args[idx + 1]

    viewport = (1440, 900)
    if "--viewport" in args:
        idx = args.index("--viewport")
        if idx + 1 < len(args):
            parts = args[idx + 1].split("x")
            viewport = (int(parts[0]), int(parts[1]))

    from .vision.compare import VisualComparator

    comparator = VisualComparator()

    # If target is HTML, capture screenshot first
    generated_png = target
    tmp_screenshot = None
    if target.endswith((".html", ".htm")):
        from .vision.capture import capture_html_to_png
        tmp_screenshot = target.replace(".html", "_anvil_capture.png").replace(".htm", "_anvil_capture.png")
        print(f"  📸 Capturing screenshot: {os.path.basename(target)}")
        print(f"     Viewport: {viewport[0]}x{viewport[1]}")
        capture_html_to_png(target, tmp_screenshot, viewport=viewport)
        generated_png = tmp_screenshot
        print(f"     Saved: {tmp_screenshot}")

    # Compare
    print(f"\n  🔍 Comparing against reference...")
    if not diff_path:
        import os
        base, ext = os.path.splitext(reference)
        diff_path = f"{base}_anvil_diff{ext if ext else '.png'}"

    result = comparator.compare(reference, generated_png, diff_output_path=diff_path)

    # Output
    print(f"\n{result.summary()}")

    # Detailed region report
    if result.region_scores:
        print(f"\n  Region Analysis ({len(result.region_scores)} zones):")
        sorted_regions = sorted(result.region_scores, key=lambda r: r.ssim)
        for r in sorted_regions:
            if r.ssim >= 0.90:
                icon = "✅"
            elif r.ssim >= 0.70:
                icon = "⚠️"
            else:
                icon = "❌"
            print(f"    {icon} {r.label:20s} SSIM={r.ssim:.4f}")


def cmd_extract(args):
    """Extract design system from a screenshot."""
    if not args:
        print("Usage: anvil extract <screenshot.png> [--output ./output/]")
        return

    image_path = args[0]
    output_dir = "./anvil_output"
    if "--output" in args:
        idx = args.index("--output")
        if idx + 1 < len(args):
            output_dir = args[idx + 1]

    from .extract.compiler import extract_design_system, compile_design_system

    ds = extract_design_system(image_path)
    print("\n  Compiling design system...")
    compile_design_system(ds, output_dir)
    print(f"\n  ✅ Design system extracted to: {output_dir}/")


def cmd_replicate(args):
    """Full pipeline: screenshot → design system → verified code."""
    if not args:
        print("Usage: anvil replicate <screenshot.png> [--output ./output/]")
        return

    image_path = args[0]
    output_dir = "./anvil_output"
    if "--output" in args:
        idx = args.index("--output")
        if idx + 1 < len(args):
            output_dir = args[idx + 1]

    from .generate.loop import replicate
    replicate(image_path, output_dir)


def cmd_generate(args):
    """Generate code from an existing design system JSON."""
    if not args:
        print("Usage: anvil generate <design_system.json> [--output ./output/]")
        return

    ds_path = args[0]
    output_dir = "./anvil_output"
    if "--output" in args:
        idx = args.index("--output")
        if idx + 1 < len(args):
            output_dir = args[idx + 1]

    print(f"  Loading design system from: {ds_path}")
    print(f"  [NOTE] Code generation from JSON requires a prior 'anvil extract' run.")
    print(f"  Use 'anvil replicate <screenshot>' for the full pipeline.")


def main():
    """ANVIL CLI entry point."""
    if len(sys.argv) < 2:
        print_banner()
        print("  Commands:")
        print("    anvil init                    — Create anvil.json config")
        print("    anvil taste <file|dir>        — Frontend design verification")
        print("    anvil prove <file|dir>        — Backend Z3 logic proof")
        print("    anvil compress <file>         — Semantic token compression")
        print("    anvil guard [path]            — Watch files, verify on save")
        print("    anvil score <file>            — Combined ANVIL score")
        print("    anvil vision <ref> <target>   — Pixel-level visual comparison")
        print("    anvil extract <screenshot>    — Extract design system from image")
        print("    anvil replicate <screenshot>  — Full pipeline: extract + generate + verify")
        print("    anvil generate <ds.json>      — Generate code from design system")
        print("    anvil daemon [--port 8084]    — Start REST API server")
        print("")
        return

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    print_banner()

    commands = {
        "init": cmd_init,
        "taste": cmd_taste,
        "prove": cmd_prove,
        "compress": cmd_compress,
        "guard": cmd_guard,
        "score": cmd_score,
        "vision": cmd_vision,
        "extract": cmd_extract,
        "replicate": cmd_replicate,
        "generate": cmd_generate,
        "daemon": cmd_daemon,
    }

    if command in commands:
        commands[command](args)
    else:
        print(f"  Unknown command: {command}")
        print(f"  Available: {', '.join(commands.keys())}")


if __name__ == "__main__":
    main()
