import { useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { AppIcons } from "@/lib/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getYarn, deleteYarn, updateYarn,
  uploadYarnPhoto, deleteYarnPhoto, yarnPhotoUrl,
  addSkeins, updateSkein, deleteSkein,
  weightBothUnits, displayWeight,
  SKEIN_STATUS_LABELS,
  type YarnDetail, type Skein, type UpdateYarnPayload, type SkeinStatus,
} from "@/api/yarn";
import { CloneYarnModal } from "@/components/yarn/CloneYarnModal";
import { Button } from "@/components/ui/button";
import { AuthedImage } from "@/components/ui/AuthedImage";
import { resizeImageToFile, formatBytes } from "@/lib/image-utils";

const PHOTO_MAX_BYTES = 5 * 1024 * 1024;

const STATUS_COLORS: Record<string, string> = {
  available: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  in_use: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
  consumed: "bg-muted text-muted-foreground",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function field(extra = "") {
  return `rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring ${extra}`;
}

// ---------------------------------------------------------------------------
// Photo
// ---------------------------------------------------------------------------

function YarnPhoto({ yarn, onChanged }: { yarn: YarnDetail; onChanged: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  const clearInput = () => { if (fileRef.current) fileRef.current.value = ""; };

  const doUpload = async (file: File) => {
    setError(null);
    setUploading(true);
    try {
      await uploadYarnPhoto(yarn.id, file);
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
    if (file.size > PHOTO_MAX_BYTES) setPendingFile(file);
    else doUpload(file);
  };

  const handleResize = async () => {
    if (!pendingFile) return;
    setUploading(true);
    try {
      await doUpload(await resizeImageToFile(pendingFile, PHOTO_MAX_BYTES));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resize failed");
      setPendingFile(null);
      clearInput();
      setUploading(false);
    }
  };

  return (
    <div className="flex items-start gap-4">
      {yarn.has_photo ? (
        <AuthedImage src={yarnPhotoUrl(yarn.id)} alt="Yarn" className="h-32 w-32 rounded-lg object-cover border" />
      ) : yarn.color_hex ? (
        <div className="h-32 w-32 rounded-lg border shrink-0" style={{ backgroundColor: yarn.color_hex }} />
      ) : (
        <div className="h-32 w-32 rounded-lg border border-dashed flex items-center justify-center text-xs text-muted-foreground">No photo</div>
      )}
      <div className="flex flex-col gap-2">
        <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif" className="hidden" onChange={handleFileSelected} />
        <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()} disabled={uploading || !!pendingFile}>
          {uploading ? "Uploading…" : yarn.has_photo ? "Replace photo" : "Upload photo"}
        </Button>
        {yarn.has_photo && !confirmRemove && (
          <Button size="sm" variant="outline" onClick={() => setConfirmRemove(true)} disabled={uploading}>Remove photo</Button>
        )}
        {yarn.has_photo && confirmRemove && (
          <span className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground text-xs">Remove?</span>
            <button onClick={async () => { setUploading(true); await deleteYarnPhoto(yarn.id); onChanged(); setUploading(false); setConfirmRemove(false); }} className="text-xs text-destructive hover:underline font-medium">Confirm</button>
            <button onClick={() => setConfirmRemove(false)} className="text-xs text-muted-foreground hover:underline">Cancel</button>
          </span>
        )}
        {pendingFile && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs dark:border-amber-800 dark:bg-amber-950">
            <p className="font-medium text-amber-900 dark:text-amber-100">Photo is {formatBytes(pendingFile.size)} — over 5 MB</p>
            <div className="mt-1.5 flex gap-2">
              <button onClick={handleResize} className="font-medium text-amber-800 hover:underline dark:text-amber-200">Resize &amp; upload</button>
              <span className="text-amber-400">·</span>
              <button onClick={() => { setPendingFile(null); clearInput(); }} className="text-amber-700 hover:underline dark:text-amber-300">Cancel</button>
            </div>
          </div>
        )}
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Edit yarn fields
// ---------------------------------------------------------------------------

function EditYarnForm({ yarn, onSaved, onCancel }: { yarn: YarnDetail; onSaved: () => void; onCancel: () => void }) {
  const initWeightUnit: "oz" | "g" = yarn.unit_weight_oz ? "oz" : "g";
  const initWeight = yarn.unit_weight_oz ?? yarn.unit_weight_g ?? "";

  const [brand, setBrand] = useState(yarn.brand);
  const [name, setName] = useState(yarn.name);
  const [weightNotation, setWeightNotation] = useState(yarn.weight_notation ?? "");
  const [fiberContent, setFiberContent] = useState(yarn.fiber_content ?? "");
  const [colorName, setColorName] = useState(yarn.color_name ?? "");
  const [colorHex, setColorHex] = useState(yarn.color_hex ?? "#ffffff");
  const [hasColor, setHasColor] = useState(!!yarn.color_hex);
  const [unitYardage, setUnitYardage] = useState(yarn.unit_yardage ?? "");
  const [unitWeight, setUnitWeight] = useState(String(initWeight));
  const [unitWeightUnit, setUnitWeightUnit] = useState<"oz" | "g">(initWeightUnit);
  const [yardsPerPound, setYardsPerPound] = useState(yarn.yards_per_pound ?? "");
  const [settMin, setSettMin] = useState(yarn.sett_min?.toString() ?? "");
  const [settMax, setSettMax] = useState(yarn.sett_max?.toString() ?? "");
  const [purchaseSource, setPurchaseSource] = useState(yarn.purchase_source ?? "");
  const [purchasePrice, setPurchasePrice] = useState(yarn.purchase_price ?? "");
  const [purchaseDate, setPurchaseDate] = useState(yarn.purchase_date ?? "");
  const [notes, setNotes] = useState(yarn.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const f = field("w-full");

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const { oz, g } = weightBothUnits(unitWeight, unitWeightUnit);
      const payload: UpdateYarnPayload = {
        brand: brand.trim(),
        name: name.trim(),
        weight_notation: weightNotation.trim() || undefined,
        fiber_content: fiberContent.trim() || undefined,
        color_name: colorName.trim() || undefined,
        color_hex: hasColor ? colorHex : undefined,
        unit_yardage: unitYardage ? parseFloat(String(unitYardage)) : undefined,
        unit_weight_oz: oz,
        unit_weight_g: g,
        yards_per_pound: yardsPerPound ? parseFloat(String(yardsPerPound)) : undefined,
        sett_min: settMin ? parseInt(settMin, 10) : undefined,
        sett_max: settMax ? parseInt(settMax, 10) : undefined,
        purchase_source: purchaseSource.trim() || undefined,
        purchase_price: purchasePrice ? parseFloat(String(purchasePrice)) : undefined,
        purchase_date: purchaseDate || undefined,
        notes: notes.trim() || undefined,
      };
      await updateYarn(yarn.id, payload);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSave} className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Brand</label>
          <input className={f} value={brand} onChange={(e) => setBrand(e.target.value)} required />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Product name</label>
          <input className={f} value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Weight notation</label>
          <input className={f} value={weightNotation} onChange={(e) => setWeightNotation(e.target.value)} placeholder="8/2" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Fiber content</label>
          <input className={f} value={fiberContent} onChange={(e) => setFiberContent(e.target.value)} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Color name</label>
          <input className={f} value={colorName} onChange={(e) => setColorName(e.target.value)} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Color swatch</label>
          <div className="flex items-center gap-2 pt-1">
            <input type="checkbox" id="edit-has-color" checked={hasColor} onChange={(e) => setHasColor(e.target.checked)} />
            <label htmlFor="edit-has-color" className="text-sm">Set color</label>
            {hasColor && <input type="color" value={colorHex} onChange={(e) => setColorHex(e.target.value)} className="h-8 w-12 rounded border border-input cursor-pointer" />}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Yardage / unit</label>
          <input type="number" min={0} step="1" className={f} value={unitYardage} onChange={(e) => setUnitYardage(e.target.value)} />
        </div>
        <div className="col-span-2">
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Weight / unit</label>
          <div className="flex gap-2">
            <input type="number" min={0} step="0.1" className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring" value={unitWeight} onChange={(e) => setUnitWeight(e.target.value)} />
            <select className="rounded-md border border-input bg-background px-2 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring" value={unitWeightUnit} onChange={(e) => setUnitWeightUnit(e.target.value as "oz" | "g")}>
              <option value="oz">oz</option>
              <option value="g">g</option>
            </select>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Yards / pound</label>
          <input type="number" min={0} step="1" className={f} value={yardsPerPound} onChange={(e) => setYardsPerPound(e.target.value)} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Sett min (epi)</label>
          <input type="number" min={1} className={f} value={settMin} onChange={(e) => setSettMin(e.target.value)} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Sett max (epi)</label>
          <input type="number" min={1} className={f} value={settMax} onChange={(e) => setSettMax(e.target.value)} />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="col-span-2">
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Purchase source</label>
          <input className={f} value={purchaseSource} onChange={(e) => setPurchaseSource(e.target.value)} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Price / unit</label>
          <input type="number" min={0} step="0.01" className={f} value={purchasePrice} onChange={(e) => setPurchasePrice(e.target.value)} />
        </div>
      </div>

      <div>
        <label className="mb-1 block text-xs font-medium text-muted-foreground">Purchase date</label>
        <input type="date" className={f} value={purchaseDate} onChange={(e) => setPurchaseDate(e.target.value)} />
      </div>

      <div>
        <label className="mb-1 block text-xs font-medium text-muted-foreground">Notes</label>
        <textarea className={`${f} resize-none`} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={saving}>{saving ? "Saving…" : "Save changes"}</Button>
        <Button type="button" size="sm" variant="outline" onClick={onCancel} disabled={saving}>Cancel</Button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Skein row
// ---------------------------------------------------------------------------

function SkeinRow({ yarn, skein, onChanged }: { yarn: YarnDetail; skein: Skein; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [status, setStatus] = useState<SkeinStatus>(skein.status as SkeinStatus);
  const [yardage, setYardage] = useState(skein.current_yardage ?? "");
  const initSkeinWeightUnit: "oz" | "g" = skein.current_weight_oz ? "oz" : "g";
  const initSkeinWeight = skein.current_weight_oz ?? skein.current_weight_g ?? "";
  const [weight, setWeight] = useState(String(initSkeinWeight));
  const [weightUnit, setWeightUnit] = useState<"oz" | "g">(initSkeinWeightUnit);
  const [notes, setNotes] = useState(skein.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const shortId = skein.id.slice(0, 8);

  const handleSave = async () => {
    setSaving(true);
    try {
      const { oz, g } = weightBothUnits(weight, weightUnit);
      await updateSkein(yarn.id, skein.id, {
        status,
        current_yardage: yardage ? parseFloat(String(yardage)) : null,
        current_weight_oz: oz ?? null,
        current_weight_g: g ?? null,
        notes: notes.trim() || null,
      });
      onChanged();
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    await deleteSkein(yarn.id, skein.id);
    onChanged();
  };

  if (editing) {
    const f = "rounded-md border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring";
    return (
      <li className="rounded-md border p-3 space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-muted-foreground font-mono">{shortId}</span>
          <select className={f} value={status} onChange={(e) => setStatus(e.target.value as SkeinStatus)}>
            <option value="available">Available</option>
            <option value="in_use">In use</option>
            <option value="consumed">Consumed</option>
          </select>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="mb-0.5 block text-xs text-muted-foreground">Remaining yds</label>
            <input type="number" min={0} step="1" className={`${f} w-full`} value={yardage} onChange={(e) => setYardage(e.target.value)} />
          </div>
          <div>
            <label className="mb-0.5 block text-xs text-muted-foreground">Current weight</label>
            <div className="flex gap-1">
              <input type="number" min={0} step="0.1" className={`${f} flex-1`} value={weight} onChange={(e) => setWeight(e.target.value)} />
              <select className={f} value={weightUnit} onChange={(e) => setWeightUnit(e.target.value as "oz" | "g")}>
                <option value="oz">oz</option>
                <option value="g">g</option>
              </select>
            </div>
          </div>
        </div>
        <div>
          <label className="mb-0.5 block text-xs text-muted-foreground">Notes</label>
          <input className={`${f} w-full`} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={handleSave} disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
          <Button size="sm" variant="outline" onClick={() => setEditing(false)} disabled={saving}>Cancel</Button>
        </div>
      </li>
    );
  }

  return (
    <li className="flex items-start gap-3 py-2 border-b last:border-0">
      <span className="text-xs text-muted-foreground font-mono pt-0.5 w-20 shrink-0">{shortId}</span>
      <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_COLORS[skein.status]}`}>
        {SKEIN_STATUS_LABELS[skein.status]}
      </span>
      <div className="flex-1 text-xs text-muted-foreground space-y-0.5">
        {skein.current_yardage && <span>{skein.current_yardage} yds remaining · </span>}
        {displayWeight(skein.current_weight_oz, skein.current_weight_g) && (
          <span>{displayWeight(skein.current_weight_oz, skein.current_weight_g)} · </span>
        )}
        {skein.notes && <span className="italic">{skein.notes}</span>}
      </div>
      <div className="flex gap-2 shrink-0">
        <button onClick={() => setEditing(true)} className="text-xs text-muted-foreground hover:underline">Edit</button>
        {!confirmDelete ? (
          <button onClick={() => setConfirmDelete(true)} className="text-xs text-destructive hover:underline">Remove</button>
        ) : (
          <span className="flex gap-1 text-xs">
            <button onClick={handleDelete} className="text-destructive hover:underline font-medium">Confirm</button>
            <span className="text-muted-foreground">·</span>
            <button onClick={() => setConfirmDelete(false)} className="text-muted-foreground hover:underline">Cancel</button>
          </span>
        )}
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Add skeins form
// ---------------------------------------------------------------------------

function AddSkeinsForm({ yarn, onAdded }: { yarn: YarnDetail; onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const initAddWeightUnit: "oz" | "g" = yarn.unit_weight_oz ? "oz" : "g";
  const initAddWeight = yarn.unit_weight_oz ?? yarn.unit_weight_g ?? "";
  const [quantity, setQuantity] = useState("1");
  const [yardage, setYardage] = useState(yarn.unit_yardage ?? "");
  const [weight, setWeight] = useState(String(initAddWeight));
  const [weightUnit, setWeightUnit] = useState<"oz" | "g">(initAddWeightUnit);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const f = "rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const { oz, g } = weightBothUnits(weight, weightUnit);
      await addSkeins(yarn.id, {
        quantity: parseInt(quantity, 10),
        current_yardage: yardage ? parseFloat(String(yardage)) : undefined,
        current_weight_oz: oz,
        current_weight_g: g,
        notes: notes.trim() || undefined,
      });
      onAdded();
      setOpen(false);
      setQuantity("1");
      setNotes("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add");
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>+ Add skeins</Button>
    );
  }

  return (
    <form onSubmit={handleAdd} className="rounded-md border p-3 space-y-3">
      <div className="grid grid-cols-3 gap-2">
        <div>
          <label className="mb-0.5 block text-xs text-muted-foreground">Qty</label>
          <input type="number" min={1} max={100} className={`${f} w-full`} value={quantity} onChange={(e) => setQuantity(e.target.value)} required />
        </div>
        <div>
          <label className="mb-0.5 block text-xs text-muted-foreground">Yardage</label>
          <input type="number" min={0} step="1" className={`${f} w-full`} value={yardage} onChange={(e) => setYardage(e.target.value)} />
        </div>
        <div>
          <label className="mb-0.5 block text-xs text-muted-foreground">Weight</label>
          <div className="flex gap-1">
            <input type="number" min={0} step="0.1" className={`${f} flex-1`} value={weight} onChange={(e) => setWeight(e.target.value)} />
            <select className={f} value={weightUnit} onChange={(e) => setWeightUnit(e.target.value as "oz" | "g")}>
              <option value="oz">oz</option>
              <option value="g">g</option>
            </select>
          </div>
        </div>
      </div>
      <div>
        <label className="mb-0.5 block text-xs text-muted-foreground">Notes (optional)</label>
        <input className={`${f} w-full`} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Dye lot, batch, etc." />
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={saving}>{saving ? "Adding…" : `Add ${quantity} skein${parseInt(quantity) !== 1 ? "s" : ""}`}</Button>
        <Button type="button" size="sm" variant="outline" onClick={() => setOpen(false)} disabled={saving}>Cancel</Button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function YarnDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [showClone, setShowClone] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const { data: yarn, isLoading, error } = useQuery({
    queryKey: ["yarn", id],
    queryFn: () => getYarn(id!),
    enabled: !!id,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["yarn", id] });
    queryClient.invalidateQueries({ queryKey: ["yarn"] });
  };

  const handleDelete = async () => {
    if (!id) return;
    setDeleting(true);
    try {
      await deleteYarn(id);
      queryClient.invalidateQueries({ queryKey: ["yarn"] });
      navigate("/yarn", { replace: true });
    } catch {
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  if (isLoading) return <div className="flex min-h-screen items-center justify-center"><p className="text-sm text-muted-foreground">Loading…</p></div>;
  if (error || !yarn) return <div className="flex min-h-screen items-center justify-center"><p className="text-sm text-destructive">Yarn not found.</p></div>;

  return (
    <div className="p-6 max-w-3xl mx-auto w-full space-y-8">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm">
          <Link to="/yarn" className="text-stone-500 hover:text-stone-900">Yarn</Link>
          <AppIcons.chevronRight className="h-3.5 w-3.5 text-stone-400" />
          <span className="font-medium text-stone-900">{yarn.brand} — {yarn.name}</span>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => setShowClone(true)}>Clone yarn</Button>
          <Button size="sm" variant="outline" onClick={() => setEditing((e) => !e)}>
            {editing ? "Cancel edit" : "Edit"}
          </Button>
        </div>
      </div>

        {/* Photo + summary */}
        <section className="space-y-4">
          <YarnPhoto yarn={yarn} onChanged={invalidate} />

          {editing ? (
            <EditYarnForm yarn={yarn} onSaved={() => { invalidate(); setEditing(false); }} onCancel={() => setEditing(false)} />
          ) : (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
              {yarn.weight_notation && (<><dt className="text-muted-foreground">Weight notation</dt><dd>{yarn.weight_notation}</dd></>)}
              {yarn.fiber_content && (<><dt className="text-muted-foreground">Fiber</dt><dd>{yarn.fiber_content}</dd></>)}
              {yarn.color_name && (<><dt className="text-muted-foreground">Color</dt><dd className="flex items-center gap-1.5">{yarn.color_hex && <span className="inline-block h-3.5 w-3.5 rounded-full border" style={{ backgroundColor: yarn.color_hex }} />}{yarn.color_name}</dd></>)}
              {yarn.unit_yardage && (<><dt className="text-muted-foreground">Yardage / unit</dt><dd>{yarn.unit_yardage} yds</dd></>)}
              {(yarn.unit_weight_oz || yarn.unit_weight_g) && (<><dt className="text-muted-foreground">Weight / unit</dt><dd>{[yarn.unit_weight_oz && `${yarn.unit_weight_oz} oz`, yarn.unit_weight_g && `${yarn.unit_weight_g} g`].filter(Boolean).join(" / ")}</dd></>)}
              {yarn.yards_per_pound && (<><dt className="text-muted-foreground">Yards / pound</dt><dd>{yarn.yards_per_pound}</dd></>)}
              {(yarn.sett_min || yarn.sett_max) && (<><dt className="text-muted-foreground">Sett (epi)</dt><dd>{yarn.sett_min && yarn.sett_max ? `${yarn.sett_min}–${yarn.sett_max}` : yarn.sett_min ?? yarn.sett_max}</dd></>)}
              {yarn.purchase_source && (<><dt className="text-muted-foreground">Purchased from</dt><dd>{yarn.purchase_source}</dd></>)}
              {yarn.purchase_price && (<><dt className="text-muted-foreground">Price / unit</dt><dd>${yarn.purchase_price}</dd></>)}
              {yarn.purchase_date && (<><dt className="text-muted-foreground">Purchase date</dt><dd>{new Date(yarn.purchase_date + "T00:00:00").toLocaleDateString()}</dd></>)}
            </dl>
          )}
          {!editing && yarn.notes && <p className="text-sm text-muted-foreground whitespace-pre-wrap">{yarn.notes}</p>}
        </section>

        {/* Skeins */}
        <section>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground uppercase tracking-wide">
            Skeins
            <span className="ml-1.5 normal-case">
              — {yarn.available_count} available of {yarn.skein_count} total
            </span>
          </h2>

          {yarn.skeins.length > 0 && (
            <ul className="mb-4 rounded-md border divide-y divide-border px-3">
              {yarn.skeins.map((s) => (
                <SkeinRow key={s.id} yarn={yarn} skein={s} onChanged={invalidate} />
              ))}
            </ul>
          )}

          <AddSkeinsForm yarn={yarn} onAdded={invalidate} />
        </section>

        {/* Delete */}
        <section className="border-t pt-6">
          {!confirmDelete ? (
            <Button variant="outline" size="sm" onClick={() => setConfirmDelete(true)}>Delete yarn record</Button>
          ) : (
            <div className="flex items-center gap-3">
              <p className="text-sm text-destructive">Delete this yarn and all skein records? This cannot be undone.</p>
              <Button variant="outline" size="sm" onClick={() => setConfirmDelete(false)} disabled={deleting}>Cancel</Button>
              <Button size="sm" onClick={handleDelete} disabled={deleting} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
                {deleting ? "Deleting…" : "Confirm delete"}
              </Button>
            </div>
          )}
        </section>

      {showClone && (
        <CloneYarnModal
          yarn={yarn}
          onSuccess={(newId) => { setShowClone(false); navigate(`/yarn/${newId}`); }}
          onClose={() => setShowClone(false)}
        />
      )}
    </div>
  );
}
