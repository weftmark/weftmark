interface Props {
  tags: string[];
  max?: number;
  className?: string;
}

function tagColor(tag: string): { background: string; color: string } {
  let h = 0;
  for (let i = 0; i < tag.length; i++) h = (h * 31 + tag.charCodeAt(i)) >>> 0;
  const hue = h % 360;
  return {
    background: `hsl(${hue}, 60%, 88%)`,
    color: `hsl(${hue}, 55%, 30%)`,
  };
}

export function TagChips({ tags, max = 3, className = "" }: Props) {
  if (!tags.length) return null;
  const visible = tags.slice(0, max);
  const overflow = tags.length - max;
  return (
    <div className={`flex flex-wrap gap-1 ${className}`}>
      {visible.map((t) => (
        <span key={t} className="rounded px-1.5 py-0.5 text-xs font-medium" style={tagColor(t)}>
          {t}
        </span>
      ))}
      {overflow > 0 && (
        <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
          +{overflow}
        </span>
      )}
    </div>
  );
}
