import { useEffect, useRef, useState } from "react";
import { getAuthToken } from "@/api/client";
import { previewSvgUrl } from "@/api/drafts";
import { AppIcons } from "@/lib/icons";
import { Button } from "@/components/ui/button";

interface Props {
  draftId: string;
  draftName: string;
  warpThreads?: number;
  weftThreads?: number;
  onClose: () => void;
}

const ZOOM_STEP = 0.25;
const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4;
const ZOOM_DEFAULT = 1;

// Drafts above this thread-area threshold get a load-confirmation gate.
// 400k threads ≈ 800 warp × 500 weft — produces a noticeably large SVG.
const LARGE_DRAFT_THRESHOLD = 400_000;

function parseSvgDimensions(svg: string): { w: number; h: number } {
  const m = svg.match(/width="(\d+(?:\.\d+)?)"[^>]*height="(\d+(?:\.\d+)?)"/);
  return m ? { w: parseFloat(m[1]), h: parseFloat(m[2]) } : { w: 800, h: 600 };
}

export function DraftPreviewModal({ draftId, draftName, warpThreads = 0, weftThreads = 0, onClose }: Props) {
  const isLarge = warpThreads * weftThreads > LARGE_DRAFT_THRESHOLD;
  const [confirmed, setConfirmed] = useState(!isLarge);
  const [svgContent, setSvgContent] = useState<string | null>(null);
  const [naturalDims, setNaturalDims] = useState({ w: 0, h: 0 });
  const [zoom, setZoom] = useState(ZOOM_DEFAULT);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!confirmed) return;
    let cancelled = false;
    async function load() {
      try {
        const token = await getAuthToken();
        const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
        const res = await fetch(previewSvgUrl(draftId), { headers, credentials: "include" });
        if (!res.ok) throw new Error(`Failed to load preview (${res.status})`);
        const text = await res.text();
        if (cancelled) return;
        const dims = parseSvgDimensions(text);
        // Replace width/height attrs so SVG fills its wrapper div
        const patched = text
          .replace(/(<svg[^>]*)\bwidth="[^"]*"/, '$1width="100%"')
          .replace(/(<svg[^>]*)\bheight="[^"]*"/, '$1height="100%"');
        setNaturalDims(dims);
        setSvgContent(patched);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Preview unavailable");
      }
    }
    load();
    return () => { cancelled = true; };
  }, [draftId, confirmed]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const clampZoom = (z: number) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z));

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-black/60"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="flex flex-col w-full h-full max-w-7xl mx-auto bg-background shadow-xl rounded-none sm:rounded-lg sm:my-6 sm:h-[calc(100vh-3rem)] overflow-hidden">

        {/* Toolbar */}
        <div className="flex items-center gap-2 px-4 py-2 border-b bg-card shrink-0">
          <span className="text-sm font-medium truncate flex-1">{draftName}</span>

          {svgContent && (
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => setZoom((z) => clampZoom(z - ZOOM_STEP))}
                disabled={zoom <= ZOOM_MIN}
                title="Zoom out"
              >
                <AppIcons.zoomOut className="h-4 w-4" />
              </Button>

              <span className="w-12 text-center text-sm tabular-nums select-none">
                {Math.round(zoom * 100)}%
              </span>

              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => setZoom((z) => clampZoom(z + ZOOM_STEP))}
                disabled={zoom >= ZOOM_MAX}
                title="Zoom in"
              >
                <AppIcons.zoomIn className="h-4 w-4" />
              </Button>

              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => setZoom(ZOOM_DEFAULT)}
                disabled={zoom === ZOOM_DEFAULT}
                title="Reset zoom"
              >
                <AppIcons.zoomReset className="h-4 w-4" />
              </Button>
            </div>
          )}

          <Button variant="ghost" size="icon" className="h-8 w-8 ml-1" onClick={onClose} title="Close">
            <AppIcons.close className="h-4 w-4" />
          </Button>
        </div>

        {/* Content */}
        <div ref={scrollRef} className="flex-1 overflow-auto bg-muted/30 p-4">
          {!confirmed && (
            <div className="flex items-center justify-center h-full">
              <div className="max-w-sm rounded-lg border bg-card p-6 text-center space-y-4">
                <p className="text-sm font-medium">Large design</p>
                <p className="text-sm text-muted-foreground">
                  This design has {warpThreads.toLocaleString()} warp &times; {weftThreads.toLocaleString()} weft threads.
                  The interactive preview may be slow to load, especially on mobile.
                </p>
                <div className="flex justify-center gap-3">
                  <Button size="sm" onClick={() => setConfirmed(true)}>Load preview</Button>
                  <Button size="sm" variant="outline" onClick={onClose}>Cancel</Button>
                </div>
              </div>
            </div>
          )}

          {confirmed && error && (
            <div className="flex items-center justify-center h-full">
              <p className="text-sm text-destructive">{error}</p>
            </div>
          )}

          {confirmed && !error && !svgContent && (
            <div className="flex items-center justify-center h-full">
              <p className="text-sm text-muted-foreground">Loading preview…</p>
            </div>
          )}

          {svgContent && (
            <div
              style={{
                width: naturalDims.w * zoom,
                height: naturalDims.h * zoom,
                minWidth: naturalDims.w * zoom,
              }}
              dangerouslySetInnerHTML={{ __html: svgContent }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
