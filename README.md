# ⚒️ ANVIL v5

**The Deterministic Physics Engine for AI-Generated UI.**

ANVIL does not generate code. It is the independent mathematical examiner that holds AI accountable. 14 validation dimensions. 3-tier short-circuit gate architecture. Zero trust in LLM self-evaluation.

```
Screenshot → AI builds code → ANVIL mathematically proves it's correct → ships
```

---

## What Makes It Different

| Tool | Approach | Result |
|---|---|---|
| Vercel v0 | AI generates → AI self-reviews | "Looks good to me" |
| Cursor | AI writes → AI checks | Fox guarding henhouse |
| Devin | Autonomous agent, no verification layer | Hope-based engineering |
| **ANVIL** | AI builds → **Independent math proves it** | Numbers don't negotiate |

ANVIL treats UI replication as a **compilation problem**, not a conversation. The browser renderer is the target machine. CSS properties are the instruction set. SSIM/CIEDE2000/Z3 are the verification passes.

---

## Architecture: 3-Tier Short-Circuit DAG

```
┌──────────────────────────────────────────────────────────┐
│  TIER 1: Symbolic & Lexical (~50ms, NO BROWSER)          │
│  ─────────────────────────────────                       │
│  TASTE CSS Lexer:    Token compliance, 4px grid, WCAG   │
│  6D Taste Vector:    Temperature/Density/Formality/      │
│                      Energy/Age/Price enforcement         │
│  Design Token Match: Palette, typography, spacing        │
│                                                          │
│  SHORT-CIRCUIT: taste_score < 4.0 → FAIL instantly       │
│  Why waste 1200ms on screenshots if CSS is wrong?        │
├──────────────────────────────────────────────────────────┤
│  TIER 2: Headless DOM Extraction (~400ms, NO SCREENSHOTS)│
│  ─────────────────────────────────                       │
│  Biomechanics:       Fitts's Law, 44×44px touch targets, │
│                      destructive action proximity        │
│  Chaos Gate:         7 data mutations (3x text, RTL,     │
│                      15x children, empty, compound word) │
│                                                          │
│  SHORT-CIRCUIT: ANY boolean gate fails → score = 0       │
│  Layout is brittle or ergonomically unsafe.              │
├──────────────────────────────────────────────────────────┤
│  TIER 3: Vision Physics (~1200ms, GPU MATRICES)          │
│  Only runs on code that passed Tiers 1-2                 │
│  ─────────────────────────────────                       │
│  SSIM:               Wang et al. windowed similarity     │
│  Semantic:           pHash + HOG + Lab + DCT             │
│                      (auto-upgrades to CLIP)             │
│  Block-Match:        Element IoU via Hungarian algorithm │
│  Saliency:           Spectral Residual + Jensen-Shannon  │
│  Physics:            Fresnel + Bloom + Specular decay    │
│  Color:              Bhattacharyya histogram distance    │
│  Edge:               Sobel + normalized cross-correlation│
│  Gestalt:            Optical mass centroid vs geometric   │
│                                                          │
│  Composite score ≥ 8.0 → PASS                           │
└──────────────────────────────────────────────────────────┘
```

**Key insight:** A layout with SSIM 0.99 that breaks with German text (Chaos Gate) or has 12px touch targets (Biomechanics) scores **zero**. Boolean gates kill before continuous metrics run.

---

## 14 Validation Dimensions

| # | Dimension | Module | Algorithm |
|---|---|---|---|
| 1 | **SSIM** | `vision/compare.py` | Wang et al. 2004 windowed luminance |
| 2 | **Semantic** | `vision/semantic.py` | pHash + HOG + Lab + DCT (→ CLIP) |
| 3 | **Block-Match** | `vision/block_match.py` | Connected components + Hungarian IoU |
| 4 | **Saliency** | `vision/saliency.py` | Spectral Residual + JSD attention map |
| 5 | **Gestalt** | `vision/gestalt.py` | Optical mass centroid (cv2.moments) |
| 6 | **Physics** | `vision/physics.py` | Fresnel + inverse-square bloom decay |
| 7 | **Color** | `vision/compare.py` | Bhattacharyya R/G/B histograms |
| 8 | **Edge** | `vision/compare.py` | Sobel gradient cross-correlation |
| 9 | **Region Grid** | `vision/compare.py` | 4×6 region SSIM breakdown |
| 10 | **Chaos Gate** | `chaos/fuzzer.py` | 7 data mutations + overflow detection |
| 11 | **Biomechanics** | `taste/biomechanics.py` | Fitts's Law + 44px touch targets |
| 12 | **TASTE** | `taste/verifier.py` | CSS lexer + CIEDE2000 color distance |
| 13 | **6D Vector** | `taste/tensor.py` | Temp/Density/Formality/Energy/Age/Price |
| 14 | **Z3 Proofs** | `z3_guard/provers.py` | Div-zero + overflow + auth + TOCTOU |

---

## Quick Start

```bash
# Install
cd ANVIL
pip install -e .

# Verify frontend CSS
anvil taste src/styles/ --profile linear

# Prove backend logic
anvil prove src/api/

# Combined score (A+ to F)
anvil score src/components/Card.tsx

# Watch files (verify on save)
anvil guard src/

# Compress LLM prompts
anvil compress prompt.txt --level medium
```

## MCP Integration (IDE)

ANVIL runs as an MCP server inside Windsurf/Cursor/VS Code. 13 tools:

