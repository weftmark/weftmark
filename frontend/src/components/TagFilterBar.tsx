import type { ReactNode } from "react";

interface TagFilterBarProps {
  readonly tags: string[];
  readonly activeTag: string | null;
  readonly onToggle: (tag: string) => void;
  readonly onClear: () => void;
  readonly clearLabel: string;
  readonly className?: string;
  readonly clearIcon: ReactNode;
}

export function TagFilterBar({ tags, activeTag, onToggle, onClear, clearLabel, className, clearIcon }: TagFilterBarProps) {
  if (tags.length === 0) return null;

  return (
    <div className={`flex flex-wrap gap-1.5${className ? ` ${className}` : ""}`}>
      {tags.map((tag) => (
        <button
          key={tag}
          type="button"
          onClick={() => onToggle(tag)}
          className={`rounded-full px-2.5 py-0.5 text-xs transition-colors ${
            activeTag === tag
              ? "bg-accent text-accent-foreground"
              : "bg-muted text-muted-foreground hover:bg-accent/20"
          }`}
        >
          {tag}
        </button>
      ))}
      {activeTag && (
        <button
          type="button"
          onClick={onClear}
          className="rounded-full px-2 py-0.5 text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
        >
          {clearIcon} {clearLabel}
        </button>
      )}
    </div>
  );
}
