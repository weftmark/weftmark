import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listYarn, yarnPhotoUrl, type YarnSummary } from "@/api/yarn";
import { AddYarnModal } from "@/components/yarn/AddYarnModal";
import { Button } from "@/components/ui/button";
import { AuthedImage } from "@/components/ui/AuthedImage";

function YarnCard({ yarn }: { yarn: YarnSummary }) {
  const skeinLabel = yarn.skein_count === 0
    ? "No skeins"
    : yarn.available_count === yarn.skein_count
      ? `${yarn.skein_count} available`
      : `${yarn.available_count} of ${yarn.skein_count} available`;

  return (
    <Link
      to={`/yarn/${yarn.id}`}
      className="flex items-start gap-3 rounded-lg border p-4 hover:border-ring transition-colors"
    >
      {yarn.has_photo ? (
        <AuthedImage
          src={yarnPhotoUrl(yarn.id)}
          alt={`${yarn.brand} ${yarn.name}`}
          className="h-14 w-14 rounded-md object-cover border shrink-0"
        />
      ) : yarn.color_hex ? (
        <div
          className="h-14 w-14 rounded-md border shrink-0"
          style={{ backgroundColor: yarn.color_hex }}
        />
      ) : (
        <div className="h-14 w-14 rounded-md border border-dashed shrink-0 flex items-center justify-center">
          <span className="text-xs text-muted-foreground">?</span>
        </div>
      )}

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{yarn.brand}</p>
        <p className="text-sm text-muted-foreground truncate">{yarn.name}</p>
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
          {yarn.weight_notation && <span>{yarn.weight_notation}</span>}
          {yarn.fiber_content && <span>{yarn.fiber_content}</span>}
          {yarn.color_name && <span>{yarn.color_name}</span>}
        </div>
      </div>

      <div className="text-right shrink-0">
        <p className="text-xs text-muted-foreground">{skeinLabel}</p>
        {yarn.unit_yardage && (
          <p className="text-xs text-muted-foreground">{yarn.unit_yardage} yds/unit</p>
        )}
      </div>
    </Link>
  );
}

export function YarnPage() {
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);

  const { data: yarns = [], isLoading, error } = useQuery({
    queryKey: ["yarn"],
    queryFn: listYarn,
  });

  const handleAdded = () => {
    setShowAdd(false);
    queryClient.invalidateQueries({ queryKey: ["yarn"] });
  };

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">← Dashboard</Link>
          <span className="font-semibold">Yarn</span>
        </div>
      </header>

      <main className="flex-1 p-6 max-w-3xl mx-auto w-full">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-semibold">Yarn inventory</h1>
          <Button onClick={() => setShowAdd(true)}>Add yarn</Button>
        </div>

        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {error && <p className="text-sm text-destructive">Failed to load yarn inventory.</p>}

        {!isLoading && yarns.length === 0 && (
          <div className="rounded-lg border border-dashed p-12 text-center">
            <p className="text-sm text-muted-foreground">No yarn yet. Add your first entry to start tracking your stash.</p>
            <Button className="mt-4" onClick={() => setShowAdd(true)}>Add yarn</Button>
          </div>
        )}

        <div className="space-y-2">
          {yarns.map((y) => <YarnCard key={y.id} yarn={y} />)}
        </div>
      </main>

      {showAdd && (
        <AddYarnModal onSuccess={handleAdded} onClose={() => setShowAdd(false)} />
      )}
    </div>
  );
}