| Tool | Description |
|---|---|
| `anvil_taste` | TASTE frontend verification |
| `anvil_prove` | Z3 backend logic proof |
| `anvil_verify` | Auto-routes frontend/backend |
| `anvil_score` | Combined A+ to F grading |
| `anvil_vision` | Pixel-level screenshot comparison |
| `anvil_validate_output` | **Core gate** — 3-tier DAG validation |
| `anvil_replicate` | Extract design tokens from screenshot |
| `anvil_extract` | Design system extraction |
| `anvil_compress` | Semantic token compression |
| `anvil_tokenize` | CSS tokenizer diagnostic |
| `anvil_guard` | Directory scan |
| `anvil_init` | Project initialization |
| `anvil_profiles` | List design profiles |

### Replication Workflow

```
1. anvil_replicate(screenshot.png)
   → Returns: palette, typography, spacing, taste_vector

2. AI builds HTML/CSS using extracted tokens

3. anvil_validate_output(reference.png, output.html, design_system.json)
   → Tier 1: TASTE lexer (~50ms) — short-circuits if tokens wrong
   → Tier 2: Biomechanics + Chaos (~400ms) — short-circuits if brittle
   → Tier 3: Vision matrices (~1200ms) — SSIM/Semantic/BlockMatch/Saliency
   → Returns: PASS/FAIL + per-dimension violations + fix hints

4. AI fixes violations → goto step 3
```

---

## Design Profiles

| Profile | Vibe | Accent | Radius |
|---|---|---|---|
| `linear` | Professional, Clean | `#5E6AD2` | 12px |
| `cyberpunk` | Dark, Neon, Angular | `#FF0040` | 0px |
| `soft` | Warm, Round, Pastel | `#FFB6C1` | 24px |
| `minimal` | Sparse, Monochrome | `#000000` | 8px |

Custom: save a StyleTensor JSON and set `custom_tensor_path` in `anvil.json`.

## Z3 Provers

| Prover | Detection |
|---|---|
| `div_zero` | AST-based unguarded division |
| `overflow` | 64-bit BitVec multiplication wrapping |
| `bounds` | Array access without len() guard |
| `auth` | OR-vs-AND role checks, missing deny returns |
| `concurrency` | Check-then-act race conditions without locks |

---

## Project Structure

```
ANVIL/
├── anvil/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py                  # Unified CLI
│   ├── daemon.py               # FastAPI REST server
│   ├── config.py               # Config + file routing
│   ├── mcp_server.py           # MCP server (13 tools)
│   │
│   ├── taste/                  # Frontend Verification
│   │   ├── tensor.py           # StyleTensor + 6D vector + 4 profiles
│   │   ├── verifier.py         # CSS lexer + CIEDE2000 + WCAG
│   │   ├── scorer.py           # Aesthetic quality scoring
│   │   └── biomechanics.py     # Fitts's Law + touch targets [NEW v5]
│   │
│   ├── z3_guard/               # Backend Verification
│   │   └── provers.py          # 5 AST-based Z3 provers
│   │
│   ├── vision/                 # Pixel-Level Comparison
│   │   ├── compare.py          # SSIM + Edge + Color + Region grid
│   │   ├── physics.py          # Photonic verification (Fresnel/Bloom)
│   │   ├── block_match.py      # Element IoU + Hungarian matching [NEW v5]
│   │   ├── semantic.py         # pHash/HOG/Lab/DCT (→ CLIP) [NEW v5]
│   │   ├── saliency.py         # Spectral Residual + JSD [NEW v5]
│   │   └── gestalt.py          # Optical mass centroid [NEW v5]
│   │
│   ├── chaos/                  # Layout Resilience Testing [NEW v5]
│   │   └── fuzzer.py           # 7 data mutations + overflow detection
│   │
│   ├── extract/                # Design System Extraction
│   │   ├── design_system.py    # OpenCV-based token extraction
│   │   └── responsive.py       # Responsive framework detection
│   │
│   ├── compress/               # Token Optimization
│   │   └── engine.py           # Semantic compressor (3 levels)
│   │
│   └── generate/               # ARCHIVED (v4+)
│       └── _ARCHIVED/          # Generation removed — ANVIL validates only
│
├── tests/
│   └── test_anvil.py           # 82 tests
├── pyproject.toml
└── README.md
```

## Dependencies

```
opencv-python          # Vision pipeline (SSIM, block-match, saliency, gestalt)
numpy                  # Matrix operations
scipy                  # Hungarian algorithm, curve fitting
Pillow                 # Image I/O
z3-solver              # Formal verification
playwright             # Headless browser (chaos gate, biomechanics)
tiktoken               # Token counting (compression)
```

**Optional (auto-upgrade):**
```
torch + transformers   # Enables real CLIP ViT-B/32 in semantic.py
```

---

## Version History

| Version | Changes |
|---|---|
| **v5** | 14 dimensions, 3-tier DAG, block-match, semantic, saliency, gestalt, chaos gate, biomechanics, 8 production bug fixes |
| **v4** | Generation archived, pure validation architecture, validate_output gate |
| **v3** | AST-based Z3 provers, hardened TASTE verifier, 6D taste vector |
| **v2** | Design system extractor, code generator |
| **v1** | TASTE + Z3 + compression, CLI + REST API |

---

*ANVIL — The Deterministic Physics Engine for AI-Generated UI.*
*© 2026 Ramli T. Michael. All rights reserved.*
