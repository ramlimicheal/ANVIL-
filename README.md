# ⚒️ ANVIL

**Forge AI Code Into Production Steel.**

The verification layer for AI-generated code. Three layers of mathematical proof between your AI assistant and your codebase.

```
AI generates code → ANVIL verifies it → You get production-ready output
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  LAYER 1: TASTE GUARD (Frontend Verification)            │
│  • Design token compliance (color, spacing, typography)  │
│  • WCAG accessibility contrast checking                  │
│  • 6D TasteVector quantification                         │
│  • 4 built-in profiles: linear, cyberpunk, soft, minimal │
├─────────────────────────────────────────────────────────┤
│  LAYER 2: Z3 GUARD (Backend Verification)                │
│  • Division by zero detection                            │
│  • Integer overflow proof (BitVec arithmetic)            │
│  • Array bounds checking                                 │
│  • Auth logic verification (OR vs AND bug detection)     │
│  • TOCTOU race condition detection                       │
├─────────────────────────────────────────────────────────┤
│  LAYER 3: SEMANTIC COMPRESSION (Token Optimization)      │
│  • Filler phrase removal                                 │
│  • Code instruction deduplication                        │
│  • Technical abbreviation                                │
│  • 3 levels: light (15%), medium (30%), aggressive (50%) │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Install
cd ANVIL
pip install -e .

# Initialize in your project
anvil init

# Verify frontend CSS/components
anvil taste src/styles/ --profile linear

# Prove backend logic
anvil prove src/api/

# Compress prompts
anvil compress prompt.txt --level medium

# Watch files (verify on save)
anvil guard src/

# Combined score
anvil score src/components/Pricing.tsx

# Start REST API daemon
anvil daemon --port 8084
```

## CLI Commands

| Command | Description |
|---|---|
| `anvil init` | Create `anvil.json` config in current directory |
| `anvil taste <path>` | Run TASTE Guard (design verification) |
| `anvil prove <path>` | Run Z3 Guard (logic verification) |
| `anvil compress <file>` | Semantic token compression |
| `anvil guard [path]` | File watcher — verify on every save |
| `anvil score <file>` | Combined ANVIL score (A+ to F) |
| `anvil daemon` | Start FastAPI REST server |

## API Endpoints

Start with `anvil daemon --port 8084`, then:

| Method | Endpoint | Description |
|---|---|---|
| GET | `/anvil/status` | Health check + config |
| POST | `/anvil/verify` | Full verification (auto-routes layers) |
| POST | `/anvil/taste` | Design verification only |
| POST | `/anvil/z3` | Logic proof only |
| POST | `/anvil/compress` | Token compression |
| POST | `/anvil/batch` | Verify multiple files |
| POST | `/anvil/score` | Combined ANVIL score |

### Example Request

```bash
curl -X POST http://localhost:8084/anvil/verify \
  -H "Content-Type: application/json" \
  -d '{"code": ".card { color: #333; padding: 13px; }", "filepath": "style.css"}'
```

## Design Profiles

TASTE Guard ships with 4 built-in profiles:

| Profile | Vibe | Accent | Radius |
|---|---|---|---|
| `linear` | Minimal, Professional | `#5E6AD2` | 12px |
| `cyberpunk` | Dark, Neon, Angular | `#FF0040` | 0px |
| `soft` | Warm, Round, Pastel | `#FFB6C1` | 24px |
| `minimal` | Clean, Sparse | `#000000` | 8px |

Custom profiles: save a StyleTensor JSON and set `custom_tensor_path` in `anvil.json`.

## Z3 Provers

| Prover | Catches |
|---|---|
| `div_zero` | Unguarded division, literal `/0` |
| `overflow` | Integer multiplication wrap-around |
| `bounds` | Array access without length check |
| `auth` | OR-vs-AND role check bugs, missing returns after deny |
| `concurrency` | Check-then-act race conditions without locks |

## Test Results

```
70 passed, 0 failed (4.68s)

Layer 1 TASTE:  34 tests (tensor, verifier, scorer)
Layer 2 Z3:     12 tests (div_zero, auth, concurrency, bounds, unified)
Layer 3 Compress: 10 tests (light, medium, aggressive, dedup, score)
Integration:    14 tests (config routing, guard, summary)
```

## Project Structure

```
ANVIL/
├── anvil/
│   ├── __init__.py          # Package root
│   ├── __main__.py          # python -m anvil
│   ├── cli.py               # Unified CLI
│   ├── daemon.py            # FastAPI REST server
│   ├── config.py            # Config + file routing
│   ├── taste/               # Layer 1: Frontend Verification
│   │   ├── tensor.py        # StyleTensor + 4 profiles
│   │   ├── verifier.py      # CSS/Tailwind checker
│   │   └── scorer.py        # Aesthetic quality scoring
│   ├── z3_guard/            # Layer 2: Backend Verification
│   │   └── provers.py       # 5 Z3 provers
│   ├── compress/            # Layer 3: Token Optimization
│   │   └── engine.py        # Semantic compressor
│   └── watcher/             # File System Guard
│       └── guard.py         # Watchdog + routing
├── tests/
│   └── test_anvil.py        # 70 tests
├── pyproject.toml           # Package config
├── ANVIL_SEED_PITCH_SCRIPT.md
├── ROADMAP.md
└── README.md
```

## Configuration (anvil.json)

```json
{
  "project_name": "my-saas",
  "taste": {
    "profile": "linear",
    "spacing_base": 4,
    "allowed_fonts": ["Inter", "system-ui", "sans-serif"],
    "wcag_level": "AA"
  },
  "z3": {
    "enabled_provers": ["div_zero", "overflow", "bounds", "auth", "concurrency"],
    "timeout_ms": 5000
  },
  "compression": {
    "level": "medium"
  },
  "watch_paths": ["src/", "app/", "lib/"],
  "ignore_patterns": ["node_modules", "__pycache__", ".git", "dist"]
}
```

---

*ANVIL — Forge AI Code Into Production Steel.*
*© 2026 Ramli T. Michael. All rights reserved.*
