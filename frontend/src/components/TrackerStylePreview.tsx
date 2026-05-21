export type TrackerStyle = "default" | "compact" | "high_contrast";

// ── Static style-picker preview (small, used in the card selector) ──────────

const DEMO_ACTIVE = [1, 3];
const DEMO_SHAFTS = 4;
const DEMO_WEFT = "#b45309";
const DEMO_PICK = 7;
const DEMO_TOTAL = 18;

function DemoBox({ n, active, style }: { n: number; active: boolean; style: TrackerStyle }) {
  const base = "rounded flex items-center justify-center font-bold text-[11px] border-2";
  if (style === "high_contrast") {
    return (
      <div className={`${base} ${active ? "bg-foreground border-foreground text-background" : "border-muted-foreground/50 bg-muted/40 text-muted-foreground"}`}>
        {n}
      </div>
    );
  }
  return (
    <div className={`${base} ${active ? "bg-primary border-primary text-primary-foreground" : "border-border bg-muted/60 text-foreground/70"}`}>
      {n}
    </div>
  );
}

function DemoPickCard({ compact, style }: { compact?: boolean; style: TrackerStyle }) {
  const height = compact ? "h-10" : "h-16";
  const border = style === "high_contrast"
    ? compact ? "border border-foreground/30" : "border-2 border-foreground/50"
    : compact ? "border border-primary/20" : "border-2 border-primary/30";
  const bg = style === "high_contrast" ? "bg-muted/60" : "bg-primary/5 dark:bg-primary/10";

  return (
    <div className={`rounded-lg ${bg} ${border} ${height} px-2 py-1.5 flex items-stretch gap-2`}>
      <div className="flex-1 grid gap-0.5" style={{ gridTemplateColumns: `repeat(${DEMO_SHAFTS}, 1fr)` }}>
        {Array.from({ length: DEMO_SHAFTS }, (_, i) => i + 1).map((n) => (
          <DemoBox key={n} n={n} active={DEMO_ACTIVE.includes(n)} style={style} />
        ))}
      </div>
      {!compact && <div className="w-4 shrink-0 rounded" style={{ backgroundColor: DEMO_WEFT }} />}
    </div>
  );
}

