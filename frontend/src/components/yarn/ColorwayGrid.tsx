import { formatColorwayLabel, type RavelryColorway } from "@/api/ravelry";

interface ColorwayGridProps {
  readonly colorways: readonly RavelryColorway[];
  readonly selectedColorway: RavelryColorway | null;
  readonly onPick: (cw: RavelryColorway) => void;
  readonly className?: string;
}

export function ColorwayGrid({ colorways, selectedColorway, onPick, className = "grid grid-cols-3 gap-1.5" }: ColorwayGridProps) {
  return (
    <div className={className}>
      {colorways.map((cw) => (
        <button
          key={cw.id}
          type="button"
          className={`text-left rounded-md border p-1.5 text-xs transition-colors ${
            selectedColorway?.id === cw.id
              ? "border-ring bg-accent/10 text-accent"
              : "border-border hover:border-ring text-card-foreground"
          }`}
          onClick={() => onPick(cw)}
        >
          {cw.photos?.[0]?.square_url && (
            <img src={cw.photos[0].square_url} alt={cw.name} className="h-10 w-full rounded object-cover mb-1" />
          )}
          <span className="truncate block leading-tight">{formatColorwayLabel(cw)}</span>
        </button>
      ))}
    </div>
  );
}
