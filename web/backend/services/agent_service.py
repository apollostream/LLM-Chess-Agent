"""Claude Code SDK integration — streams analysis via Claude Code.

Uses the Claude Code SDK to get full agent behavior: tool use,
skill auto-discovery, parse_position.sh, bfih_validator.py, etc.
Requires the `claude` CLI to be installed and ANTHROPIC_API_KEY set.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator

# Unset CLAUDECODE to allow SDK to launch from within a Claude Code session
os.environ.pop("CLAUDECODE", None)

from claude_code_sdk import query, ClaudeCodeOptions
from claude_code_sdk.types import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ToolUseBlock,
)

from config import PROJECT_ROOT

_GUIDE_PROMPT = """Analyze this chess position using the Implicative Reasoning Playbook: {fen}

Pre-computed imbalances, tactical motifs, and engine evaluation are provided below — use them as your source, do NOT re-run parse_position.sh.

Engine evaluation (Stockfish depth {depth}, top {lines} lines):
{engine_json}

IMPORTANT SCORE CONVENTION: Engine scores are ALWAYS from White's perspective. Positive (+) means White is better, negative (−) means Black is better. For example, "+2.54" when Black is to move means WHITE is ahead by 2.54 pawns — Black is LOSING. Do NOT misinterpret a positive score as good for Black.

IMPORTANT: When discussing candidate moves, plans, or tactical lines, you MUST ground your analysis in the engine's principal variations above. Do not propose moves or continuations that contradict the engine evaluation. Reference specific PV lines when relevant.

When citing evaluation scores, quote the EXACT score_display values from the engine evaluation above — do not round, interpolate, or approximate.

Imbalances and tactical motifs:
{analysis_json}
{pv_context}

=== IMPLICATIVE REASONING PLAYBOOK ===

Follow this algorithm to explain WHY the engine's top move is best:

1. POSITION ASSESSMENT: Identify the top 2-3 imbalances favoring each side. State who stands better and the position's character (static vs dynamic).

2. HUB FEATURE CHANGES: From the PV deltas above, identify the most significant changes in material, initiative, pawn count, dynamic/static score, and space. These explain the primary strategic effect of the engine's recommendation.

3. TACTICAL MOTIF ANALYSIS: Compare tactical motifs at P₀ vs the PV endpoint. For EACH motif that changed:
   - Name the specific motif (fork, pin, skewer, discovered attack, etc.)
   - Identify the pieces and squares involved (from the tactical motifs)
   - Classify: is this threat CREATION, ELIMINATION, CONVERSION, or PROPHYLAXIS?

4. DEPENDENCY CHAINS: Trace how hub changes produce downstream effects:
   - Initiative ↑ → fork/check/skewer threats emerge simultaneously (empirical: they co-move)
   - Pawn captured → file opens → rook activation
   - Material gain → board control shifts
   - Development ↑ → dynamism increases, opponent's dynamism decreases

5. GAME PHASE CONTEXT: Weight your analysis appropriately:
   - Opening: emphasize development, center control, castling
   - Middlegame: emphasize initiative, tactical motifs, king safety
   - Endgame: emphasize passed pawns, king activity, pawn structure

6. SYNTHESIZE: Write a coach-style Player's Guide explaining:
   - The current position assessment (imbalances, who stands better)
   - WHY the engine's move is best (grounded in feature deltas and tactical changes)
   - The concrete plan for the side to move (referencing specific PV lines)
   - If the eval swing greatly exceeds what positional features explain, acknowledge deep tactical content"""

_DEEP_PROMPT = """Perform a deep BFIH analysis of this position: {fen}

Use --deep mode. Follow the full 9-phase BFIH protocol as defined in SKILL.md.

Pre-computed imbalances and tactical motifs:
{analysis_json}"""

_SYNTHESIS_PROMPT = """Compose a Game Synopsis for this chess game.

You are given Player's Guides for {n} critical positions — each is a PV-grounded positional analysis. Synthesize them into a coherent narrative.

IMPORTANT SCORE CONVENTION: Engine scores are ALWAYS from White's perspective. Positive (+) means White is better, negative (−) means Black is better. "+2.54" means White is ahead, not the side to move. Do NOT misinterpret the sign.

IMPORTANT: Each critical moment header includes "Engine best move: [move] ([score])" — this is the engine's TOP recommendation at that position. When describing what should have been played, you MUST cite this move AND its exact score. Do not substitute alternative moves from lower-ranked engine lines or your own analysis. Do not round, interpolate, or approximate the evaluation score — quote it verbatim from the header.

Use this exact formatting template:

