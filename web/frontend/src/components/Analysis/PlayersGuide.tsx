/** Player's Guide — coach-voice narrative (placeholder for Phase 5). */

interface Props {
  content: string;
  streaming: boolean;
}

export function PlayersGuide({ content, streaming }: Props) {
  if (!content && !streaming) {
    return (
      <div style={{ color: "#888", padding: 12 }}>
        Click "Analyze" to get a coach-style analysis.
      </div>
    );
  }

  return (
    <div style={{ padding: 12, fontSize: 14, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
      {content}
      {streaming && <span style={{ animation: "blink 1s infinite" }}>|</span>}
    </div>
  );
}
