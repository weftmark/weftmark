import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listLooms, type Loom } from "@/api/looms";
import { NewLoomModal } from "@/components/looms/NewLoomModal";
import { Button } from "@/components/ui/button";

function LoomCard({ loom }: { loom: Loom }) {
  const v = loom.current_version;
  return (
    <Link
      to={`/looms/${loom.id}`}
      className="rounded-lg border p-5 hover:border-ring transition-colors block"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-medium">{loom.manufacturer} {loom.model_name}</p>
          {loom.serial_number && (
            <p className="text-xs text-muted-foreground">S/N: {loom.serial_number}</p>
          )}
        </div>
        <div className="text-right text-xs text-muted-foreground shrink-0">
          {v && <span>{v.num_shafts}S / {v.num_treadles}T</span>}
        </div>
      </div>
      {v?.weaving_width && (
        <p className="mt-2 text-sm text-muted-foreground">
          Weaving width: {v.weaving_width} {v.weaving_width_unit}
        </p>
      )}
      <div className="mt-2 flex gap-2">
        {loom.supports_lift_tracking && (
          <span className="rounded bg-muted px-1.5 py-0.5 text-xs">lift tracking</span>
        )}
        {loom.supports_treadle_tracking && (
          <span className="rounded bg-muted px-1.5 py-0.5 text-xs">treadle tracking</span>
        )}
      </div>
    </Link>
  );
}

export function LoomsPage() {
  const [showNew, setShowNew] = useState(false);
  const queryClient = useQueryClient();

  const { data: looms, isLoading, error } = useQuery({
    queryKey: ["looms"],
    queryFn: listLooms,
  });

  const handleSuccess = () => {
    setShowNew(false);
    queryClient.invalidateQueries({ queryKey: ["looms"] });
  };

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">
            ← Dashboard
          </Link>
          <span className="font-semibold">Equipment</span>
        </div>
        <Button size="sm" onClick={() => setShowNew(true)}>
          New loom
        </Button>
      </header>

      <main className="flex-1 p-6 max-w-4xl mx-auto w-full">
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {error && (
          <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            Failed to load looms
          </p>
        )}
        {looms && looms.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <p className="text-muted-foreground">No looms yet.</p>
            <Button className="mt-4" onClick={() => setShowNew(true)}>
              Add your first loom
            </Button>
          </div>
        )}
        {looms && looms.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2">
            {looms.map((l) => (
              <LoomCard key={l.id} loom={l} />
            ))}
          </div>
        )}
      </main>

      {showNew && (
        <NewLoomModal onSuccess={handleSuccess} onClose={() => setShowNew(false)} />
      )}
    </div>
  );
}
