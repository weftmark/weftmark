import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { updateProjectShare, revokeProjectShare, type ProjectDetail } from "@/api/projects";
import { AppIcons } from "@/lib/icons";
import { Button } from "@/components/ui/button";

export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.cssText = "position:fixed;opacity:0;top:0;left:0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  }
}

export function ShareModal({
  project,
  onUpdated,
  onClose,
}: {
  project: ProjectDetail;
  onUpdated: (updated: ProjectDetail) => void;
  onClose: () => void;
}) {
  const [expiryDays, setExpiryDays] = useState<string>("30");
  const [copied, setCopied] = useState(false);

  const hasSlug = !!project.share_slug && project.share_visibility !== "private";
  const shareUrl = hasSlug ? `${window.location.origin}/p/${project.share_slug}` : null;

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const shareMutation = useMutation({
    mutationFn: () => {
      const days = parseInt(expiryDays, 10);
      const expires =
        !isNaN(days) && days > 0
          ? new Date(Date.now() + days * 86_400_000).toISOString()
          : null;
      return updateProjectShare(project.id, "link", expires);
    },
    onSuccess: onUpdated,
  });

  const revokeMutation = useMutation({
    mutationFn: () => revokeProjectShare(project.id),
    onSuccess: () => {
      onUpdated({ ...project, share_slug: null, share_visibility: "private", share_expires_at: null });
      onClose();
    },
  });

  async function handleCopy() {
    if (!shareUrl) return;
    const ok = await copyToClipboard(shareUrl);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } else {
      alert(`Copy this URL:\n${shareUrl}`);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-card rounded-xl border border-border shadow-2xl flex flex-col max-w-md w-full">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h2 className="font-semibold text-sm flex items-center gap-2">
            <AppIcons.share className="h-4 w-4" />
            Share project
          </h2>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
            aria-label="Close"
          >
            <AppIcons.close className="h-4 w-4" />
          </button>
        </div>

        <div className="p-4 space-y-4">
          {hasSlug && shareUrl ? (
            <>
              <div className="flex items-center gap-2">
                <input
                  readOnly
                  value={shareUrl}
                  className="flex-1 rounded border border-border bg-muted px-2 py-1.5 text-xs font-mono text-muted-foreground select-all min-w-0"
                  onClick={(e) => (e.target as HTMLInputElement).select()}
                />
                <Button variant="outline" size="sm" onClick={handleCopy} className="shrink-0 min-w-[72px]">
                  {copied ? (
                    "Copied!"
                  ) : (
                    <>
                      <AppIcons.copyLink className="h-3.5 w-3.5 mr-1" />
                      Copy
                    </>
                  )}
                </Button>
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>Anyone with the link</span>
                {project.share_expires_at && (
                  <span>· expires {new Date(project.share_expires_at).toLocaleDateString()}</span>
                )}
                <a
                  href={`/p/${project.share_slug}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ml-auto flex items-center gap-1 hover:text-foreground transition-colors"
                >
                  View <AppIcons.externalLink className="h-3 w-3" />
                </a>
              </div>
              <div className="pt-1 border-t border-border">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => revokeMutation.mutate()}
                  disabled={revokeMutation.isPending}
                >
                  {revokeMutation.isPending ? "Revoking…" : "Revoke link"}
                </Button>
              </div>
            </>
          ) : (
            <>
              <p className="text-xs text-muted-foreground">
                Create a read-only link — anyone with it can view this project without an account.
              </p>
              <div className="flex items-center gap-2 text-sm">
                <label className="text-muted-foreground text-xs shrink-0">Expires after</label>
                <select
                  value={expiryDays}
                  onChange={(e) => setExpiryDays(e.target.value)}
                  className="rounded border border-border bg-background px-2 py-1 text-xs"
                >
                  <option value="7">7 days</option>
                  <option value="30">30 days</option>
                  <option value="90">90 days</option>
                  <option value="365">1 year</option>
                  <option value="">Never</option>
                </select>
              </div>
              <Button
                size="sm"
                onClick={() => shareMutation.mutate()}
                disabled={shareMutation.isPending}
              >
                {shareMutation.isPending ? "Creating…" : "Create link"}
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
