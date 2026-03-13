# Sharing the Chess Imbalances Skill as a User-Friendly App

Research conducted 2026-03-12. Goal: identify the most compelling way to share Claude Code + the chess-imbalances skill with a friend (who has a Claude Code account) as an easy-to-use app.

---

## The Core Question

We have a powerful chess analysis pipeline:
- `board_utils.py` — structured position analysis (material, pawn structure, piece activity, king safety, space, etc.)
- `tactical_motifs.py` — 19 tactical pattern detectors across 3 tiers
- `engine_eval.py` — Stockfish integration (eval, multi-PV, move classification)
- `SKILL.md` — Claude Code skill that turns all of this into Silman-framework narrative analysis

How do we wrap this in something a friend can use without touching a terminal?

---

## Distribution Channels (Simplest to Most Ambitious)

### 1. Git Clone + Claude Code Skill (Available Now, ~5 min setup)

The simplest path. Your friend clones the repo, and the skill auto-loads:

```bash
git clone https://github.com/apollostream/LLM-Chess-Agent.git
cd LLM-Chess-Agent
pip install -r requirements.txt  # or use .venv
# Now just use Claude Code in this directory — the skill is live
```

**Pros:** Zero additional code. Works today.
**Cons:** Requires terminal comfort, git, Python environment setup. Not "app-like."

### 2. Claude Code Plugin Marketplace (Available Now, Medium Effort)

Claude Code has a plugin ecosystem (834+ plugins across 43 marketplaces as of early 2026). A plugin bundles skills, slash commands, hooks, and MCP servers into a single installable unit.

```bash
# Your friend would run:
/plugin marketplace add apollostream/LLM-Chess-Agent
/plugin install chess-imbalances
```

**How it works:** Create a `marketplace.json` in the repo, register skills and dependencies. Users install with two commands. Plugin sources support GitHub repos, git URLs, npm/pip packages, and local paths.

**Pros:** One-command install. Automatic updates. Community-standard distribution.
**Cons:** Still terminal-based. Friend needs Claude Code CLI. No visual board.

