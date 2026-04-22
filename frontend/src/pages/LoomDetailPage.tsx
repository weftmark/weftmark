import { useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getLoom, deleteLoom, uploadLoomPhoto, deleteLoomPhoto, loomPhotoUrl,
  uploadVersionPhoto, deleteVersionPhoto, versionPhotoUrl,
  uploadVersionReceipt, deleteVersionReceipt, versionReceiptUrl,
  type LoomDetail, type LoomVersion, type LoomVersionPhoto, type LoomVersionReceipt,
  LOOM_TYPE_LABELS,
} from "@/api/looms";
import { AddVersionModal } from "@/components/looms/AddVersionModal";
import { EditLoomModal } from "@/components/looms/EditLoomModal";
import { Button } from "@/components/ui/button";

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ProfilePhoto({ loom, onChanged }: { loom: LoomDetail; onChanged: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      await uploadLoomPhoto(loom.id, file);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleDelete = async () => {
    setUploading(true);
    try {
      await deleteLoomPhoto(loom.id);
      onChanged();
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex items-start gap-4">
      {loom.has_photo ? (
        <img
          src={loomPhotoUrl(loom.id)}
          alt="Loom profile"
          className="h-32 w-32 rounded-lg object-cover border"
        />
      ) : (
        <div className="h-32 w-32 rounded-lg border border-dashed flex items-center justify-center text-xs text-muted-foreground">
          No photo
        </div>
      )}
      <div className="flex flex-col gap-2">
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,image/gif"
          className="hidden"
          onChange={handleUpload}
        />
        <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()} disabled={uploading}>
          {uploading ? "Uploading…" : loom.has_photo ? "Replace photo" : "Upload photo"}
        </Button>
        {loom.has_photo && (
          <Button size="sm" variant="outline" onClick={handleDelete} disabled={uploading}>
            Remove photo
          </Button>
        )}
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>
    </div>
  );
}

function VersionPhotos({
  loom,
  version,
  onChanged,
}: {
  loom: LoomDetail;
  version: LoomVersion;
  onChanged: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      await uploadVersionPhoto(loom.id, version.id, file);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleDelete = async (photo: LoomVersionPhoto) => {
    try {
      await deleteVersionPhoto(loom.id, version.id, photo.id);
      onChanged();
    } catch {
      // silently ignore
    }
  };

  return (
    <div>
      <p className="text-sm font-medium mb-2">Photos</p>
      <div className="flex flex-wrap gap-2">
        {version.photos.map((p) => (
          <div key={p.id} className="relative group">
            <img
              src={versionPhotoUrl(loom.id, version.id, p.id)}
              alt={p.filename}
              className="h-20 w-20 rounded object-cover border"
            />
            <button
              onClick={() => handleDelete(p)}
              className="absolute -top-1 -right-1 hidden group-hover:flex h-5 w-5 items-center justify-center rounded-full bg-destructive text-destructive-foreground text-xs"
              title="Remove"
            >
              ×
            </button>
          </div>
        ))}
        <div>
          <input
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            className="hidden"
            onChange={handleUpload}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="h-20 w-20 rounded border border-dashed flex items-center justify-center text-xs text-muted-foreground hover:border-ring transition-colors"
          >
            {uploading ? "…" : "+ Add"}
          </button>
        </div>
      </div>
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  );
}

function VersionReceipts({
  loom,
  version,
  onChanged,
}: {
  loom: LoomDetail;
  version: LoomVersion;
  onChanged: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [description, setDescription] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      await uploadVersionReceipt(loom.id, version.id, file, description || undefined);
      setDescription("");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleDelete = async (receipt: LoomVersionReceipt) => {
    try {
      await deleteVersionReceipt(loom.id, version.id, receipt.id);
      onChanged();
    } catch {
      // silently ignore
    }
  };

  return (
    <div>
      <p className="text-sm font-medium mb-2">Receipts &amp; documents</p>
      {version.receipts.length > 0 && (
        <ul className="mb-3 space-y-1">
          {version.receipts.map((r) => (
            <li key={r.id} className="flex items-center gap-2 text-sm">
              <a
                href={versionReceiptUrl(loom.id, version.id, r.id)}
                target="_blank"
                rel="noreferrer"
                className="underline underline-offset-2 hover:text-foreground text-muted-foreground truncate max-w-xs"
              >
                {r.description || r.filename}
              </a>
              <button
                onClick={() => handleDelete(r)}
                className="ml-auto shrink-0 text-xs text-destructive hover:underline"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex gap-2 items-center">
        <input
          className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Label (optional)"
        />
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,application/pdf"
          className="hidden"
          onChange={handleUpload}
        />
        <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()} disabled={uploading}>
          {uploading ? "Uploading…" : "Upload"}
        </Button>
      </div>
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  );
}

function VersionCard({
  loom,
  version,
  isCurrent,
  onChanged,
}: {
  loom: LoomDetail;
  version: LoomVersion;
  isCurrent: boolean;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(isCurrent);

  return (
    <div className={`rounded-lg border ${isCurrent ? "border-ring" : ""}`}>
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-3 text-left"
        onClick={() => setOpen((o) => !o)}
      >
        <span className="text-sm font-medium">
          v{version.version_number}
          {isCurrent && (
            <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-xs font-normal">current</span>
          )}
          {version.description && (
            <span className="ml-2 text-xs text-muted-foreground font-normal">{version.description}</span>
          )}
        </span>
        <span className="text-xs text-muted-foreground">{version.effective_date} {open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t px-4 py-4 space-y-4">
          {/* Spec */}
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
            {version.num_shafts != null && (
              <><dt className="text-muted-foreground">Shafts</dt><dd>{version.num_shafts}</dd></>
            )}
            {version.num_treadles != null && (
              <><dt className="text-muted-foreground">Treadles</dt><dd>{version.num_treadles}</dd></>
            )}
            {version.num_heddles != null && (
              <><dt className="text-muted-foreground">Heddles</dt><dd>{version.num_heddles}</dd></>
            )}
            {version.weaving_width && (
              <><dt className="text-muted-foreground">Weaving width</dt><dd>{version.weaving_width} {version.weaving_width_unit}</dd></>
            )}
            {version.warp_waste_allowance && (
              <><dt className="text-muted-foreground">Warp waste</dt><dd>{version.warp_waste_allowance} {version.warp_waste_unit}</dd></>
            )}
          </dl>

          <VersionPhotos loom={loom} version={version} onChanged={onChanged} />
          <VersionReceipts loom={loom} version={version} onChanged={onChanged} />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function LoomDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showAddVersion, setShowAddVersion] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const { data: loom, isLoading, error } = useQuery({
    queryKey: ["loom", id],
    queryFn: () => getLoom(id!),
    enabled: !!id,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["loom", id] });
    queryClient.invalidateQueries({ queryKey: ["looms"] });
  };

  const handleVersionAdded = () => {
    setShowAddVersion(false);
    invalidate();
  };

  const handleEditSaved = (updated: LoomDetail) => {
    queryClient.setQueryData(["loom", id], updated);
    queryClient.invalidateQueries({ queryKey: ["looms"] });
    setShowEdit(false);
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
          <span className="text-xs text-muted-foreground">{LOOM_TYPE_LABELS[loom.loom_type]}</span>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setShowEdit(true)}>
            Edit
          </Button>
          <Button size="sm" onClick={() => setShowAddVersion(true)}>
            Add version
          </Button>
        </div>
      </header>

      <main className="flex-1 p-6 max-w-3xl mx-auto w-full space-y-8">
        {/* Profile photo + identity */}
        <section className="space-y-4">
          <ProfilePhoto loom={loom} onChanged={invalidate} />
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
            {loom.serial_number && (
              <><dt className="text-muted-foreground">Serial number</dt><dd className="col-span-1 sm:col-span-2">{loom.serial_number}</dd></>
            )}
            {loom.purchase_date && (
              <><dt className="text-muted-foreground">Purchased</dt><dd className="col-span-1 sm:col-span-2">{loom.purchase_date}</dd></>
            )}
            {loom.purchase_price && (
              <><dt className="text-muted-foreground">Purchase price</dt><dd className="col-span-1 sm:col-span-2">{loom.purchase_price}</dd></>
            )}
            {loom.vendor && (
              <><dt className="text-muted-foreground">Purchased from</dt><dd className="col-span-1 sm:col-span-2">{loom.vendor}</dd></>
            )}
          </dl>
          {(loom.supports_lift_tracking || loom.supports_treadle_tracking) && (
            <div className="flex gap-2">
              {loom.supports_lift_tracking && (
                <span className="rounded bg-muted px-2 py-0.5 text-xs">lift tracking</span>
              )}
              {loom.supports_treadle_tracking && (
                <span className="rounded bg-muted px-2 py-0.5 text-xs">treadle tracking</span>
              )}
            </div>
          )}
          {loom.notes && (
            <p className="text-sm text-muted-foreground whitespace-pre-wrap">{loom.notes}</p>
          )}
        </section>

        {/* Configuration history */}
        <section>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground uppercase tracking-wide">
            Configuration history
          </h2>
          <div className="space-y-3">
            {sortedVersions.map((v) => (
              <VersionCard
                key={v.id}
                loom={loom}
                version={v}
                isCurrent={v.id === currentVersionId}
                onChanged={invalidate}
              />
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
              <Button variant="outline" size="sm" onClick={() => setConfirmDelete(false)} disabled={deleting}>
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
          loomType={loom.loom_type}
          onSuccess={handleVersionAdded}
          onClose={() => setShowAddVersion(false)}
        />
      )}
      {showEdit && (
        <EditLoomModal
          loom={loom}
          onSuccess={handleEditSaved}
          onClose={() => setShowEdit(false)}
        />
      )}
    </div>
  );
}
