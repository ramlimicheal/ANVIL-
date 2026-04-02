"""
ANVIL Daemon — Unified FastAPI server combining all 3 verification layers.
Exposes REST endpoints for TASTE, Z3, Compression, and combined verification.
"""

import os
import sys
import json
import time
from typing import Optional

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

from .config import AnvilConfig, detect_file_layer
from .taste.tensor import StyleTensor, load_profile
from .taste.verifier import TasteVerifier
from .taste.scorer import AestheticScorer
from .z3_guard.provers import AnvilZ3Guard
from .compress.engine import SemanticCompressor
from .watcher.guard import AnvilGuard


# ─── Pydantic Models ──────────────────────────────────────────

if HAS_FASTAPI:
    class VerifyRequest(BaseModel):
        code: str
        filepath: str = ""
        profile: str = "linear"

    class CompressRequest(BaseModel):
        text: str
        level: str = "medium"

    class BatchRequest(BaseModel):
        files: list  # List of {code, filepath} dicts
        profile: str = "linear"


def create_app(config: Optional[AnvilConfig] = None) -> "FastAPI":
    """Create and configure the ANVIL FastAPI application."""
    if not HAS_FASTAPI:
        raise ImportError("FastAPI not installed. pip install fastapi uvicorn")

    config = config or AnvilConfig()
    app = FastAPI(
        title="ANVIL",
        description="Forge AI Code Into Production Steel",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize layers
    guard = AnvilGuard(config)
    compressor = SemanticCompressor(config.compression.level)
    scorer = AestheticScorer()
    start_time = time.time()

    # ─── Endpoints ────────────────────────────────────────────

    @app.get("/anvil/status")
    def status():
        return {
            "status": "operational",
            "version": "0.1.0",
            "uptime_seconds": round(time.time() - start_time, 1),
            "layers": {
                "taste": guard._taste_verifier is not None,
                "z3": guard._z3_guard is not None,
                "compression": True,
            },
            "config": {
                "profile": config.taste.profile,
                "z3_provers": config.z3.enabled_provers,
                "compression_level": config.compression.level,
            },
        }

    @app.post("/anvil/verify")
    def verify(req: VerifyRequest):
        """Verify code through all applicable layers."""
        result = guard.verify_code(req.code, req.filepath)
        return {
            "filepath": result.filepath,
            "layers_run": result.layers_run,
            "passed": result.passed,
            "taste": result.details.get("taste"),
            "z3": result.details.get("z3"),
            "timestamp": result.timestamp,
        }

    @app.post("/anvil/taste")
    def taste_verify(req: VerifyRequest):
        """Run TASTE Guard only."""
        try:
            tensor = load_profile(req.profile)
        except ValueError as e:
            raise HTTPException(400, str(e))

        verifier = TasteVerifier(tensor)
        result = verifier.score(req.code)
        return {
            "score": result["score"],
            "pass": result["pass"],
            "errors": result["errors"],
            "warnings": result["warnings"],
            "infos": result["infos"],
            "violations": [str(v) for v in result["violations"][:20]],
            "total_violations": result["total_violations"],
            "profile": req.profile,
        }

    @app.post("/anvil/z3")
    def z3_verify(req: VerifyRequest):
        """Run Z3 Guard only."""
        if not guard._z3_guard:
            raise HTTPException(503, "Z3 not available")

        result = guard._z3_guard.score(req.code, req.filepath)
        return {
            "score": result["score"],
            "pass": result["pass"],
            "bugs_found": result["bugs_found"],
            "proven_safe": result["proven_safe"],
            "results": [str(r) for r in result["results"][:20]],
            "total_checks": result["total_checks"],
        }

    @app.post("/anvil/compress")
    def compress(req: CompressRequest):
        """Compress text semantically."""
        comp = SemanticCompressor(req.level)
        result = comp.compress(req.text)
        return {
            "compressed": result.compressed,
            "original_tokens": result.original_tokens,
            "compressed_tokens": result.compressed_tokens,
            "reduction_pct": result.reduction_pct,
            "techniques": result.techniques_applied,
            "level": req.level,
        }

    @app.post("/anvil/batch")
    def batch_verify(req: BatchRequest):
        """Verify multiple files in one request."""
        results = []
        for item in req.files:
            code = item.get("code", "")
            filepath = item.get("filepath", "")
            r = guard.verify_code(code, filepath)
            results.append({
                "filepath": r.filepath,
                "layers_run": r.layers_run,
                "passed": r.passed,
                "taste_score": r.taste_score,
                "z3_score": r.z3_score,
            })

        total = len(results)
        passed = sum(1 for r in results if r["passed"])
        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "results": results,
        }

    @app.post("/anvil/score")
    def full_score(req: VerifyRequest):
        """Get combined ANVIL score for code."""
        result = guard.verify_code(req.code, req.filepath)
        scores = []
        if result.taste_score is not None:
            scores.append(result.taste_score)
        if result.z3_score is not None:
            scores.append(result.z3_score)

        combined = round(sum(scores) / max(len(scores), 1), 1)
        return {
            "anvil_score": combined,
            "taste_score": result.taste_score,
            "z3_score": result.z3_score,
            "passed": result.passed,
            "grade": _grade(combined),
        }

    def _grade(score: float) -> str:
        if score >= 9.0: return "A+"
        if score >= 8.0: return "A"
        if score >= 7.0: return "B"
        if score >= 6.0: return "C"
        if score >= 4.0: return "D"
        return "F"

    return app


def run_daemon(host: str = "0.0.0.0", port: int = 8084, config: Optional[AnvilConfig] = None):
    """Start the ANVIL daemon."""
    import uvicorn

    app = create_app(config)
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  ⚒️  ANVIL DAEMON — http://{host}:{port}")
    print(f"  Endpoints:")
    print(f"    POST /anvil/verify    — Full verification")
    print(f"    POST /anvil/taste     — Design check only")
    print(f"    POST /anvil/z3        — Logic proof only")
    print(f"    POST /anvil/compress  — Token compression")
    print(f"    POST /anvil/batch     — Batch verification")
    print(f"    POST /anvil/score     — Combined score")
    print(f"    GET  /anvil/status    — Health check")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_daemon()
