"""
ANVIL File Watcher — Monitors file saves and routes to correct verification layer.
Frontend files → TASTE Guard, Backend files → Z3 Guard, Both for mixed files.
"""

import os
import sys
import time
import json
from pathlib import Path
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field

from ..config import detect_file_layer, AnvilConfig, FRONTEND_EXTENSIONS, BACKEND_EXTENSIONS

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False


@dataclass
class GuardResult:
    """Combined result from all layers for a single file."""
    filepath: str
    layers_run: List[str]
    taste_score: Optional[float] = None
    z3_score: Optional[float] = None
    taste_violations: int = 0
    z3_bugs: int = 0
    passed: bool = True
    details: Dict = field(default_factory=dict)
    timestamp: float = 0.0

    def summary(self) -> str:
        parts = [f"ANVIL ━━━ {os.path.basename(self.filepath)}"]
        if "taste" in self.layers_run:
            icon = "✅" if (self.taste_score or 0) >= 6.0 else "⚠️"
            parts.append(f"  TASTE  {icon} {self.taste_score}/10 ({self.taste_violations} violations)")
        if "z3" in self.layers_run:
            icon = "✅" if (self.z3_score or 0) >= 6.0 else "⚠️"
            parts.append(f"  Z3     {icon} {self.z3_score}/10 ({self.z3_bugs} bugs)")
        status = "✅ PASS" if self.passed else "❌ BLOCKED"
        parts.append(f"  STATUS {status}")
        parts.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(parts)


class AnvilGuard:
    """Core guard that routes files to verification layers."""

    def __init__(self, config: Optional[AnvilConfig] = None):
        self.config = config or AnvilConfig()
        self._taste_verifier = None
        self._z3_guard = None
        self._init_layers()

    def _init_layers(self):
        """Initialize verification layers."""
        # Layer 1: TASTE
        try:
            from ..taste.tensor import load_profile
            from ..taste.verifier import TasteVerifier
            tensor = load_profile(self.config.taste.profile)
            self._taste_verifier = TasteVerifier(tensor)
        except Exception as e:
            print(f"[ANVIL] TASTE init warning: {e}")

        # Layer 2: Z3
        try:
            from ..z3_guard.provers import AnvilZ3Guard
            self._z3_guard = AnvilZ3Guard(
                enabled_provers=self.config.z3.enabled_provers,
                timeout_ms=self.config.z3.timeout_ms,
            )
        except Exception as e:
            print(f"[ANVIL] Z3 init warning: {e}")

    def verify_file(self, filepath: str) -> GuardResult:
        """Verify a single file through appropriate layers."""
        if not os.path.exists(filepath):
            return GuardResult(filepath=filepath, layers_run=[], passed=True)

        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

        return self.verify_code(code, filepath)

    def verify_code(self, code: str, filepath: str = "") -> GuardResult:
        """Verify code string through appropriate layers."""
        layer = detect_file_layer(filepath)
        layers_run = []
        result = GuardResult(
            filepath=filepath,
            layers_run=[],
            timestamp=time.time(),
        )

        # Route to TASTE
        if layer in ("taste", "both") and self._taste_verifier:
            taste_result = self._taste_verifier.score(code)
            result.taste_score = taste_result["score"]
            result.taste_violations = taste_result["total_violations"]
            result.details["taste"] = {
                "score": taste_result["score"],
                "pass": taste_result["pass"],
                "errors": taste_result["errors"],
                "warnings": taste_result["warnings"],
                "violations": [str(v) for v in taste_result["violations"][:10]],
            }
            layers_run.append("taste")

        # Route to Z3
        if layer in ("z3", "both") and self._z3_guard:
            z3_result = self._z3_guard.score(code, filepath)
            result.z3_score = z3_result["score"]
            result.z3_bugs = z3_result["bugs_found"]
            result.details["z3"] = {
                "score": z3_result["score"],
                "pass": z3_result["pass"],
                "bugs_found": z3_result["bugs_found"],
                "results": [str(r) for r in z3_result["results"][:10]],
            }
            layers_run.append("z3")

        result.layers_run = layers_run

        # Overall pass: all layers must pass
        taste_ok = result.taste_score is None or result.taste_score >= 6.0
        z3_ok = result.z3_score is None or result.z3_score >= 6.0
        result.passed = taste_ok and z3_ok

        return result

    def verify_directory(self, dirpath: str) -> List[GuardResult]:
        """Verify all files in a directory."""
        results = []
        all_ext = FRONTEND_EXTENSIONS | BACKEND_EXTENSIONS

        for root, dirs, files in os.walk(dirpath):
            # Skip ignored directories
            dirs[:] = [d for d in dirs if d not in self.config.ignore_patterns]

            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext in all_ext:
                    fpath = os.path.join(root, fname)
                    result = self.verify_file(fpath)
                    if result.layers_run:
                        results.append(result)

        return results


if HAS_WATCHDOG:
    class AnvilWatchHandler(FileSystemEventHandler):
        """Watchdog handler that triggers ANVIL verification on file changes."""

        def __init__(self, guard: AnvilGuard, callback: Optional[Callable] = None):
            self.guard = guard
            self.callback = callback
            self._last_modified: Dict[str, float] = {}
            self._debounce_ms = 500

        def on_modified(self, event):
            if event.is_directory:
                return
            self._handle(event.src_path)

        def on_created(self, event):
            if event.is_directory:
                return
            self._handle(event.src_path)

        def _handle(self, filepath: str):
            # Debounce rapid saves
            now = time.time() * 1000
            last = self._last_modified.get(filepath, 0)
            if now - last < self._debounce_ms:
                return
            self._last_modified[filepath] = now

            # Check if file type is relevant
            ext = os.path.splitext(filepath)[1].lower()
            all_ext = FRONTEND_EXTENSIONS | BACKEND_EXTENSIONS
            if ext not in all_ext:
                return

            # Skip ignored paths
            for pattern in self.guard.config.ignore_patterns:
                if pattern in filepath:
                    return

            # Run verification
            result = self.guard.verify_file(filepath)
            if result.layers_run:
                print(f"\n{result.summary()}")
                if self.callback:
                    self.callback(result)


def start_watcher(config: Optional[AnvilConfig] = None, watch_path: str = "."):
    """Start the ANVIL file watcher daemon."""
    if not HAS_WATCHDOG:
        print("[ANVIL] Error: watchdog not installed. pip install watchdog")
        sys.exit(1)

    guard = AnvilGuard(config)
    handler = AnvilWatchHandler(guard)
    observer = Observer()
    observer.schedule(handler, watch_path, recursive=True)
    observer.start()

    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  ⚒️  ANVIL GUARD — Watching: {os.path.abspath(watch_path)}")
    print(f"  TASTE: {config.taste.profile if config else 'linear'} profile")
    print(f"  Z3:    {len(guard._z3_guard.provers) if guard._z3_guard else 0} provers active")
    print(f"  Press Ctrl+C to stop")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n[ANVIL] Guard stopped.")
    observer.join()