**Docs:** [code.claude.com/docs/en/plugin-marketplaces](https://code.claude.com/docs/en/plugin-marketplaces), [code.claude.com/docs/en/plugins](https://code.claude.com/docs/en/plugins)

### 3. MCP Server (Available Now, Medium Effort)

Wrap `board_utils.py` as an MCP (Model Context Protocol) server. This makes the analysis available to Claude Desktop, Claude Code, and any MCP-compatible client via natural language.

```python
# chess_mcp_server.py (FastMCP)
from fastmcp import FastMCP
mcp = FastMCP("chess-imbalances")

@mcp.tool()
def analyze_position(fen: str, engine: bool = False) -> dict:
    """Analyze a chess position through Silman's imbalance framework."""
    board = chess.Board(fen)
    return board_utils.analyze_position(board, ...)
```

Your friend adds one line to their Claude Desktop config and can then say "analyze this position" in natural language.

**Existing chess MCP servers for reference:**
- [chessagine-mcp](https://github.com/jalpp/chessagine-mcp) — Stockfish + opening DB + Lichess, TypeScript
- [chesspal-mcp-engine](https://github.com/wilson-urdaneta/chesspal-mcp-engine) — Stockfish via FastMCP, Python
- [chess-mcp](https://github.com/pab1it0/chess-mcp) — Chess.com data API
- [chess-support-mcp](https://github.com/danilop/chess-support-mcp) — game state management for LLMs

**Pros:** Natural language interface. Works in Claude Desktop (GUI). No terminal needed after setup.
**Cons:** No visual board. Setup requires editing a JSON config file.

### 4. Claude Agent SDK + Web App (Available Now, Higher Effort, Most Compelling)

**This is the formal way to wrap Claude Code inside an app.** The Claude Agent SDK (Python v0.1.48, TypeScript v0.2.71) gives you the same tools, agent loop, and context management that power Claude Code, as a programmable library.

```python
from claude_agent_sdk import query, ClaudeAgentOptions

async for message in query(
    prompt="Analyze this chess position: <FEN>",
    options=ClaudeAgentOptions(allowed_tools=["Read", "Bash", "Glob"]),
):
    # Stream the analysis to your web UI
    yield message
```

**Key resources:**
- [Agent SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [GitHub: anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python)
- [GitHub: anthropics/claude-agent-sdk-demos](https://github.com/anthropics/claude-agent-sdk-demos)
- [Building Agents with Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk)

**Constraint:** Requires an Anthropic API key. Cannot redistribute Claude Code's own rate limits. Must use your own branding (not "Claude Code").

---

## UI/UX Hypotheses: What Would Be Truly Compelling?

### Hypothesis A: "The Silman Coach" — Streamlit Prototype (Fastest to Build)

**Concept:** A web app where you paste a FEN or upload a PGN, see the board rendered with tactical annotations (arrows for skewers, highlights for weak squares), and get streaming Silman-framework commentary.

**Stack:**
- `streamlit` + `streamlit-chess-board` (fsmosca) or `streamlit-chess` (TheoLvs) for interactive board
- `python-chess` SVG rendering with arrows for tactical motifs
- Claude API (or Agent SDK) for narrative generation
- Existing `board_utils.py` + `tactical_motifs.py` + `engine_eval.py` as the analysis backend

**UX Flow:**
1. Paste FEN, upload PGN, or enter moves
2. Board renders with click-through move navigation
3. Side panel streams: imbalance assessment, tactical resources, engine eval
4. Arrows/highlights show key tactical motifs (Bc6 skewer, fork squares, etc.)
5. "What should I play?" button triggers candidate move analysis

**Effort:** ~2-3 days to prototype. Streamlit handles auth, hosting, sharing via URL.
**Polish ceiling:** Medium. Streamlit's re-run model creates latency. UI is functional but not beautiful.

**Reference:** [Chesalyser](https://github.com/kayozxo/Chesalyser) — full Streamlit chess analyzer with Stockfish. Good UX reference.

### Hypothesis B: "The Commentary Engine" — React + Chessground (Highest Polish)

**Concept:** A Lichess-quality board UI with real-time streaming commentary. The board shows the position with professional-grade piece rendering. As you navigate moves, Claude provides running Silman-framework analysis — like having a grandmaster commentator whispering in your ear.

**Stack:**
- Frontend: React + [Chessground](https://github.com/lichess-org/chessground) (Lichess's board UI, 10KB gzipped, zero deps) + chess.js for logic
- Backend: FastAPI + your analysis pipeline + Claude Agent SDK for narrative
- WebSocket for streaming commentary as user navigates moves
- Arrows/highlights via Chessground's built-in annotation API

**UX Flow:**
1. Upload PGN or paste FEN. Board appears with Lichess-quality rendering.
2. Navigation bar below board — click through moves like on Lichess.
3. Right panel: streaming analysis for current position
   - **Imbalances** tab: Silman framework assessment with color-coded severity
   - **Tactics** tab: detected motifs with board arrows showing each one
   - **Engine** tab: eval bar, top 3 lines, move classification (best/good/inaccuracy/blunder)
   - **Plan** tab: target sector, fantasy position, candidate moves
4. Click any move in the PGN — get classification (best/excellent/good/inaccuracy/mistake/blunder) with explanation
5. "Deep Analysis" button triggers full BFIH protocol

**Board annotation capabilities (all built into Chessground):**
- Arrows: show skewer lines, fork targets, discovered attack rays
- Square highlights: weak squares, outpost squares, king danger zone
- Last-move highlighting
- Premove/candidate move display
- Drag-and-drop for "what if" exploration

**Alternative frontend frameworks:**
| Framework | Arrows | Highlights | Drag/Drop | Polish |
|-----------|--------|------------|-----------|--------|
| [Chessground](https://github.com/lichess-org/chessground) | Built-in | Built-in | Yes | Highest (Lichess-quality) |
| [react-chessboard](https://github.com/Clariity/react-chessboard) | customArrows prop | squareStyles prop | Yes | High |
| [cm-chessboard](https://github.com/shaack/cm-chessboard) | Arrow Extension | Marker Extension | Yes | High |
| [chessboard-element](https://github.com/justinfagnani/chessboard-element) | Limited | Limited | Yes | Medium (Web Component) |

**Effort:** ~1-2 weeks for MVP. Production-quality in ~1 month.
**Polish ceiling:** Very high. This is what Lichess and chess.com look like.

### Hypothesis C: "The Analysis Artifact" — Claude Artifacts (Zero Code)

**Concept:** Create a reusable Claude Artifact that renders an interactive chess board with your analysis overlaid. Share the artifact URL — your friend opens it in any browser.

Claude can already generate [interactive chess artifacts](https://claude.ai/public/artifacts/34d7eea2-6160-4ff0-9197-497c33011c1d). The idea is to create a template artifact that:
- Accepts a FEN via URL parameter or text input
- Renders the board with chessboard.js (embedded in the artifact)
- Displays pre-computed analysis alongside the board

**Limitation:** Artifacts are static HTML/JS — no server calls. So the analysis must be pre-computed and embedded. This works for sharing specific analyses ("look at this position") but not for interactive "analyze any position" workflows.

**Effort:** ~1 hour per analysis artifact. Zero infrastructure.
**Best for:** Sharing specific interesting positions, not a general-purpose tool.

### Hypothesis D: "The MCP Chess Coach" — Claude Desktop Integration (Smoothest UX for Claude Users)

**Concept:** Package the analysis pipeline as an MCP server. Your friend adds it to Claude Desktop and can analyze positions using natural language — "What are the imbalances in this position?" — with Claude orchestrating your tools behind the scenes.

**UX Flow:**
1. Friend installs: `pip install chess-imbalances-mcp` (or clones repo)
2. Adds one entry to Claude Desktop's MCP config
3. Opens Claude Desktop and says: "Analyze the position after 1.e4 e5 2.Nf3 Nc6 3.Bb5"
4. Claude calls your MCP tools, gets structured analysis, and narrates it
5. Claude can render board diagrams using python-chess SVG (as image artifacts)

**Pros:** Most natural interaction model. Leverages Claude's own conversational ability. Your friend already knows how to use Claude.
**Cons:** No persistent board UI. Each analysis is a conversation turn. Can't click through moves.

---

## Hypothesis A Deep Dive: Streamlit App

### What It Would Look Like

Two-column layout: python-chess SVG board with arrow overlays on the left, streaming Claude narrative on the right. Move navigation via slider/buttons. Tabbed analysis panel (Imbalances / Tactics / Engine / Plan).

### Board Rendering

python-chess `chess.svg.board()` supports arrows, square highlights, last-move shading, check indicators, coordinate labels, and custom colors. Display via `st.html(svg_string)`. This is static/read-only — no drag-and-drop, no click-to-move. Chesalyser (existing Streamlit chess app) proves this approach works in production.

### Streamlit Chess Components (Status: Dead)

| Component | Last Activity | Status |
|-----------|--------------|--------|
| `streamlit-chess-board` (fsmosca) | Dec 2022 | Dead. Doesn't work on Streamlit Community Cloud. |
| `streamlit-chess` (TheoLvs) | May 2021 | Dead. 3 commits total. Broken imports. |

Neither is viable. The python-chess SVG approach is the only realistic path.

### Effort Estimate

| Component | Effort |
|-----------|--------|
| Board SVG with tactical arrows | ~4 hours |
| Two-column layout | ~1 hour |
| PGN upload + FEN input | ~2 hours |
| Move navigation slider | ~2 hours |
| Tabbed analysis panel | ~3 hours |
| Claude streaming narrative | ~4 hours |
| FEN-keyed analysis cache | ~2 hours |
| Prompt caching | ~30 min |
| Dark theme + styling | ~2 hours |
| Deployment (Streamlit Community Cloud) | ~1 hour |
| **Total** | **~3 days** |

### Strengths

- Python-only — zero frontend code
- Free deployment with shareable URL
- `@st.cache_data` for trivial caching
- `st.write_stream` for Claude streaming
- Board arrows from python-chess are professional quality

### Limitations

- No drag-and-drop (all components are dead/broken)
- No click-to-move (SVG is static)
- ~200-500ms flicker on every widget interaction (Streamlit re-runs full script)
- Poor mobile support (columns don't reflow)
- 1GB memory limit on free tier

---

## Hypothesis B Deep Dive: React + Chessground App

### What It Would Look Like

Lichess-quality interactive board with smooth piece animation, programmatic arrows showing tactical motifs, drag-and-drop for "what if" exploration, and streaming Silman-framework narrative in a side panel. Move tree with click-to-navigate. Eval bar. Tabbed analysis.

### Chessground (v10.1.0, March 2026)

Lichess's board UI. 10KB gzipped, zero dependencies, vanilla TypeScript. Battle-tested on millions of users.

**Arrow API:**
```typescript
ground.setAutoShapes([
  { orig: 'c6', dest: 'f3', brush: 'green' },           // skewer arrow
  { orig: 'e3', dest: 'd3', brush: 'yellow' },           // fork arrow
  { orig: 'g2', brush: 'red' },                           // danger circle
  { orig: 'e2', dest: 'e4', brush: 'blue', label: { text: '!' } }  // labeled
]);
```
Brushes: `green`, `red`, `blue`, `yellow`, `purple` (CSS-customizable). Users can right-click-drag to draw their own arrows.

**Square highlights:** `lastMove`, `check`, `selected` — all CSS-class-based, fully customizable.

**Animation:** `animation: { enabled: true, duration: 200 }` — smooth CSS transitions between positions.

**Interactivity:** Drag-and-drop, tap-tap moves, premove display, move destination dots, touch/mobile support.

**Themes:** Swap CSS files for board colors and piece sets.

### React Integration

Chessground is framework-agnostic (Lichess uses Snabbdom, not React). Available wrappers:

| Package | Status | Notes |
|---------|--------|-------|
| `@react-chess/chessground` | Active | Cleanest wrapper, React 16.8-18 |
| `@bezalel6/react-chessground` | Active | Full TypeScript, modern fork |
| DIY (~30 lines) | N/A | `useRef` + `useEffect` — full control |

**Gotcha:** `drawable.autoShapes` resets to `[]` before each config merge — must re-supply arrows on every render.

### Backend: FastAPI + SSE

SSE (Server-Sent Events) over WebSocket for this use case:
- Analysis is unidirectional (server → client)
- Built-in browser reconnection with `Last-Event-ID`
- Works over standard HTTP, CDN-friendly
- Simpler infrastructure

```python
@app.post("/stream")
async def stream_analysis(request: AnalysisRequest):
    async def generate():
        async with client.messages.stream(...) as stream:
            async for text in stream.text_stream:
                yield f"data: {json.dumps({'text': text})}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

### Architecture

```
Browser (React + Vite + TypeScript)
  ├── Chessground (board, arrows, drag-drop)
  ├── chess.js (move validation, PGN parsing)
  └── EventSource (SSE) for streaming
        │
FastAPI (Python backend)
  ├── POST /analyze  → board_utils.py JSON (cached by FEN)
  ├── POST /tactics  → tactical_motifs.py (cached by FEN)
  ├── POST /engine   → engine_eval.py (cached by FEN+depth)
  ├── POST /stream   → SSE: Claude narrative (prompt-cached)
  └── POST /classify → engine_eval.classify_move()
```

### Effort Estimate

| Component | Lines | Effort | Difficulty |
|-----------|-------|--------|------------|
| Chessground wrapper + board | ~100 | 1-2 hours | Easy |
| Arrow/highlight mapping from analysis | ~150 | 2-4 hours | Easy-Medium |
| Position input (FEN/PGN, upload) | ~200 | 2-4 hours | Easy |
| Streaming analysis panel + tabs | ~300 | 4-8 hours | Medium |
| Move tree navigator + PGN display | ~400 | 1-2 days | **Hard** |
| FastAPI backend (endpoints, SSE) | ~250 | 4-8 hours | Medium |
| Integration with existing pipeline | ~100 | 2-4 hours | Easy |
| FEN-keyed caching layer | ~100 | 2-4 hours | Easy |
| Styling, layout, responsive | ~300 CSS | 1-2 days | Medium |
| **Total** | **~1,850** | **~2-3 weeks** | |

The move tree is the rabbit hole. Flat PGN with click-to-navigate: ~1 day. Full branching variation tree (like Lichess): weeks.

### Deployment

| Component | Platform | Free Tier | Paid |
|-----------|----------|-----------|------|
| React frontend | Vercel | 100GB bandwidth/mo | $20/mo |
| Python backend | Render | 750 hrs/mo (sleeps) | $7/mo |
| Alternative | Railway | $5 credit/mo | Usage-based |
| Self-hosted | Docker Compose | N/A | Your infra |

### Strengths

- Lichess-quality board with animation, arrows, drag-and-drop
- "What if" exploration — drag a piece, see analysis update
- No interaction flicker (React state updates are instant)
- Mobile-ready (Chessground built for Lichess mobile)
- Unlimited UI ceiling — eval bar, variation trees, annotation tools
- Full control over streaming UX

### Limitations

- 5-10x more frontend effort (~1,500 lines TypeScript vs zero)
- Two codebases to maintain (frontend + backend)
- Deployment complexity (two services, CORS, env vars in two places)
- Requires TypeScript/React skills
- Not free by default (though free tiers exist)
- Move tree navigator is disproportionately complex

---

## Head-to-Head: Streamlit vs React + Chessground

| Dimension | Streamlit | React + Chessground |
|-----------|-----------|---------------------|
| Time to prototype | ~3 days | ~1-2 weeks |
| Time to polish | ~1 week | ~3-4 weeks |
| Board quality | Static SVG, no animation | Lichess-grade, animated, interactive |
| Drag-and-drop | No | Yes (native) |
| Arrows/highlights | python-chess SVG (static) | Programmatic, animated, user-drawable |
| Mobile | Poor | Good |
| Streaming UX | `st.write_stream` (adequate) | Full SSE control, token-by-token |
| Interaction latency | ~200-500ms flicker | Instant |
| Layout control | Streamlit widgets only | Full CSS/HTML |
| Deployment cost | Free | Free tiers exist, ~$7-27/mo always-on |
| Frontend code | 0 lines | ~1,500 lines TypeScript |
| Backend code | ~200 lines | ~350 lines (FastAPI) |
| Skill required | Python only | Python + TypeScript + React + CSS |

**Verdict:** Streamlit is a 3-day experiment that validates whether the analysis is compelling. React + Chessground is a 3-week investment that makes the experience feel like a real product. The backend is identical — the question is purely about the frontend experience and how much time to invest.

---

## Existing Projects Worth Studying

| Project | Stack | Relevance |
|---------|-------|-----------|
| [ChessAgine Web](https://github.com/jalpp/chessagineweb) | React + FastAPI + Ollama/Claude + Stockfish | Closest to Hypothesis B. Open source. Has MCP server. |
| [Chesalyser](https://github.com/kayozxo/Chesalyser) | Streamlit + Stockfish + python-chess SVG | Closest to Hypothesis A. Good Streamlit chess UX reference. |
| [ChessCoach](https://github.com/chrisbutner/ChessCoach) | Custom engine + Transformer commentary | Architecture reference: engine eval → neural commentary pipeline. |
| [DecodeChess](https://decodechess.com/) | Commercial, closed source | UX reference for "explainable AI" chess analysis. |
| [ChessLogix](https://www.chesslogix.com/) | Stockfish + GPT-4/Claude | Commercial reference for engine + LLM commentary. |

---

## Recommendation

**For sharing with a friend who has Claude Code:** Start with **Option 2 (Plugin)** — it's the lowest-friction path that preserves the full skill experience. Your friend installs with two commands and uses `/chess-imbalances` naturally.

**For building something truly compelling:** **Hypothesis B (React + Chessground)** is the endgame, but **Hypothesis A (Streamlit)** is the right first step. Build the Streamlit prototype in 2-3 days, validate the UX with your friend, then graduate to Chessground if it warrants the investment.

**For maximum reach with minimum code:** **Hypothesis D (MCP server)** lets anyone with Claude Desktop use your analysis pipeline via natural language. Combined with the Plugin for Claude Code users, this covers both audiences.

The **Claude Agent SDK** is the formal bridge between "Claude Code skill" and "standalone app." It's what you'd use under the hood for Hypotheses A and B.

---

## Caching Architecture

Chess positions have a perfect cache key: the FEN string. A three-layer caching strategy dramatically reduces cost and latency.

### Layer 1: Deterministic Analysis Cache (FEN → JSON)

`board_utils.py`, `tactical_motifs.py`, and `engine_eval.py` are pure functions — same FEN always produces same output. Cache with no expiry concerns.

- **Key:** FEN string (optionally strip halfmove/fullmove counters)
- **Storage:** Redis, SQLite, or in-memory dict
- **Savings:** 100% — skip all computation on cache hit
- **Engine eval key:** FEN + depth (different depths produce different results)

### Layer 2: Anthropic Prompt Cache (System Prompt Prefix)

Anthropic's built-in prompt caching stores reusable prefixes server-side. Cache reads cost **90% less** than base input tokens.

```python
response = client.messages.create(
    cache_control={"type": "ephemeral"},  # 5-min TTL, auto-refreshes on hit
    system="<system prompt + imbalances_guide.md + tool definitions>",
    messages=[{"role": "user", "content": f"Analyze: {fen}"}]
)
```

With ~8,000 tokens of static system prompt cached, input cost drops from $0.0246 to $0.003 per request (Sonnet 4.5) — **87.8% savings**.

TTL options: 5-minute (default, 1.25x write cost) or 1-hour (2x write cost). The Agent SDK enables prompt caching automatically with zero configuration.

Pricing (per million tokens, cache read vs base input):

| Model | Base Input | Cache Read | Savings |
|-------|-----------|------------|---------|
| Opus 4.6/4.5 | $5.00 | $0.50 | 90% |
| Sonnet 4.6/4.5/4 | $3.00 | $0.30 | 90% |
| Haiku 4.5 | $1.00 | $0.10 | 90% |

### Layer 3: Full Narrative Cache (FEN + Mode → LLM Response)

Optionally cache Claude's entire narrative analysis keyed by FEN + analysis mode (default/deep).

- **TTL:** Hours to days
- **Trade-off:** Instant response, but "frozen" phrasing. Add a "re-analyze" button to bust cache.
- **Semantic caching bonus:** For natural-language queries, tools like GPTCache or LangChain's RedisSemanticCache find similar cached queries via vector embedding. Useful when users phrase the same question differently.

### Caching by Architecture

| Architecture | Layer 1 (JSON) | Layer 2 (Prompt) | Layer 3 (Narrative) |
|-------------|----------------|------------------|---------------------|
| Plugin | Dict (per session) | Automatic via Agent SDK | N/A (Claude inline) |
| MCP Server | Dict/Redis in server | Automatic via Claude Desktop | Redis by FEN+mode |
| Streamlit App | `@st.cache_data` | `cache_control` on API calls | Redis or `st.cache_data` |
| React + Chessground | Redis/SQLite behind FastAPI | `cache_control` on API calls | Redis + "refresh" button |

---

## Competitive Analysis: Why This Tool Is Different

### The Landscape (March 2026)

Every existing chess analysis tool follows the same architecture: **Engine evaluates → LLM narrates the engine's output.** The LLM is a translator, not a thinker.

| Tool | Approach | Explains WHY? | Uses a Framework? | Imbalance Analysis? |
|------|----------|--------------|-------------------|---------------------|
| DecodeChess | Custom AI on Stockfish | Per-move concepts | No systematic framework | No |
| ChessLogix | Stockfish + GPT-4/Claude | Claims to, no evidence | No | No |
| Lichess | Pure Stockfish | No — pure numbers | No | No |
| Chess.com | Stockfish + rule-based coach | Tactical observations only | No | No |
| ChessMentor AI | Stockfish + Gemini chat | Ad-hoc LLM responses | No | No |
| ChessAgine | MCP bridge to Stockfish | Depends on connected LLM | No | No |
| MattPlaysChess | Stockfish + Claude narrative | Game-flow narrative | No | No |
| **This project** | **board_utils.py + Claude** | **Systematic positional assessment** | **Silman's 10 imbalances + BFIH** | **Yes — the only one** |

### What No One Has Built

No tool provides systematic positional assessment through a strategic framework. The Silman imbalance methodology exists only as a human thinking process taught through books and coaching. Every tool works at the *move level* ("this move is good/bad because..."), none at the *position level* ("this position favors White because of these specific imbalances, therefore the plan should be...").

### Academic Validation

"Bridging the Gap between Expert and Language Models" (NAACL 2025) found:
- GPT-4o alone: **36% correctness** in chess commentary
- With engine guidance: **43%**
- With structured concept extraction first: **60%** — matching human reference

The paper's conclusion validates this project's architecture: you must extract positional concepts *before* the LLM interprets them. `board_utils.py` producing structured JSON is exactly the approach the research says is necessary.

### What BFIH Adds

Every existing tool presents its assessment as fact. But positional assessment is genuinely ambiguous — a space advantage might be strength or overextension, a pawn majority might be an asset or liability. BFIH deep mode does what no chess tool has attempted:

1. **Competing hypotheses** — 2-4 genuinely competing positional assessments with probability assignments
2. **Paradigm inversion** — forced argument for the opposite conclusion, not as straw man
3. **Evidence matrix** — each imbalance explicitly mapped to each hypothesis
4. **Reflexive review** — metacognition about the analysis itself ("Am I anchored by the engine number?")
5. **Discomfort heuristic** — quality check on intellectual honesty

The output is not "here's the answer." It's "here's how to think about this position, including the strongest case against my conclusion."

### The Gap

The market gap isn't "better engine eval" — Stockfish is superhuman. The gap is **positional thinking as a skill**. Every chess improvement book says you get better by learning to assess positions and form plans. Every software tool gives you engine lines instead. This tool is a chess *thinking* tool. Everyone else built chess *answering* tools.

---

## Key Constraints

- Agent SDK requires an Anthropic API key — you can't redistribute Claude Code's rate limits
- Anthropic prohibits branding Agent SDK apps as "Claude Code" — must use your own branding
- Skills with Python dependencies (like python-chess) need documented install steps or plugin hooks for auto-install
- There is no official "Share" button for skills yet — [community has asked for this](https://every.to/vibe-check/vibe-check-claude-skills-need-a-share-button)
- The [AgentSkills.io](https://agentskills.io) open standard means skills work across Claude Code, Cursor, Codex, Gemini CLI, Aider, Windsurf, and 5+ other tools
