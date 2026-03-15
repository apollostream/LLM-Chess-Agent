/**
 * Open a print-friendly popout of rendered markdown analysis.
 * For synopsis mode, injects board diagrams at each critical moment.
 */

import type { CriticalMoment } from "../api/types";

const PRINT_CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Inter', -apple-system, system-ui, sans-serif;
    font-size: 14px;
    line-height: 1.75;
    color: #1a1a2e;
    max-width: 760px;
    margin: 0 auto;
    padding: 40px 24px;
    background: #fff;
  }

  h1 { font-size: 24px; font-weight: 700; margin: 24px 0 12px; color: #1a1a2e; }
  h2 { font-size: 19px; font-weight: 600; margin: 20px 0 10px; color: #c9a227; }
  h3 { font-size: 16px; font-weight: 600; margin: 16px 0 8px; color: #1a1a2e; }
  h4 { font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; margin: 14px 0 6px; }

  p { margin: 8px 0; }
  strong, b { color: #1a1a2e; }
  em { font-style: italic; color: #555; }

  ul, ol { margin: 6px 0; padding-left: 22px; }
  li { margin: 3px 0; }

  code {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    background: #f5f5f0;
    border: 1px solid #e0ddd4;
    border-radius: 3px;
    padding: 1px 5px;
  }

  pre {
    background: #f5f5f0;
    border: 1px solid #e0ddd4;
    border-radius: 6px;
    padding: 12px 16px;
    overflow-x: auto;
    margin: 10px 0;
  }
  pre code { background: none; border: none; padding: 0; }

  table {
    border-collapse: collapse;
    width: 100%;
    margin: 10px 0;
    font-size: 13px;
  }
  th {
    text-align: left;
    font-weight: 600;
    color: #c9a227;
    border-bottom: 2px solid #e0ddd4;
    padding: 6px 10px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  td {
    padding: 5px 10px;
    border-bottom: 1px solid #eee;
  }

  hr { border: none; border-top: 1px solid #e0ddd4; margin: 16px 0; }

  blockquote {
    border-left: 3px solid #c9a227;
    margin: 10px 0;
    padding: 4px 14px;
    color: #555;
  }

  .board-figure {
    text-align: center;
    margin: 20px auto;
    page-break-inside: avoid;
  }
  .board-figure img {
    max-width: 360px;
    border: 1px solid #e0ddd4;
    border-radius: 4px;
  }
  .board-figure figcaption {
    font-size: 12px;
    color: #777;
    margin-top: 6px;
    font-style: italic;
  }

  .report-header {
    border-bottom: 2px solid #c9a227;
    padding-bottom: 12px;
    margin-bottom: 24px;
  }
  .report-header h1 { margin: 0 0 4px; }
  .report-meta {
    font-size: 12px;
    color: #777;
  }

  @media print {
    body { padding: 0; max-width: none; }
    .board-figure { page-break-inside: avoid; }
    h2, h3 { page-break-after: avoid; }
  }
`;

/** Build board figure HTML for a critical moment. */
function boardFigure(m: CriticalMoment): string {
  const fen = encodeURIComponent(m.fen_before);
  const dots = m.side === "black" ? "..." : ".";
  const label = `${m.move_number}${dots}${m.san}`;
  return `<figure class="board-figure">` +
    `<img src="/api/v1/board.svg?fen=${fen}&size=360" alt="Position before ${label}" />` +
    `<figcaption>Before ${label} (${m.classification})</figcaption>` +
    `</figure>`;
}

/**
 * Build markdown with board images injected for synopsis mode.
 * Inserts board diagram markdown before each critical moment's section.
 */
export function injectBoardMarkdown(md: string, moments: CriticalMoment[]): string {
  if (moments.length === 0) return md;

  // Strategy: split markdown into lines, find paragraphs that first mention
  // each critical moment's move number, and insert a board image after that paragraph.
  const lines = md.split("\n");
  const result: string[] = [];
  const pendingMoments = new Map<number, CriticalMoment>();
  for (const m of moments) {
    pendingMoments.set(m.move_number, m);
  }

  for (let i = 0; i < lines.length; i++) {
    result.push(lines[i]);

    // Check if this line references a pending moment's move number
    // and the next line is empty (paragraph boundary)
    const nextIsBlank = i + 1 >= lines.length || lines[i + 1].trim() === "";
    if (nextIsBlank && lines[i].trim()) {
      for (const [moveNum, m] of pendingMoments) {
        const dots = m.side === "black" ? "\\.\\.\\." : "\\.";
        const pat = new RegExp(`\\b${moveNum}${dots}|[Mm]ove\\s+${moveNum}\\b`);
        if (pat.test(lines[i])) {
          const fen = encodeURIComponent(m.fen_before);
          const label = `${m.move_number}${m.side === "black" ? "..." : "."}${m.san}`;
          result.push("");
          result.push(`![Before ${label} (${m.classification})](/api/v1/board.svg?fen=${fen}&size=360)`);
          pendingMoments.delete(moveNum);
          break;
        }
      }
    }
  }

  // Any remaining moments that weren't matched — append at end
  for (const [, m] of pendingMoments) {
    const fen = encodeURIComponent(m.fen_before);
    const label = `${m.move_number}${m.side === "black" ? "..." : "."}${m.san}`;
    result.push("");
    result.push(`![Before ${label} (${m.classification})](/api/v1/board.svg?fen=${fen}&size=360)`);
  }

  return result.join("\n");
}

interface ExportOptions {
  markdown: string;
  mode: string;
  title?: string;
  moments?: CriticalMoment[];
}

export function openReport({ markdown, mode, title }: ExportOptions): void {
  const modeLabel =
    mode === "guide" ? "Player's Guide" :
    mode === "deep" ? "Deep Analysis (BFIH)" :
    mode === "synopsis" ? "Game Synopsis" : "Analysis";

  const reportTitle = title || modeLabel;
  const dateStr = new Date().toLocaleDateString("en-US", {
    year: "numeric", month: "long", day: "numeric",
  });

  // Board images are already injected into the markdown by the caller (App.tsx claudeContent memo),
  // so no need to re-inject here.
  const finalMarkdown = markdown;

  const escapedMd = JSON.stringify(finalMarkdown);

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${reportTitle} — Chess Imbalances</title>
  <style>${PRINT_CSS}</style>
  <script src="https://cdn.jsdelivr.net/npm/marked@15/marked.min.js"><\/script>
</head>
<body>
  <div class="report-header">
    <h1>${reportTitle}</h1>
    <div class="report-meta">${modeLabel} &middot; ${dateStr} &middot; Chess Imbalances — Silman's Framework</div>
  </div>
  <div id="content"></div>
  <script>
    document.getElementById('content').innerHTML = marked.parse(${escapedMd});
  <\/script>
</body>
</html>`;

  const win = window.open("", "_blank");
  if (!win) return;
  win.document.write(html);
  win.document.close();
}
