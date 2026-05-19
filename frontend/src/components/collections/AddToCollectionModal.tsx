import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listCollections, getCollection } from "@/api/collections";
import { AppIcons } from "@/lib/icons";
import { Button } from "@/components/ui/button";

interface Props {
  itemId: string;
  itemType: "draft" | "project";
  onAdd: (collectionId: string, itemId: string) => Promise<void>;
  onRemove: (collectionId: string, itemId: string) => Promise<void>;
  onClose: () => void;
}

export function AddToCollectionModal({ itemId, itemType, onAdd, onRemove, onClose }: Props) {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<string | null>(null);

  const { data: collections = [], isLoading } = useQuery({
    queryKey: ["collections"],
    queryFn: () => listCollections(),
  });

  // Fetch detail for each collection to know membership — only feasible for typical small lists
  const { data: membershipMap = {} } = useQuery({
    queryKey: ["collection-membership", itemType, itemId, collections.map((c) => c.id).join(",")],
    queryFn: async () => {
      const map: Record<string, boolean> = {};
      await Promise.all(
        collections.map(async (c) => {
          try {
            const detail = await getCollection(c.id);
            if (itemType === "draft") {
              map[c.id] = detail.drafts.some((d) => d.id === itemId);
            } else {
              map[c.id] = detail.projects.some((p) => p.id === itemId);
            }
          } catch {
            map[c.id] = false;
          }
        })
      );
      return map;
    },
    enabled: collections.length > 0,
  });

  async function toggle(collectionId: string) {
    setPending(collectionId);
    try {
      if (membershipMap[collectionId]) {
        await onRemove(collectionId, itemId);
      } else {
        await onAdd(collectionId, itemId);
      }
      queryClient.invalidateQueries({ queryKey: ["collection-membership"] });
      queryClient.invalidateQueries({ queryKey: ["collection", collectionId] });
      queryClient.invalidateQueries({ queryKey: ["collections"] });
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card shadow-lg flex flex-col max-h-[70vh]">
        <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-border">
          <h2 className="text-base font-semibold">Add to collection</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <AppIcons.close className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-1.5">
          {isLoading && <p className="text-sm text-muted-foreground text-center py-4">Loading…</p>}
          {!isLoading && collections.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-4">No collections yet.</p>
          )}
          {collections.map((c) => {
            const isMember = !!membershipMap[c.id];
            const isPending = pending === c.id;
            return (
              <button
                key={c.id}
                className="w-full flex items-center gap-3 rounded-md px-3 py-2.5 text-sm hover:bg-muted transition-colors text-left"
                onClick={() => toggle(c.id)}
                disabled={isPending}
              >
                <div className={`h-4 w-4 shrink-0 rounded border transition-colors flex items-center justify-center ${
                  isMember ? "bg-accent border-accent" : "border-border"
                }`}>
                  {isMember && <AppIcons.close className="h-2.5 w-2.5 text-accent-foreground rotate-45 hidden" />}
                  {isMember && <span className="text-accent-foreground text-xs leading-none">✓</span>}
                </div>
                <div className="min-w-0 flex-1">
                  <span className="font-medium truncate block">{c.name}</span>
                  <span className="text-xs text-muted-foreground">{c.draft_count} drafts · {c.project_count} projects</span>
                </div>
                {isPending && <AppIcons.spinner className="h-3.5 w-3.5 animate-spin shrink-0 text-muted-foreground" />}
              </button>
            );
          })}
        </div>
        <div className="px-5 pb-4 pt-3 border-t border-border">
          <Button variant="ghost" size="sm" className="w-full" onClick={onClose}>Done</Button>
        </div>
      </div>
    </div>
  );
}
