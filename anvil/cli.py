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

    def grade(s):
        if s >= 9.0: return "A+"
        if s >= 8.0: return "A"
        if s >= 7.0: return "B"
        if s >= 6.0: return "C"
        if s >= 4.0: return "D"
        return "F"

    print(f"\n  ⚒️  ANVIL SCORE: {combined}/10 ({grade(combined)})")
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
        "daemon": cmd_daemon,
    }

    if command in commands:
        commands[command](args)
    else:
        print(f"  Unknown command: {command}")
        print(f"  Available: {', '.join(commands.keys())}")


if __name__ == "__main__":
    main()
