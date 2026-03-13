/** Classification color badge for critical moments. */

const CLASS_MAP: Record<string, string> = {
  blunder: "badge-blunder",
  mistake: "badge-mistake",
  inaccuracy: "badge-inaccuracy",
  good: "badge-good",
  excellent: "badge-excellent",
  best: "badge-best",
};

interface Props {
  classification: string;
  small?: boolean;
}

export function MomentBadge({ classification, small }: Props) {
  const cls = CLASS_MAP[classification] ?? "";
  const size = small ? 8 : 12;

  return (
    <span
      className={cls}
      style={{
        display: "inline-block",
        width: size,
        height: size,
        borderRadius: "50%",
        verticalAlign: "middle",
        boxShadow: "0 0 4px rgba(0,0,0,0.4)",
      }}
      title={classification}
    />
  );
}
