import { useCallback, useEffect, useRef, useState } from "react";
import { getAuthToken } from "@/api/client";
import { AppIcons } from "@/lib/icons";
import { Button } from "@/components/ui/button";

interface Props {
  src: string;
  title: string;
  onClose: () => void;
  /** When false, renders `gate` content instead of loading the image. */
  gateConfirmed?: boolean;
  /** Content shown when gateConfirmed is false (e.g. large-draft warning). */
  gate?: React.ReactNode;
}

const ZOOM_STEP = 0.25;
const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4;
const ZOOM_DEFAULT = 1;

export function ZoomablePreviewModal({ src, title, onClose, gateConfirmed = true, gate }: Props) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [naturalDims, setNaturalDims] = useState({ w: 0, h: 0 });
  const [zoom, setZoom] = useState(ZOOM_DEFAULT);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const objectUrlRef = useRef<string | null>(null);

  const clampZoom = (z: number) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z));

  const computeFitZoom = useCallback(() => {
    const el = scrollRef.current;
    if (!el || !naturalDims.w || !naturalDims.h) return ZOOM_DEFAULT;
    const pad = 32; // p-4 on each side
    return clampZoom(Math.min(
      (el.clientWidth - pad) / naturalDims.w,
      (el.clientHeight - pad) / naturalDims.h,
    ));
   
  }, [naturalDims]);

  useEffect(() => {
    if (!gateConfirmed) return;
    let cancelled = false;
    async function load() {
      try {
        const token = await getAuthToken();
        const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
        const res = await fetch(src, { headers, credentials: "include" });
        if (!res.ok) throw new Error(`Failed to load preview (${res.status})`);
        const blob = await res.blob();
        if (cancelled) return;
        if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
        const url = URL.createObjectURL(blob);
        objectUrlRef.current = url;
        setBlobUrl(url);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Preview unavailable");
      }
    }
    load();
    return () => {
      cancelled = true;
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    };
  }, [src, gateConfirmed]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "0" && blobUrl) setZoom(computeFitZoom());
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, blobUrl, computeFitZoom]);

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-black/60"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="flex flex-col w-full h-full max-w-7xl mx-auto bg-background shadow-xl rounded-none sm:rounded-lg sm:my-6 sm:h-[calc(100vh-3rem)] overflow-hidden">

        {/* Toolbar */}
        <div className="flex items-center gap-2 px-4 py-2 border-b bg-card shrink-0">
          <span className="text-sm font-medium truncate flex-1">{title}</span>

          {blobUrl && (
            <div className="flex items-center gap-1">
              <Button
                variant="ghost" size="icon" className="h-8 w-8"
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
                variant="ghost" size="icon" className="h-8 w-8"
                onClick={() => setZoom((z) => clampZoom(z + ZOOM_STEP))}
                disabled={zoom >= ZOOM_MAX}
                title="Zoom in"
              >
                <AppIcons.zoomIn className="h-4 w-4" />
              </Button>

              <Button
                variant="ghost" size="icon" className="h-8 w-8"
                onClick={() => setZoom(computeFitZoom())}
                title="Zoom to fit (0)"
              >
                <AppIcons.zoomFit className="h-4 w-4" />
              </Button>

              <Button
                variant="ghost" size="icon" className="h-8 w-8"
                onClick={() => setZoom(ZOOM_DEFAULT)}
                disabled={zoom === ZOOM_DEFAULT}
                title="Reset zoom (100%)"
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
          {!gateConfirmed && gate}

          {gateConfirmed && error && (
            <div className="flex items-center justify-center h-full">
              <p className="text-sm text-destructive">{error}</p>
            </div>
          )}

          {gateConfirmed && !error && !blobUrl && (
            <div className="flex items-center justify-center h-full">
              <p className="text-sm text-muted-foreground">Loading preview…</p>
            </div>
          )}

          {blobUrl && (
            <img
              src={blobUrl}
              alt="Preview"
              onLoad={(e) => {
                const img = e.currentTarget;
                if (img.naturalWidth && img.naturalHeight) {
                  setNaturalDims({ w: img.naturalWidth, h: img.naturalHeight });
                }
              }}
              style={{
                width: naturalDims.w ? naturalDims.w * zoom : undefined,
                height: naturalDims.h ? naturalDims.h * zoom : undefined,
                imageRendering: "pixelated",
                display: "block",
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