```
# Game Synopsis: [White] vs. [Black]

## [Thematic Arc Title — a vivid subtitle capturing the game's story]

[Opening paragraph: set the scene — opening name, early character, strategic themes established. Mention specific moves.]

### [Descriptive Title] (Move [N], [Side])

[What happened, why it mattered, what should have been played (cite engine best move). Write in flowing prose, not bullet points.]

### [Descriptive Title] (Move [N], [Side])

[Continue for each critical moment...]

### [Optional: Phase or Conversion Section Title] (Moves [N]–[M])

[For long endgame conversions or multi-move sequences, summarize as a section.]

### Key Lessons

**For White:** [1-2 sentences of concrete, actionable advice drawn from the game.]

**For Black:** [1-2 sentences of concrete, actionable advice drawn from the game.]

**The decisive moment** was move [N] — [1 sentence explaining why this was the turning point.]
```

Rules:
- Use H1 for the game title, H2 for the thematic subtitle, H3 for each critical moment section
- Bold **move notation** when citing the actual move played or the engine's recommended move
- Write in analytical prose — no bullet lists, no numbered lists
- Each critical moment section should be 1-2 substantial paragraphs
- The Key Lessons section must have per-side advice and identify the single decisive moment

PGN:
{pgn}

---

{guides_block}
"""


async def stream_agent(
    mode: str,
    fen: str | None = None,
    analysis_json: str | None = None,
    engine_json: str | None = None,
    depth: int = 20,
    lines: int = 3,
    pgn: str | None = None,
    guides_block: str | None = None,
    n_moments: int = 0,
) -> AsyncIterator[str]:
    """Stream Claude Code analysis as SSE events.

    Yields SSE-formatted strings: "data: {json}\\n\\n"
    """
    if mode == "guide":
        # Compute PV context (feature deltas + tactical motif details)
        pv_context_str = ""
        if fen and analysis_json and engine_json:
            try:
                from services.chess_pipeline import compute_pv_context
                import json as _json
                analysis_dict = _json.loads(analysis_json)
                pv_ctx = compute_pv_context(fen, analysis_dict, engine_json)
                if pv_ctx:
                    pv_context_str = "\n" + pv_ctx
            except Exception:
                pass  # Fall back to prompt without PV context

        prompt = _GUIDE_PROMPT.format(
            fen=fen,
            analysis_json=analysis_json or "{}",
            engine_json=engine_json or "{}",
            depth=depth,
            lines=lines,
            pv_context=pv_context_str,
        )
    elif mode == "deep":
        prompt = _DEEP_PROMPT.format(fen=fen, analysis_json=analysis_json or "{}")
    elif mode == "synthesis":
        prompt = _SYNTHESIS_PROMPT.format(
            n=n_moments,
            pgn=pgn or "",
            guides_block=guides_block or "",
        )
    else:
        yield _sse({"type": "error", "content": f"Unknown mode: {mode}"})
        return

    max_turns = 50 if mode == "deep" else 15 if mode == "synthesis" else 25
    options = ClaudeCodeOptions(
        cwd=str(PROJECT_ROOT),
        permission_mode="auto",
        max_turns=max_turns,
        include_partial_messages=True,
    )

    try:
        async for message in query(prompt=prompt, options=options):
            try:
                if isinstance(message, StreamEvent):
                    event = message.event
                    event_type = event.get("type")

                    if event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                yield _sse({"type": "text", "content": text})

                    elif event_type == "content_block_start":
                        cb = event.get("content_block", {})
                        if cb.get("type") == "tool_use":
                            yield _sse({
                                "type": "tool_start",
                                "tool": cb.get("name", ""),
                            })

                    elif event_type == "content_block_stop":
                        pass

                elif isinstance(message, AssistantMessage):
                    # Text already streamed via StreamEvent deltas — only emit tool use
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            yield _sse({
                                "type": "tool_use",
                                "tool": block.name,
                                "input": _truncate(block.input),
                            })

                elif isinstance(message, ResultMessage):
                    yield _sse({
                        "type": "done",
                        "is_error": message.is_error,
                        "duration_ms": message.duration_ms,
                        "cost_usd": message.total_cost_usd,
                    })

            except Exception:
                # Skip unknown message types (e.g. rate_limit_event)
                continue

    except Exception as e:
        yield _sse({"type": "error", "content": str(e)})


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _truncate(obj: dict, max_len: int = 200) -> dict:
    """Truncate long string values in a dict for display."""
    result = {}
    for k, v in obj.items():
        if isinstance(v, str) and len(v) > max_len:
            result[k] = v[:max_len] + "..."
        else:
            result[k] = v
    return result
