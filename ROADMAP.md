# ANVIL — Product Roadmap
## What's Built vs What Needs Building

---

## ✅ DONE (Working Code, Tested)

### Z3 Guard (Layer 2) — Backend Verification
| Component | File | Status |
|---|---|---|
| Z3 Bridge (ISM → SMT-LIB) | `AXIOM-Z3-KERNEL/cassiel/cassiel_z3_bridge.py` | ✅ 406 lines |
| 5 Vulnerability Provers | `cassiel/cassiel_vulnerability_provers.py` | ✅ 423 lines |
| FastAPI Daemon (:8082) | `cassiel/cassiel_daemon.py` | ✅ 406 lines |
| SENTINEL Wire | `cassiel/cassiel_sentinel_wire.py` | ✅ 305 lines |
| Test Suite | `tests/test_cassiel.py` | ✅ 18/18 passing |
| Launch Script | `launch_cassiel.sh` | ✅ 100 lines |

### TASTE Engine (Layer 1 — Partial) — Frontend Intelligence
| Component | File | Status |
|---|---|---|
| Vision Extractor (KMeans) | `taste_v4_engine.py` L0 | ✅ Screenshot → palette |
| StyleTensor + Extractor | `taste_v4_engine.py` L1 | ✅ JSON → tensor |
| 6D TasteVector | `taste_v4_engine.py` L2 | ✅ Quantification |
| Semantic Tokens | `taste_v4_engine.py` L3 | ✅ Trust/override/consequence |
| GCL Specification | `taste_v4_engine.py` L4 | ✅ Constraint language |
| HTML Generator | `taste_v4_engine.py` L5 | ✅ Full dashboard output |
| Feedback Loop | `taste_v4_engine.py` L6 | ✅ "make darker" → mutation |
| Quality Gate (Scoring) | `taste_v4_engine.py` L7 | ✅ Harmony/contrast /10 |
| TASTE Engine Spec | `TASTE_ENGINE.md` | ✅ Full documentation |

### SENTINEL V15 — Audit Engine
| Component | Status |
|---|---|
| 10 Detectors | ✅ Working |
| Brain (5,939 entries) | ✅ Indexed |
| Taint Engine | ✅ Working |
| Dual-Agent Falsifier | ✅ Working |

### AXIOM Daemon — Code Safety
| Component | Status |
|---|---|
| AST Parser (Python) | ✅ Working |
| Destroyer Gate (regex) | ✅ Working |
| File Watcher | ✅ Working |
| Z3 Constraints (Python) | ✅ Working |

---

## 🔧 NEEDS BUILDING

### Phase 1: ANVIL Core (Weeks 1-2)
| Task | Description | Effort |
|---|---|---|
| **TASTE Verifier** | Parse AI-generated CSS/Tailwind, compare against loaded StyleTensor, flag violations | 3 days |
| **Multi-lang AST (tree-sitter)** | Replace Python ast.parse with tree-sitter for JS/TS/Sol/Go | 5 days |
| **Unified ANVIL CLI** | Single CLI: `anvil taste`, `anvil prove`, `anvil compress`, `anvil guard` | 2 days |
| **ANVIL Daemon** | Unified FastAPI server combining TASTE + Z3 + Compression | 2 days |
| **File Watcher Integration** | On file save → route to correct layer (frontend → TASTE, backend → Z3) | 1 day |

### Phase 2: IDE Extension (Weeks 3-4)
| Task | Description | Effort |
|---|---|---|
| **VS Code Extension** | Extension that calls ANVIL daemon on save, shows inline violations | 5 days |
| **Cursor Integration** | Same extension, Cursor-compatible | 1 day (VS Code compatible) |
| **Inline Diagnostics** | Show TASTE violations as yellow squiggles, Z3 failures as red | 3 days |
| **Status Bar** | "ANVIL: ✅ 12/12 design tokens | ✅ Math proven" in bottom bar | 1 day |

