# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
.venv/bin/pytest tests/ -v

# Run a single test class or test
.venv/bin/pytest tests/test_board_utils.py::TestPawnStructure -v
.venv/bin/pytest tests/test_board_utils.py::TestPawnStructure::test_passed_pawn -v

# Analyze a position (JSON output)
.claude/skills/chess-imbalances/scripts/parse_position.sh "<FEN>"

# Analyze with text output, or at a specific move
.claude/skills/chess-imbalances/scripts/parse_position.sh game.pgn --format text --move 15b

# Analyze with Stockfish engine evaluation
.claude/skills/chess-imbalances/scripts/parse_position.sh "<FEN>" --format text --engine --depth 20 --lines 3

# BFIH validator — validate a single phase or all phases
.venv/bin/python .claude/skills/chess-imbalances/scripts/bfih_validator.py validate-phase 1 analysis/bfih_phases/phase_1.json
.venv/bin/python .claude/skills/chess-imbalances/scripts/bfih_validator.py validate-all analysis/bfih_phases/ --position-data analysis/bfih_phases/position_data.json
.venv/bin/python .claude/skills/chess-imbalances/scripts/bfih_validator.py schema 3

# BFIH formatter — render validated phases to markdown
.venv/bin/python .claude/skills/chess-imbalances/scripts/bfih_formatter.py render analysis/bfih_phases/ --output analysis/deep-analysis.md
.venv/bin/python .claude/skills/chess-imbalances/scripts/bfih_formatter.py summary analysis/bfih_phases/

# Game narrative — detect critical moments in a PGN
# (used as a library from Python, not a standalone CLI)
# from game_narrative import detect_critical_moments, GameNarrative, render_game_story
# moments = detect_critical_moments("game.pgn", depth=18, threshold_cp=50, decay_scale_cp=750)

# Install dependencies
source .venv/bin/activate && pip install -r requirements.txt
```

## Architecture

This is a Claude Code skill project. The skill analyzes chess positions through Silman's 10-imbalance framework.

**Core pipeline:** Input (FEN/PGN/moves) → `board_utils.py` (python-chess analysis → JSON) → Claude (imbalance narrative + strategic assessment) → output (file + summary, or console-only).

**`board_utils.py`** is the analysis engine. It produces a structured JSON report with sections: material, pawn_structure, piece_activity, files, king_safety, space, pins, tactics, development, game_phase, legal_moves. Each section maps to one or more of Silman's 10 imbalances — the mapping is documented in `references/imbalances_guide.md` and the SKILL.md quick-reference table.

**`tactical_motifs.py`** detects 19 tactical patterns across three tiers: static board patterns (pins, batteries, x-rays, hanging/overloaded/trapped pieces, weak back rank, advanced passed pawns, alignments), single-move threats (forks, skewers, discovered attacks/checks, double checks, back rank mates, removal of guard), and 2-move forced sequences (deflections, zwischenzug, smothered mates). Called by `board_utils.py` and produces the `tactics` key in the analysis JSON.

**Three analysis modes** are defined in `SKILL.md`:
- **Guide** (default): PV-grounded Player's Guide — scan all 10 imbalances with engine multi-PV lines, synthesize, recommend concrete plans referencing specific engine variations.
- **Deep** (`--deep`): Full BFIH protocol — competing hypotheses, paradigm inversion, evidence matrix. Protocol defined in `references/bfih_chess_protocol.md`.
- **Synopsis** (`--narrative`): Full-game engine sweep → critical moment detection → PV-grounded Player's Guide per moment → synthesis into coherent game narrative. Requires PGN input.

**BFIH enforcement pipeline** (`--deep` mode): Three CLI tools support deep analysis. `bfih_models.py` defines Pydantic v2 models for the 9 BFIH phases with built-in validation constraints. `bfih_validator.py` is a CLI tool Claude Code calls after generating each phase's JSON — it validates against models and enforces cross-phase gates (G2, G5, G6, G8). `bfih_formatter.py` renders validated phase JSON to markdown. Claude Code follows SKILL.md's step-by-step deep mode protocol; Python provides validation and formatting, not orchestration.

**`game_narrative.py`** provides the full-game narrative pipeline. `detect_critical_moments()` sweeps every move with Stockfish, flags eval swings above a threshold, and returns sorted `CriticalMoment` objects. An exponential decay factor (`decay_scale_cp`, default 750) raises the effective threshold in lopsided positions — `effective = threshold / exp(-|eval|/A)` — suppressing noise when the game is already decided while still flagging important conversion errors. `GameNarrative` and related Pydantic models define the game story structure (arc type, critical moments, turning point, key lessons). `render_game_story()` renders a completed narrative to markdown. Claude Code uses this as a library — detection is automated, narrative synthesis is Claude's job.

**`engine_eval.py`** wraps Stockfish via python-chess's UCI protocol. Context-managed `EngineEval` class provides `evaluate_position()`, `evaluate_multipv()`, and `classify_move()`. Auto-discovers Stockfish binary; gracefully returns `None` when unavailable. Called by `board_utils.py` when `--engine` flag is passed, producing the `engine` key in the analysis JSON.

**`parse_position.sh`** is a thin wrapper that resolves `.venv/bin/python` and forwards args to `board_utils.py`. Always use the venv Python, never system Python.

**Web backend** (`web/backend/`): FastAPI app serving the React frontend. `agent_service.py` streams Claude Code SDK calls with three prompt modes: `guide` (PV-grounded Player's Guide), `deep` (BFIH), `synthesis` (game synopsis from pre-built guides). `synopsis_service.py` orchestrates the Game Synopsis pipeline: parallel engine+analysis → sequential cached Player's Guides → streaming synthesis. All results cached via `cache.py` (AnalysisCache, AgentCache).

## Coding Rules

Follow the five agentic coding rules (see memory/agentic-coding-rules.md):
1. **1-3-1**: When stuck, present 1 problem, 3 options, 1 recommendation. Wait for user confirmation.
2. **DRY**: No repeated code. Grep and refactor.
3. **TDD**: Write tests BEFORE implementation. Confirm test structure with the user first.
4. **Continuous Learning**: When features change or docs become stale, propose updates to CLAUDE.md/SKILL.md/rules. Don't wait to be asked.
5. **Planning**: For complex tasks, plan first with a todo list before writing code.

## FEN Construction

Never hand-construct FEN strings without programmatic verification. Derive test positions from move sequences (`board_from_moves()`) where possible. For hand-crafted FEN, validate with `chess.Board(fen)` before use. Common pitfalls: captures move pieces (not remove them), pin geometry requires clear lines, hidden pawns provide unexpected support.

## GitHub

SSH is blocked in this environment. Push via HTTPS with token:
```bash
git remote set-url origin https://x-access-token:$(gh auth token)@github.com/apollostream/LLM-Chess-Agent.git
```
