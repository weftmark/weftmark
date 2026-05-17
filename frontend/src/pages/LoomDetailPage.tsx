import { useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { AppIcons } from "@/lib/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuthContext } from "@/context/AuthContext";
import { measurementSystemToUnit, displayLength, convertLength, type LengthUnit } from "@/lib/units";
import { listProjects } from "@/api/projects";
import { ProjectSummaryList } from "@/components/projects/ProjectSummaryList";
import {
  getLoom, deleteLoom, uploadLoomPhoto, deleteLoomPhoto, loomPhotoUrl,
  uploadVersionPhoto, deleteVersionPhoto, versionPhotoUrl,
  uploadVersionReceipt, deleteVersionReceipt, versionReceiptUrl,
  addAccessory, deleteAccessory, updateVersion,
  addReed, deleteReed,
  type LoomDetail, type LoomVersion, type LoomVersionPhoto,
  type LoomVersionReceipt, type LoomVersionAccessory, type LoomReed,
  LOOM_TYPE_LABELS, SUPPORTED_LOOM_TYPES,
} from "@/api/looms";
import { AddVersionModal } from "@/components/looms/AddVersionModal";
import { EditLoomModal } from "@/components/looms/EditLoomModal";
import { CloneVersionModal } from "@/components/looms/CloneVersionModal";
import { Button } from "@/components/ui/button";
import { AuthedImage } from "@/components/ui/AuthedImage";
import { downloadAuthed } from "@/api/client";
import { resizeImageToFile, formatBytes } from "@/lib/image-utils";
import { SuperuserInspectionBanner } from "@/components/ui/SuperuserInspectionBanner";

const PHOTO_MAX_BYTES = 5 * 1024 * 1024; // 5 MB — must match backend MAX_FILE_SIZE
const MAX_VERSION_PHOTOS = 5;            // must match backend MAX_VERSION_PHOTOS

// ---------------------------------------------------------------------------
// Reusable inline confirm
// ---------------------------------------------------------------------------

function ConfirmInline({
  label,
  onConfirm,
  onCancel,
}: {
  label: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <span className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <button
        onClick={onConfirm}
        className="text-destructive hover:underline text-xs font-medium"
      >
        Confirm
      </button>
      <button
        onClick={onCancel}
        className="text-muted-foreground hover:underline text-xs"
      >
        Cancel
      </button>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Profile photo
// ---------------------------------------------------------------------------

function ProfilePhoto({ loom, onChanged }: { loom: LoomDetail; onChanged: () => void }) {
  const { user } = useAuthContext();
  const isReadOnly = !!user?.is_superuser && loom.owner_id !== user.id;
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);

  const clearInput = () => { if (fileRef.current) fileRef.current.value = ""; };

  const doUpload = async (file: File) => {
    setError(null);
    setUploading(true);
    try {
      await uploadLoomPhoto(loom.id, file);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      setPendingFile(null);
      clearInput();
    }
  };

  const handleFileSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > PHOTO_MAX_BYTES) {
      setPendingFile(file);
    } else {
      doUpload(file);
    }
  };

  const handleResize = async () => {
    if (!pendingFile) return;
    setUploading(true);
    try {
      const resized = await resizeImageToFile(pendingFile, PHOTO_MAX_BYTES);
      await doUpload(resized);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resize failed");
      setPendingFile(null);
      clearInput();
      setUploading(false);
    }
  };

  const handleDelete = async () => {
    setUploading(true);
    try {
      await deleteLoomPhoto(loom.id);
      onChanged();
    } finally {
      setUploading(false);
      setConfirmRemove(false);
    }
  };

  return (
    <div className="flex items-start gap-4">
      {loom.has_photo ? (
        <AuthedImage
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
        {!isReadOnly && (
          <>
            <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif" className="hidden" onChange={handleFileSelected} />
            <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()} disabled={uploading || !!pendingFile}>
              {uploading ? "Uploading…" : loom.has_photo ? "Replace photo" : "Upload photo"}
            </Button>
            {loom.has_photo && !confirmRemove && (
              <Button size="sm" variant="outline" onClick={() => setConfirmRemove(true)} disabled={uploading || !!pendingFile}>
                Remove photo
              </Button>
            )}
            {loom.has_photo && confirmRemove && (
              <ConfirmInline
                label="Remove this photo?"
                onConfirm={handleDelete}
                onCancel={() => setConfirmRemove(false)}
              />
            )}
          </>
        )}
        {pendingFile && (
          <div className="rounded-md border border-copper-subtle bg-copper-subtle px-3 py-2 text-xs">
            <p className="font-medium text-copper-on-subtle">
              Photo is {formatBytes(pendingFile.size)} — over the 5 MB limit
            </p>
            <div className="mt-1.5 flex gap-2">
              <button onClick={handleResize} className="font-medium text-copper-on-subtle hover:underline">
                Resize &amp; upload
              </button>
              <span className="text-muted-foreground">·</span>
              <button onClick={() => { setPendingFile(null); clearInput(); }} className="text-copper-on-subtle hover:underline">
                Cancel
              </button>
            </div>
          </div>
        )}
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Version photos
// ---------------------------------------------------------------------------

function VersionPhotos({ loom, version, onChanged }: { loom: LoomDetail; version: LoomVersion; onChanged: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);

  const atLimit = version.photos.length >= MAX_VERSION_PHOTOS;
  const clearInput = () => { if (fileRef.current) fileRef.current.value = ""; };

  const doUpload = async (file: File) => {
    setError(null);
    setUploading(true);
    try {
      await uploadVersionPhoto(loom.id, version.id, file);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      setPendingFile(null);
      clearInput();
    }
  };

  const handleFileSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > PHOTO_MAX_BYTES) {
      setPendingFile(file);
    } else {
      doUpload(file);
    }
  };

  const handleResize = async () => {
    if (!pendingFile) return;
    setUploading(true);
    try {
      const resized = await resizeImageToFile(pendingFile, PHOTO_MAX_BYTES);
      await doUpload(resized);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resize failed");
      setPendingFile(null);
      clearInput();
      setUploading(false);
    }
  };

  const handleDelete = async (photo: LoomVersionPhoto) => {
    try {
      await deleteVersionPhoto(loom.id, version.id, photo.id);
      onChanged();
    } catch {
      /* ignore */
    } finally {
      setConfirmId(null);
    }
  };

  return (
    <div>
      <p className="text-sm font-medium mb-2">
        Photos
        <span className="ml-1.5 text-xs font-normal text-muted-foreground">
          {version.photos.length}/{MAX_VERSION_PHOTOS}
        </span>
      </p>
      <div className="flex flex-wrap gap-2 items-start">
        {version.photos.map((p) => (
          <div key={p.id} className="flex flex-col items-center gap-1">
            <AuthedImage src={versionPhotoUrl(loom.id, version.id, p.id)} alt={p.filename} className="h-20 w-20 rounded object-cover border" />
            {confirmId !== p.id ? (
              <button
                onClick={() => setConfirmId(p.id)}
                className="text-xs text-destructive hover:underline"
              >
                Remove
              </button>
            ) : (
              <span className="flex gap-1 text-xs">
                <button onClick={() => handleDelete(p)} className="text-destructive hover:underline font-medium">Confirm</button>
                <span className="text-muted-foreground">·</span>
                <button onClick={() => setConfirmId(null)} className="text-muted-foreground hover:underline">Cancel</button>
              </span>
            )}
          </div>
        ))}
        {!atLimit && (
          <div>
            <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif" className="hidden" onChange={handleFileSelected} />
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading || !!pendingFile}
              className="h-20 w-20 rounded border border-dashed flex items-center justify-center text-xs text-muted-foreground hover:border-ring transition-colors disabled:opacity-50"
            >{uploading ? "…" : "+ Add"}</button>
          </div>
        )}
      </div>
      {pendingFile && (
        <div className="mt-2 rounded-md border border-copper-subtle bg-copper-subtle px-3 py-2 text-xs">
          <p className="font-medium text-copper-on-subtle">
            Photo is {formatBytes(pendingFile.size)} — over the 5 MB limit
          </p>
          <div className="mt-1.5 flex gap-2">
            <button onClick={handleResize} className="font-medium text-copper-on-subtle hover:underline">
              Resize &amp; upload
            </button>
            <span className="text-muted-foreground">·</span>
            <button onClick={() => { setPendingFile(null); clearInput(); }} className="text-copper-on-subtle hover:underline">
              Cancel
            </button>
          </div>
        </div>
      )}
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Version receipts
// ---------------------------------------------------------------------------

function VersionReceipts({ loom, version, onChanged }: { loom: LoomDetail; version: LoomVersion; onChanged: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [description, setDescription] = useState("");
  const [uploading, setUploading] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);
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
      /* ignore */
    } finally {
      setConfirmId(null);
    }
  };

  return (
    <div>
      <p className="text-sm font-medium mb-2">Receipts &amp; documents</p>
      {version.receipts.length > 0 && (
        <ul className="mb-3 space-y-2">
          {version.receipts.map((r) => (
            <li key={r.id} className="flex items-center gap-2 text-sm">
              <button
                type="button"
                onClick={() => downloadAuthed(versionReceiptUrl(loom.id, version.id, r.id), r.filename).catch(() => {})}
                className="underline underline-offset-2 text-muted-foreground hover:text-foreground truncate max-w-xs text-left"
              >{r.description || r.filename}</button>
              <span className="ml-auto shrink-0">
                {confirmId !== r.id ? (
                  <button onClick={() => setConfirmId(r.id)} className="text-xs text-destructive hover:underline">
                    Remove
                  </button>
                ) : (
                  <ConfirmInline
                    label={`Remove "${r.description || r.filename}"?`}
                    onConfirm={() => handleDelete(r)}
                    onCancel={() => setConfirmId(null)}
                  />
                )}
              </span>
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
        <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" className="hidden" onChange={handleUpload} />
        <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()} disabled={uploading}>
          {uploading ? "Uploading…" : "Upload"}
        </Button>
      </div>
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Accessories
// ---------------------------------------------------------------------------

function VersionAccessories({ loom, version, onChanged }: { loom: LoomDetail; version: LoomVersion; onChanged: () => void }) {
  const [input, setInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = input.trim();
    if (!name) return;
    setSaving(true);
    setError(null);
    try {
      await addAccessory(loom.id, version.id, name);
      setInput("");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (acc: LoomVersionAccessory) => {
    try {
      await deleteAccessory(loom.id, version.id, acc.id);
      onChanged();
    } catch {
      /* ignore */
    } finally {
      setConfirmId(null);
    }
  };

  return (
    <div>
      <p className="text-sm font-medium mb-2">Accessories</p>
      {version.accessories.length > 0 && (
        <ul className="mb-3 space-y-2">
          {version.accessories.map((acc) => (
            <li key={acc.id} className="flex items-center gap-2 text-sm">
              <span className="flex-1">{acc.name}</span>
              <span className="shrink-0">
                {confirmId !== acc.id ? (
                  <button onClick={() => setConfirmId(acc.id)} className="text-xs text-destructive hover:underline">
                    Remove
                  </button>
                ) : (
                  <ConfirmInline
                    label={`Remove "${acc.name}"?`}
                    onConfirm={() => handleDelete(acc)}
                    onCancel={() => setConfirmId(null)}
                  />
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={handleAdd} className="flex gap-2">
        <input
          className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. Second warp beam"
          disabled={saving}
        />
        <Button size="sm" variant="outline" type="submit" disabled={saving || !input.trim()}>
          Add
        </Button>
      </form>
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Reed inventory
// ---------------------------------------------------------------------------

function ReedsPanel({ loom, onChanged }: { loom: LoomDetail; onChanged: () => void }) {
  const [dentsInput, setDentsInput] = useState("");
  const [widthInput, setWidthInput] = useState("");
  const [labelInput, setLabelInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    const dents = parseFloat(dentsInput);
    if (!dentsInput || isNaN(dents) || dents <= 0) {
      setError("Dents per inch must be a positive number");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await addReed(loom.id, {
        dents_per_inch: dents,
        ...(widthInput ? { width_cm: parseFloat(widthInput) } : {}),
        ...(labelInput.trim() ? { label: labelInput.trim() } : {}),
      });
      setDentsInput("");
      setWidthInput("");
      setLabelInput("");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add reed");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (reed: LoomReed) => {
    try {
      await deleteReed(loom.id, reed.id);
      onChanged();
    } catch {
      /* ignore */
    } finally {
      setConfirmId(null);
    }
  };

  const duplicate = dentsInput
    ? loom.reeds.some((r) => r.dents_per_inch === parseFloat(dentsInput))
    : false;

  return (
    <section className="border-t pt-6">
      <h2 className="mb-3 text-sm font-medium text-muted-foreground uppercase tracking-wide">Reed inventory</h2>
      {loom.reeds.length > 0 && (
        <ul className="mb-4 space-y-2">
          {loom.reeds.map((reed) => (
            <li key={reed.id} className="flex items-center gap-3 text-sm">
              <span className="w-20 font-medium tabular-nums">{reed.dents_per_inch} dent</span>
              {reed.width_cm != null && (
                <span className="text-muted-foreground">{reed.width_cm} cm wide</span>
              )}
              {reed.label && (
                <span className="text-muted-foreground italic">{reed.label}</span>
              )}
              <span className="ml-auto shrink-0">
                {confirmId !== reed.id ? (
                  <button
                    onClick={() => setConfirmId(reed.id)}
                    className="text-xs text-destructive hover:underline"
                  >
                    Remove
                  </button>
                ) : (
                  <ConfirmInline
                    label={`Remove ${reed.dents_per_inch}-dent reed?`}
                    onConfirm={() => handleDelete(reed)}
                    onCancel={() => setConfirmId(null)}
                  />
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={handleAdd} className="flex flex-wrap gap-2 items-end">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">Dents/inch *</label>
          <input
            type="number"
            min="0.5"
            step="0.5"
            className="w-24 rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            value={dentsInput}
            onChange={(e) => setDentsInput(e.target.value)}
            placeholder="e.g. 10"
            disabled={saving}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">Width (cm)</label>
          <input
            type="number"
            min="0"
            step="0.5"
            className="w-24 rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            value={widthInput}
            onChange={(e) => setWidthInput(e.target.value)}
            placeholder="optional"
            disabled={saving}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">Label</label>
          <input
            className="w-36 rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            value={labelInput}
            onChange={(e) => setLabelInput(e.target.value)}
            placeholder="optional"
            disabled={saving}
          />
        </div>
        <Button size="sm" variant="outline" type="submit" disabled={saving || !dentsInput}>
          Add reed
        </Button>
      </form>
      {duplicate && (
        <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
          You already have a {parseFloat(dentsInput)}-dent reed on this loom.
        </p>
      )}
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </section>
  );
}


// ---------------------------------------------------------------------------
// Version card
// ---------------------------------------------------------------------------

function VersionCard({
  loom, version, isCurrent, onChanged, onClone,
}: {
  loom: LoomDetail;
  version: LoomVersion;
  isCurrent: boolean;
  onChanged: () => void;
  onClone: (v: LoomVersion) => void;
}) {
  const { user } = useAuthContext();
  const isReadOnly = !!user?.is_superuser && loom.owner_id !== user.id;
  const displayUnit = measurementSystemToUnit(user?.measurement_system ?? "metric");
  const [open, setOpen] = useState(isCurrent);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(version.name ?? "");
  const [editDesc, setEditDesc] = useState(version.description ?? "");
  const [editWasteUnit, setEditWasteUnit] = useState<LengthUnit>(
    (version.warp_waste_allowance ? version.warp_waste_unit : displayUnit) as LengthUnit
  );
  const [editWaste, setEditWaste] = useState(
    version.warp_waste_allowance ? parseFloat(version.warp_waste_allowance).toFixed(1) : ""
  );
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const displayName = version.name || `v${version.version_number}`;

  const handleEditSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setEditError(null);
    try {
      const waste = editWaste.trim() ? parseFloat(editWaste) : undefined;
      await updateVersion(loom.id, version.id, {
        name: editName.trim() || undefined,
        description: editDesc.trim() || undefined,
        ...(waste !== undefined ? { warp_waste_allowance: waste, warp_waste_unit: editWasteUnit } : {}),
      });
      onChanged();
      setEditing(false);
    } catch (err) {
      setEditError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleEditCancel = () => {
    setEditName(version.name ?? "");
    setEditDesc(version.description ?? "");
    setEditWaste(version.warp_waste_allowance ? parseFloat(version.warp_waste_allowance).toFixed(1) : "");
    setEditWasteUnit((version.warp_waste_allowance ? version.warp_waste_unit : displayUnit) as LengthUnit);
    setEditError(null);
    setEditing(false);
  };

  function handleWasteUnitChange(newUnit: LengthUnit) {
    if (editWaste) {
      const val = parseFloat(editWaste);
      if (!isNaN(val)) setEditWaste(convertLength(val, editWasteUnit, newUnit).toFixed(1));
    }
    setEditWasteUnit(newUnit);
  }

  return (
    <div className={`rounded-lg border ${isCurrent ? "border-ring" : ""}`}>
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-3 text-left"
        onClick={() => setOpen((o) => !o)}
      >
        <span className="text-sm font-medium">
          {version.name ? (
            <>{version.name} <span className="font-normal text-muted-foreground">v{version.version_number}</span></>
          ) : (
            <>v{version.version_number}</>
          )}
          {isCurrent && <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-xs font-normal">current</span>}
          {version.description && <span className="ml-2 text-xs text-muted-foreground font-normal">{version.description}</span>}
        </span>
        <span className="text-xs text-muted-foreground">{new Date(version.effective_date + "T00:00:00").toLocaleDateString()} {open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t px-4 py-4 space-y-3">
          {/* Specs / edit form */}
          <div className="rounded-md border border-border p-3">
            {editing ? (
              <form onSubmit={handleEditSave} className="space-y-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Configuration name</label>
                  <input
                    className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    placeholder={`v${version.version_number}`}
                    autoFocus
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Description</label>
                  <input
                    className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                    value={editDesc}
                    onChange={(e) => setEditDesc(e.target.value)}
                    placeholder="Optional description"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Warp waste default</label>
                  <div className="flex gap-2">
                    <input
                      type="number"
                      min="0"
                      step="0.1"
                      className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                      value={editWaste}
                      onChange={(e) => setEditWaste(e.target.value)}
                      placeholder="e.g. 50"
                    />
                    <select
                      className="rounded-md border border-input bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                      value={editWasteUnit}
                      onChange={(e) => handleWasteUnitChange(e.target.value as LengthUnit)}
                    >
                      <option value="cm">cm</option>
                      <option value="in">in</option>
                    </select>
                  </div>
                </div>
                {editError && <p className="text-xs text-destructive">{editError}</p>}
                <div className="flex gap-2">
                  <Button type="submit" size="sm" disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
                  <Button type="button" size="sm" variant="outline" onClick={handleEditCancel} disabled={saving}>Cancel</Button>
                </div>
              </form>
            ) : (
              <div className="flex items-start justify-between gap-2">
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
                  {version.num_shafts != null && (<><dt className="text-muted-foreground">Shafts</dt><dd>{version.num_shafts}</dd></>)}
                  {version.num_treadles != null && (<><dt className="text-muted-foreground">Treadles</dt><dd>{version.num_treadles}</dd></>)}
                  {version.num_heddles != null && (<><dt className="text-muted-foreground">Heddles</dt><dd>{version.num_heddles}</dd></>)}
                  {version.weaving_width && (<><dt className="text-muted-foreground">Weaving width</dt><dd>{displayLength(version.weaving_width, version.weaving_width_unit, displayUnit)}</dd></>)}
                  <dt className="text-muted-foreground">Warp waste</dt>
                  <dd>
                    {version.warp_waste_allowance ? (() => {
                      const storedUnit = (version.warp_waste_unit ?? displayUnit) as LengthUnit;
                      const primary = displayLength(version.warp_waste_allowance, storedUnit, storedUnit);
                      if (storedUnit === displayUnit) return primary;
                      const secondary = displayLength(version.warp_waste_allowance, storedUnit, displayUnit);
                      return <><span className="font-medium">{primary}</span>{" "}<span className="text-xs text-muted-foreground">({secondary})</span></>;
                    })() : <span className="italic text-muted-foreground">Not set</span>}
                  </dd>
                </dl>
                {!isReadOnly && (
                  <button
                    type="button"
                    onClick={() => setEditing(true)}
                    className="shrink-0 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                    title="Edit configuration"
                  >
                    <AppIcons.edit className="h-4 w-4" />
                  </button>
                )}
              </div>
            )}
          </div>

          <div className="rounded-md border border-border p-3">
            <VersionAccessories loom={loom} version={version} onChanged={onChanged} />
          </div>
          <div className="rounded-md border border-border p-3">
            <VersionPhotos loom={loom} version={version} onChanged={onChanged} />
          </div>
          <div className="rounded-md border border-border p-3">
            <VersionReceipts loom={loom} version={version} onChanged={onChanged} />
          </div>

          {!isReadOnly && (
            <div className="border-t pt-3">
              <Button size="sm" variant="outline" onClick={() => onClone(version)}>
                Clone this configuration
              </Button>
              <p className="mt-1 text-xs text-muted-foreground">
                Creates a new configuration pre-filled with {displayName}'s spec and accessories.
              </p>
            </div>
          )}
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
  const { user } = useAuthContext();
  const [showAddVersion, setShowAddVersion] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [cloneSource, setCloneSource] = useState<LoomVersion | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [dangerZoneOpen, setDangerZoneOpen] = useState(false);

  const { data: loom, isLoading, error } = useQuery({
    queryKey: ["loom", id],
    queryFn: () => getLoom(id!),
    enabled: !!id,
  });

  const { data: loomProjects = [] } = useQuery({
    queryKey: ["projects", { loomId: id }],
    queryFn: () => listProjects({ loomId: id! }),
    enabled: !!id,
  });
  const activeProject = loomProjects.find((a) => a.status === "active");

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["loom", id] });
    queryClient.invalidateQueries({ queryKey: ["looms"] });
  };

  const handleVersionAdded = () => { setShowAddVersion(false); invalidate(); };
  const handleCloned = () => { setCloneSource(null); invalidate(); };
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

  if (isLoading) return <div className="flex min-h-screen items-center justify-center"><p className="text-muted-foreground text-sm">Loading…</p></div>;
  if (error || !loom) return <div className="flex min-h-screen items-center justify-center"><p className="text-destructive text-sm">Loom not found.</p></div>;

  const sortedVersions = [...loom.versions].sort((a, b) => b.version_number - a.version_number);
  const currentVersionId = loom.current_version?.id;
  const isReadOnly = !!user?.is_superuser && loom.owner_id !== user.id;

  return (
    <div className="max-w-3xl mx-auto w-full">
      {isReadOnly && <SuperuserInspectionBanner />}
      <div className="p-6 space-y-8">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm">
          <Link to="/looms" className="text-muted-foreground hover:text-foreground">Equipment</Link>
          <AppIcons.chevronRight className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="font-medium text-foreground">{loom.manufacturer} {loom.model_name}</span>
          <span className="text-xs text-muted-foreground">{LOOM_TYPE_LABELS[loom.loom_type]}</span>
        </div>
        <div className="flex gap-2">
          {!isReadOnly && <Button size="sm" variant="outline" onClick={() => setShowEdit(true)}>Edit</Button>}
          {!isReadOnly && <Button size="sm" onClick={() => setShowAddVersion(true)}>Add version</Button>}
        </div>
      </div>
        {!SUPPORTED_LOOM_TYPES.has(loom.loom_type) && (
          <div className="rounded-md border border-copper-subtle bg-copper-subtle px-4 py-3 text-sm text-copper-on-subtle">
            <span className="font-medium">Project tracking not supported</span> — this loom type is not currently
            supported for project tracking. It has been saved for documentation and will be available if support
            is added later.
          </div>
        )}
        <section className="space-y-4">
          <ProfilePhoto loom={loom} onChanged={invalidate} />
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
            {loom.serial_number && (<><dt className="text-muted-foreground">Serial number</dt><dd className="col-span-1 sm:col-span-2">{loom.serial_number}</dd></>)}
            {loom.purchase_date && (<><dt className="text-muted-foreground">Purchased</dt><dd className="col-span-1 sm:col-span-2">{new Date(loom.purchase_date + "T00:00:00").toLocaleDateString()}</dd></>)}
            {loom.purchase_price && (<><dt className="text-muted-foreground">Purchase price</dt><dd className="col-span-1 sm:col-span-2">{loom.purchase_price}</dd></>)}
            {loom.vendor && (<><dt className="text-muted-foreground">Purchased from</dt><dd className="col-span-1 sm:col-span-2">{loom.vendor}</dd></>)}
          </dl>
          {(loom.supports_lift_tracking || loom.supports_treadle_tracking) && (
            <div className="flex gap-2">
              {loom.supports_lift_tracking && <span className="rounded bg-muted px-2 py-0.5 text-xs">lift tracking</span>}
              {loom.supports_treadle_tracking && <span className="rounded bg-muted px-2 py-0.5 text-xs">treadle tracking</span>}
            </div>
          )}
          {loom.notes && <p className="text-sm text-muted-foreground whitespace-pre-wrap">{loom.notes}</p>}
          {activeProject && (
            <div className="rounded-md border border-green-300 bg-green-50 dark:bg-green-950/30 dark:border-green-700 px-3 py-2.5 text-sm flex items-center justify-between gap-4">
              <div>
                <span className="font-medium text-green-900 dark:text-green-200">Active project: </span>
                <span className="text-green-800 dark:text-green-300">{activeProject.name}</span>
              </div>
              <Link
                to={`/projects/${activeProject.id}`}
                className="shrink-0 text-xs text-green-700 dark:text-green-400 hover:underline"
              >
                View →
              </Link>
            </div>
          )}
        </section>

        <section>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground uppercase tracking-wide">Configuration history</h2>
          <div className="space-y-3">
            {sortedVersions.map((v) => (
              <VersionCard
                key={v.id}
                loom={loom}
                version={v}
                isCurrent={v.id === currentVersionId}
                onChanged={invalidate}
                onClone={setCloneSource}
              />
            ))}
          </div>
        </section>

        <ReedsPanel loom={loom} onChanged={invalidate} />

        <section className="border-t pt-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold">Projects</h2>
            <Link to="/projects" className="text-xs text-muted-foreground hover:text-foreground">
              All projects →
            </Link>
          </div>
          <ProjectSummaryList projects={loomProjects} />
        </section>

        {!isReadOnly && (
          <section className="border-t pt-6">
            <button
              type="button"
              className="flex w-full items-center justify-between text-sm font-medium text-destructive hover:text-destructive/80"
              onClick={() => { setDangerZoneOpen((o) => !o); setConfirmDelete(false); }}
            >
              <span>Danger zone</span>
              <span className="text-xs text-muted-foreground">{dangerZoneOpen ? "▲ collapse" : "▼ expand"}</span>
            </button>
            {dangerZoneOpen && (
              <div className="mt-4 rounded-md border border-destructive/30 px-4 py-4">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-medium">Delete this loom</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">Permanently removes the loom and all its configurations. This cannot be undone.</p>
                  </div>
                  {!confirmDelete ? (
                    <Button variant="outline" size="sm" className="shrink-0 border-destructive/50 text-destructive hover:bg-destructive/10" onClick={() => setConfirmDelete(true)}>
                      Delete loom
                    </Button>
                  ) : (
                    <div className="flex shrink-0 items-center gap-2">
                      <Button variant="outline" size="sm" onClick={() => setConfirmDelete(false)} disabled={deleting}>Cancel</Button>
                      <Button size="sm" onClick={handleDelete} disabled={deleting} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
                        {deleting ? "Deleting…" : "Confirm delete"}
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>
        )}

      {showAddVersion && (
        <AddVersionModal loomId={loom.id} loomType={loom.loom_type} onSuccess={handleVersionAdded} onClose={() => setShowAddVersion(false)} />
      )}
      {showEdit && (
        <EditLoomModal loom={loom} onSuccess={handleEditSaved} onClose={() => setShowEdit(false)} />
      )}
      {cloneSource && (
        <CloneVersionModal loomId={loom.id} source={cloneSource} onSuccess={handleCloned} onClose={() => setCloneSource(null)} />
      )}
      </div>
    </div>
  );
}
