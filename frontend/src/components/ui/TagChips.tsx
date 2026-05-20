interface Props {
  tags: string[];
  max?: number;
  className?: string;
}

export function TagChips({ tags, max = 3, className = "" }: Props) {
  if (!tags.length) return null;
  const visible = tags.slice(0, max);
  const overflow = tags.length - max;
  return (
    <div className={`flex flex-wrap gap-1 ${className}`}>
      {visible.map((t) => (
        <span key={t} className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
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