export function TrackerStylePreview({ style }: { style: TrackerStyle }) {
  const isCompact = style === "compact";
  const isHighContrast = style === "high_contrast";

  return (
    <div className="pointer-events-none select-none space-y-1.5 p-3 rounded-lg bg-muted/30 border border-border/50">
      {!isCompact && (
        <>
          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
            <div className={`h-full rounded-full ${isHighContrast ? "bg-foreground" : "bg-primary"}`} style={{ width: `${(DEMO_PICK / DEMO_TOTAL) * 100}%` }} />
          </div>
          <div className="text-center font-semibold text-xs text-muted-foreground">
            Pick {DEMO_PICK} / {DEMO_TOTAL}
          </div>
        </>
      )}
      <div className="grid grid-cols-[1fr_2fr_1fr] gap-1 items-center">
        <DemoPickCard compact style={style} />
        <DemoPickCard style={style} />
        <DemoPickCard compact style={style} />
      </div>
      {!isCompact && (
        <div className="rounded bg-muted/50 p-1 overflow-hidden">
          <div className="grid gap-px" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
            {Array.from({ length: 4 }, (_, row) =>
              Array.from({ length: 4 }, (__, col) => {
                const lit = (row + col) % 2 === 0;
                return (
                  <div
                    key={`${row}-${col}`}
                    className={`h-2 rounded-sm ${lit ? (isHighContrast ? "bg-foreground/70" : "bg-primary/60") : "bg-muted-foreground/15"}`}
                  />
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Live tracker preview (full-width, reflects current toggle settings) ──────

const LIVE_SHAFTS_ALL = 8;   // total shafts on the loom
const LIVE_SHAFTS_USED = 4;  // shafts actually used by the design (trailing 4 are "unused")
const LIVE_ACTIVE = [1, 3];
const LIVE_WEFT = "#b45309";
const LIVE_PICK = 12;
const LIVE_TOTAL = 32;
const LIVE_PROGRESS = LIVE_PICK / LIVE_TOTAL;

type ColorMode = "theme" | "strip" | "filled";

function LiveBox({
  n,
  active,
  unused,
  colorMode,
  style,
}: {
  n: number;
  active: boolean;
  unused: boolean;
  colorMode: ColorMode;
  style: TrackerStyle;
}) {
  const base = "rounded-md border-2 flex flex-col items-center justify-center font-bold overflow-hidden";
  const fontSize = "text-sm";

  // Unused shafts: clearly distinct — dashed border, no background, very faint text
  if (unused) {
    return (
      <div
        className={`${base} border-dashed ${style === "high_contrast" ? "border-muted-foreground/30 text-muted-foreground/30" : "border-border/40 text-foreground/25"}`}
        style={{ borderStyle: "dashed" }}
      >
        <span className={fontSize}>{n}</span>
      </div>
    );
  }

  if (active && colorMode === "filled") {
    return (
      <div className={`${base}`} style={{ backgroundColor: LIVE_WEFT, borderColor: LIVE_WEFT }}>
        <span className={fontSize} style={{ color: "#fff" }}>{n}</span>
      </div>
    );
  }
  if (active && colorMode === "strip") {
    return (
      <div className={`${base} ${style === "high_contrast" ? "bg-foreground border-foreground" : "bg-primary border-primary"}`}>
        <span className={`${fontSize} ${style === "high_contrast" ? "text-background" : "text-primary-foreground"} flex-1 flex items-center justify-center w-full`}>{n}</span>
        <div className="h-[18%] w-full shrink-0" style={{ backgroundColor: LIVE_WEFT }} />
      </div>
    );
  }
  if (active) {
    return (
      <div className={`${base} ${style === "high_contrast" ? "bg-foreground border-foreground text-background" : "bg-primary border-primary text-primary-foreground"}`}>
        <span className={fontSize}>{n}</span>
      </div>
    );
  }
  return (
    <div className={`${base} ${style === "high_contrast" ? "border-muted-foreground/60 bg-muted/50 text-muted-foreground" : "border-border bg-muted/60 text-foreground/60"}`}>
      <span className={fontSize}>{n}</span>
    </div>
  );
}

function LivePickCard({
  compact,
  style,
  colorMode,
  showWeftColor,
  shaftCount,
}: {
  compact?: boolean;
  style: TrackerStyle;
  colorMode: ColorMode;
  showWeftColor: boolean;
  shaftCount: number;
}) {
  const height = compact ? "h-14" : "h-24";
  const border = style === "high_contrast"
    ? compact ? "border border-foreground/30" : "border-2 border-foreground/40"
    : compact ? "border border-primary/20" : "border-2 border-primary/30";
  const bg = style === "high_contrast" ? "bg-muted/60" : "bg-primary/5 dark:bg-primary/10";

  return (
    <div className={`rounded-xl ${bg} ${border} ${height} px-3 py-2 flex flex-col gap-1.5`}>
      <div className="flex-1 grid gap-1" style={{ gridTemplateColumns: `repeat(${shaftCount}, 1fr)` }}>
        {Array.from({ length: shaftCount }, (_, i) => i + 1).map((n) => (
          <LiveBox
            key={n}
            n={n}
            active={!compact && LIVE_ACTIVE.includes(n)}
            unused={n > LIVE_SHAFTS_USED}
            colorMode={compact ? "theme" : colorMode}
            style={style}
          />
        ))}
      </div>
      {!compact && showWeftColor && (
        <div
          className="h-5 w-full shrink-0 rounded-md flex items-center justify-center text-[10px] font-semibold uppercase tracking-wider"
          style={{ backgroundColor: LIVE_WEFT, color: "#fff" }}
        >
          Weft
        </div>
      )}
    </div>
  );
}

export function TrackerLivePreview({
  style,
  colorMode,
  showProgress,
  showDrawdown,
  showWeftColor,
  showPickCards,
  hideUnusedShafts,
}: {
  style: TrackerStyle;
  colorMode: string;
  showProgress: boolean;
  showDrawdown: boolean;
  showWeftColor: boolean;
  showPickCards: boolean;
  hideUnusedShafts: boolean;
}) {
  const isHighContrast = style === "high_contrast";
  const cm = (colorMode as ColorMode) ?? "strip";
  const shaftCount = hideUnusedShafts ? LIVE_SHAFTS_USED : LIVE_SHAFTS_ALL;

  return (
    <div className="pointer-events-none select-none rounded-xl border-2 border-dashed border-border bg-background p-4 space-y-3">
      {/* Header label */}
      <p className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground/60 text-center">Preview</p>

      {/* Progress bar */}
      {showProgress && (
        <div className="space-y-1">
          <div className="flex justify-between text-[10px] text-muted-foreground">
            <span>Pick {LIVE_PICK}</span>
            <span>{LIVE_TOTAL} picks</span>
          </div>
          <div className={`h-2 rounded-full ${isHighContrast ? "bg-foreground/20" : "bg-muted"} overflow-hidden`}>
            <div
              className={`h-full rounded-full transition-all ${isHighContrast ? "bg-foreground" : "bg-primary"}`}
              style={{ width: `${LIVE_PROGRESS * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* Pick number */}
      <div className="text-center">
        <span className={`text-xs font-semibold ${isHighContrast ? "text-foreground" : "text-muted-foreground"}`}>
          Pick {LIVE_PICK} / {LIVE_TOTAL}
        </span>
      </div>

      {/* Pick cards */}
      {showPickCards ? (
        <div className="grid grid-cols-[1fr_2fr_1fr] gap-2 items-center">
          <div>
            <p className="text-[9px] text-muted-foreground text-center mb-1">← Pick {LIVE_PICK - 1}</p>
            <LivePickCard compact style={style} colorMode={cm} showWeftColor={false} shaftCount={shaftCount} />
          </div>
          <LivePickCard style={style} colorMode={cm} showWeftColor={showWeftColor} shaftCount={shaftCount} />
          <div>
            <p className="text-[9px] text-muted-foreground text-center mb-1">Pick {LIVE_PICK + 1} →</p>
            <LivePickCard compact style={style} colorMode={cm} showWeftColor={false} shaftCount={shaftCount} />
          </div>
        </div>
      ) : (
        <LivePickCard style={style} colorMode={cm} showWeftColor={showWeftColor} shaftCount={shaftCount} />
      )}

      {/* Shaft count note when hiding unused */}
      {hideUnusedShafts && shaftCount < LIVE_SHAFTS_ALL && (
        <p className="text-[9px] text-muted-foreground text-center">
          {LIVE_SHAFTS_ALL - shaftCount} unused shaft{LIVE_SHAFTS_ALL - shaftCount !== 1 ? "s" : ""} hidden
        </p>
      )}

      {/* Drawdown pattern */}
      {showDrawdown && (
        <div className="space-y-1">
          <p className="text-[9px] text-muted-foreground uppercase tracking-wide">Drawdown</p>
          <div className="rounded-lg border border-border bg-muted/30 p-2 overflow-hidden">
            <div className="grid gap-px" style={{ gridTemplateColumns: `repeat(${shaftCount}, 1fr)` }}>
              {Array.from({ length: 4 }, (_, row) =>
                Array.from({ length: shaftCount }, (__, col) => {
                  const shaftNum = col + 1;
                  const isUnused = shaftNum > LIVE_SHAFTS_USED;
                  const lit = !isUnused && (row + col) % 2 === 0;
                  return (
                    <div
                      key={`${row}-${col}`}
                      className={`h-3 rounded-sm ${
                        isUnused
                          ? "bg-muted-foreground/8 border border-dashed border-border/30"
                          : lit
                            ? (isHighContrast ? "bg-foreground/80" : "bg-primary/70")
                            : "bg-muted-foreground/15"
                      }`}
                    />
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