### Phase 3: Compression Layer (Week 5)
| Task | Description | Effort |
|---|---|---|
| **Semantic Compressor** | Analyze prompts, remove redundancy, preserve meaning | 3 days |
| **Token Counter** | Show before/after token count and cost savings | 1 day |
| **Compression Profiles** | Different levels: light (10%), medium (30%), aggressive (50%) | 2 days |

### Phase 4: Polish + Launch (Weeks 6-8)
| Task | Description | Effort |
|---|---|---|
| **Landing Page** | ANVIL website with demo, pricing, docs | 3 days |
| **Documentation** | Full docs: installation, usage, API reference | 3 days |
| **Free Tier Backend** | Auth, usage tracking, rate limiting for free users | 3 days |
| **Pro Tier Billing** | Stripe integration for $12/mo subscription | 2 days |
| **CI/CD Plugin** | GitHub Action: run ANVIL on every PR | 3 days |

---

## Timeline Summary

```
Week 1-2:  ANVIL Core (CLI + Daemon + TASTE Verifier + Tree-sitter)
Week 3-4:  VS Code Extension (inline diagnostics, status bar)
Week 5:    Compression Layer (token optimization)
Week 6-8:  Landing page, docs, auth, billing, CI/CD
Week 9:    Public Beta Launch
Week 12:   5,000 users target
```

---

## File Structure (Target)

```
ANVIL/
├── anvil/
│   ├── __init__.py
│   ├── cli.py                    # Unified CLI entry point
│   ├── daemon.py                 # Unified FastAPI server
│   ├── config.py                 # Project config loader
│   │
│   ├── taste/                    # Layer 1: Frontend Verification
│   │   ├── tensor.py             # StyleTensor data model
│   │   ├── extractor.py          # CSS/Tailwind → token extraction
│   │   ├── verifier.py           # Compare code against tensor [BUILD]
│   │   ├── vision.py             # Screenshot → palette (KMeans)
│   │   ├── vector.py             # 6D TasteVector quantification
│   │   ├── scorer.py             # Quality Gate (harmony/contrast)
│   │   └── profiles/             # Predefined design profiles
│   │       ├── linear.json
│   │       ├── cyberpunk.json
│   │       └── soft.json
│   │
│   ├── z3_guard/                 # Layer 2: Backend Verification
│   │   ├── bridge.py             # ISM → Z3 constraint translator
│   │   ├── provers.py            # 5 specialized provers
│   │   ├── parsers/              # Language-specific AST parsers
│   │   │   ├── python_parser.py  # Exists (ast.parse)
│   │   │   ├── js_parser.py      # [BUILD] tree-sitter
│   │   │   ├── ts_parser.py      # [BUILD] tree-sitter
│   │   │   ├── sol_parser.py     # [BUILD] tree-sitter
│   │   │   └── go_parser.py      # [BUILD] tree-sitter
│   │   └── destroyer.py          # Dangerous pattern detection
│   │
│   ├── compress/                 # Layer 3: Token Optimization
│   │   ├── analyzer.py           # Token analysis [BUILD]
│   │   ├── compressor.py         # Semantic compression [BUILD]
│   │   └── profiles.py           # Compression levels [BUILD]
│   │
│   └── watcher/                  # File System Guard
│       ├── guard.py              # Watchdog file monitor
│       └── router.py             # Route files to correct layer
│
├── extension/                    # VS Code Extension [BUILD]
│   ├── package.json
│   ├── src/
│   │   └── extension.ts
│   └── README.md
│
├── tests/
│   ├── test_taste.py
│   ├── test_z3.py
│   ├── test_compress.py
│   └── test_integration.py
│
├── docs/
│   ├── getting-started.md
│   ├── api-reference.md
│   └── design-systems.md
│
├── ANVIL_SEED_PITCH_SCRIPT.md
├── ROADMAP.md
├── README.md
├── pyproject.toml
└── LICENSE
```
