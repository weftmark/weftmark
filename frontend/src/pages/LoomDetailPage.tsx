import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getLoom, deleteLoom, type LoomVersion } from "@/api/looms";
import { AddVersionModal } from "@/components/looms/AddVersionModal";
import { Button } from "@/components/ui/button";

function VersionRow({ v, isCurrent }: { v: LoomVersion; isCurrent: boolean }) {
  return (
    <div className={`rounded-lg border p-4 ${isCurrent ? "border-ring" : ""}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">
          v{v.version_number}
          {isCurrent && (
            <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-xs font-normal">current</span>
          )}
        </span>
        <span className="text-xs text-muted-foreground">{v.effective_date}</span>
      </div>
      {v.description && (
        <p className="mt-1 text-sm text-muted-foreground">{v.description}</p>
      )}
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
        <dt className="text-muted-foreground">Shafts</dt>
        <dd>{v.num_shafts}</dd>
        <dt className="text-muted-foreground">Treadles</dt>
        <dd>{v.num_treadles}</dd>
        {v.weaving_width && (
          <>
            <dt className="text-muted-foreground">Weaving width</dt>
            <dd>{v.weaving_width} {v.weaving_width_unit}</dd>
          </>
        )}
        {v.warp_waste_allowance && (
          <>
            <dt className="text-muted-foreground">Warp waste</dt>
            <dd>{v.warp_waste_allowance} {v.warp_waste_unit}</dd>
          </>
        )}
      </dl>
    </div>
  );
}

export function LoomDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showAddVersion, setShowAddVersion] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const { data: loom, isLoading, error } = useQuery({
    queryKey: ["loom", id],
    queryFn: () => getLoom(id!),
    enabled: !!id,
  });

  const handleVersionAdded = () => {
    setShowAddVersion(false);
    queryClient.invalidateQueries({ queryKey: ["loom", id] });
    queryClient.invalidateQueries({ queryKey: ["looms"] });
  };

  const handleDelete = async () => {
    if (!id) return;
    setDeleting(true);
    try {
      await deleteLoom(id);
      queryClient.invalidateQueries({ queryKey: ["looms"] });
      navigate("/looms", { replace: true });
    } catch {
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground text-sm">Loading…</p>
      </div>
    );
  }

  if (error || !loom) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-destructive text-sm">Loom not found.</p>
      </div>
    );
  }

  const sortedVersions = [...loom.versions].sort((a, b) => b.version_number - a.version_number);
  const currentVersionId = loom.current_version?.id;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to="/looms" className="text-sm text-muted-foreground hover:text-foreground">
            ← Equipment
          </Link>
          <span className="font-semibold">
            {loom.manufacturer} {loom.model_name}
          </span>
        </div>
        <Button size="sm" onClick={() => setShowAddVersion(true)}>
          Add version
        </Button>
      </header>

      <main className="flex-1 p-6 max-w-3xl mx-auto w-full space-y-6">
        {/* Identity */}
        <section>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground uppercase tracking-wide">Details</h2>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
            <dt className="text-muted-foreground">Manufacturer</dt>
            <dd className="col-span-1 sm:col-span-2">{loom.manufacturer}</dd>
            <dt className="text-muted-foreground">Model</dt>
            <dd className="col-span-1 sm:col-span-2">{loom.model_name}</dd>
            {loom.serial_number && (
              <>
                <dt className="text-muted-foreground">Serial number</dt>
                <dd className="col-span-1 sm:col-span-2">{loom.serial_number}</dd>
              </>
            )}
            {loom.purchase_date && (
              <>
                <dt className="text-muted-foreground">Purchased</dt>
                <dd className="col-span-1 sm:col-span-2">{loom.purchase_date}</dd>
              </>
            )}
            {loom.purchase_price && (
              <>
                <dt className="text-muted-foreground">Purchase price</dt>
                <dd className="col-span-1 sm:col-span-2">{loom.purchase_price}</dd>
              </>
            )}
            {loom.vendor && (
              <>
                <dt className="text-muted-foreground">Vendor</dt>
                <dd className="col-span-1 sm:col-span-2">{loom.vendor}</dd>
              </>
            )}
          </dl>
          {loom.notes && (
            <p className="mt-3 text-sm text-muted-foreground whitespace-pre-wrap">{loom.notes}</p>
          )}
          <div className="mt-3 flex gap-2">
            {loom.supports_lift_tracking && (
              <span className="rounded bg-muted px-2 py-0.5 text-xs">lift tracking</span>
            )}
            {loom.supports_treadle_tracking && (
              <span className="rounded bg-muted px-2 py-0.5 text-xs">treadle tracking</span>
            )}
          </div>
        </section>

        {/* Version history */}
        <section>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground uppercase tracking-wide">
            Configuration history
          </h2>
          <div className="space-y-3">
            {sortedVersions.map((v) => (
              <VersionRow key={v.id} v={v} isCurrent={v.id === currentVersionId} />
            ))}
          </div>
        </section>

        {/* Delete */}
        <section className="border-t pt-6">
          {!confirmDelete ? (
            <Button variant="outline" size="sm" onClick={() => setConfirmDelete(true)}>
              Delete loom
            </Button>
          ) : (
            <div className="flex items-center gap-3">
              <p className="text-sm text-destructive">Delete this loom? This cannot be undone.</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setConfirmDelete(false)}
                disabled={deleting}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleDelete}
                disabled={deleting}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {deleting ? "Deleting…" : "Confirm delete"}
              </Button>
            </div>
          )}
        </section>
      </main>

      {showAddVersion && (
        <AddVersionModal
          loomId={loom.id}
          onSuccess={handleVersionAdded}
          onClose={() => setShowAddVersion(false)}
        />
      )}
    </div>
  );
}
