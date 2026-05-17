import { useState } from "react";
import { previewSvgUrl } from "@/api/drafts";
import { Button } from "@/components/ui/button";
import { ZoomablePreviewModal } from "@/components/ui/ZoomablePreviewModal";

interface Props {
  draftId: string;
  draftName: string;
  warpThreads?: number;
  weftThreads?: number;
  onClose: () => void;
}

// Drafts above this thread-area threshold get a load-confirmation gate.
// 400k threads ≈ 800 warp × 500 weft — produces a noticeably large SVG.
const LARGE_DRAFT_THRESHOLD = 400_000;

export function DraftPreviewModal({ draftId, draftName, warpThreads = 0, weftThreads = 0, onClose }: Props) {
  const isLarge = warpThreads * weftThreads > LARGE_DRAFT_THRESHOLD;
  const [confirmed, setConfirmed] = useState(!isLarge);

  const gate = (
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
  );

  return (
    <ZoomablePreviewModal
      src={previewSvgUrl(draftId)}
      title={draftName}
      onClose={onClose}
      gateConfirmed={confirmed}
      gate={gate}
    />
  );
}
