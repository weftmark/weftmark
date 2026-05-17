import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getWarpingPlan, type WarpingPlan, type ColorStat } from "@/api/projects";
import { AppIcons } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { TieUpDiagram } from "@/components/TieUpDiagram";

function Swatch({ hex }: { hex: string | null }) {
  if (!hex) return <span className="inline-block h-4 w-4 rounded border border-border bg-muted" />;
  return (
    <span
      className="inline-block h-4 w-4 rounded border border-border/50"
      style={{ backgroundColor: hex }}
      title={hex}
    />
  );
}

function ColorTable({ rows, label }: { rows: ColorStat[]; label: string }) {
  if (rows.length === 0) return null;
  return (
    <section>
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2 print:text-black">{label}</h2>
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-border text-muted-foreground text-xs">
            <th className="py-1.5 text-left font-medium w-8">Color</th>
            <th className="py-1.5 text-left font-medium">Hex</th>
            <th className="py-1.5 text-right font-medium">Count</th>
            <th className="py-1.5 text-right font-medium">%</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.hex} className="border-b border-border/50">
              <td className="py-1.5"><Swatch hex={row.hex} /></td>
              <td className="py-1.5 font-mono text-xs">{row.hex}</td>
              <td className="py-1.5 text-right tabular-nums">{row.count}</td>
              <td className="py-1.5 text-right tabular-nums text-muted-foreground">{row.percentage}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function ColorRuns({ plan }: { plan: WarpingPlan }) {
  if (!plan.warp_color_runs || plan.warp_color_runs.length === 0) return null;
  return (
    <section>
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2 print:text-black">
        Beam Winding Order
      </h2>
      <p className="text-xs text-muted-foreground mb-3">
        Wind the warp beam in this order, keeping each color group together.
      </p>
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-border text-muted-foreground text-xs">
            <th className="py-1.5 text-left font-medium w-10">#</th>
            <th className="py-1.5 text-left font-medium w-8">Color</th>
            <th className="py-1.5 text-left font-medium">Hex</th>
            <th className="py-1.5 text-right font-medium">Ends</th>
            <th className="py-1.5 text-right font-medium">Range</th>
          </tr>
        </thead>
        <tbody>
          {plan.warp_color_runs.map((run, i) => (
            <tr key={i} className="border-b border-border/50">
              <td className="py-1.5 text-muted-foreground text-xs">{i + 1}</td>
              <td className="py-1.5"><Swatch hex={run.color} /></td>
              <td className="py-1.5 font-mono text-xs">{run.color ?? "—"}</td>
              <td className="py-1.5 text-right tabular-nums font-medium">{run.count}</td>
              <td className="py-1.5 text-right tabular-nums text-muted-foreground text-xs">
                {run.start_end}–{run.end_end}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function ThreadingTable({ plan }: { plan: WarpingPlan }) {
  if (!plan.threading || plan.threading.length === 0) return null;
  return (
    <section>
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2 print:text-black">
        Threading Sequence
      </h2>
      <p className="text-xs text-muted-foreground mb-3">
        Thread each warp end through the listed shaft(s) in order.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse min-w-[320px]">
          <thead>
            <tr className="border-b border-border text-muted-foreground text-xs">
              <th className="py-1.5 text-right font-medium w-16 pr-4">End</th>
              <th className="py-1.5 text-left font-medium w-24">Shaft(s)</th>
              <th className="py-1.5 text-left font-medium w-8">Color</th>
              <th className="py-1.5 text-left font-medium">Hex</th>
            </tr>
          </thead>
          <tbody>
            {plan.threading.map((entry) => (
              <tr key={entry.end} className={`border-b border-border/30 ${entry.end % 10 === 0 ? "border-b-border" : ""}`}>
                <td className="py-0.5 text-right pr-4 tabular-nums text-muted-foreground text-xs">{entry.end}</td>
                <td className="py-0.5 font-medium tabular-nums">
                  {entry.shafts.length > 0 ? entry.shafts.join(", ") : "—"}
                </td>
                <td className="py-0.5"><Swatch hex={entry.color} /></td>
                <td className="py-0.5 font-mono text-xs text-muted-foreground">{entry.color ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function TieUpSection({ plan }: { plan: WarpingPlan }) {
  if (!plan.has_tieup || !plan.tieup || !plan.tieup_num_shafts || !plan.tieup_num_treadles) return null;
  return (
    <section>
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2 print:text-black">
        Treadle Tie-Up
      </h2>
      <p className="text-xs text-muted-foreground mb-3">
        Filled squares show which shafts are connected to each treadle.
        Columns = treadles (left to right), rows = shafts (top to bottom).
      </p>
      <div className="overflow-x-auto">
        <TieUpDiagram
          tieup={plan.tieup}
          numShafts={plan.tieup_num_shafts}
          numTreadles={plan.tieup_num_treadles}
        />
      </div>
    </section>
  );
}

export function WarpingPlanPage() {
  const { id } = useParams<{ id: string }>();
  const { data: plan, isLoading, isError } = useQuery({
    queryKey: ["warping-plan", id],
    queryFn: () => getWarpingPlan(id!),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-40">
        <AppIcons.spinner className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isError || !plan) {
    return (
      <div className="flex flex-col items-center justify-center h-40 gap-3">
        <p className="text-sm text-muted-foreground">Failed to load warping plan.</p>
        <Link to={`/projects/${id}`}>
          <Button variant="outline" size="sm">Back to project</Button>
        </Link>
      </div>
    );
  }

  const warpLengthM = plan.warp_length_cm != null ? (plan.warp_length_cm / 100).toFixed(2) : null;

  return (
    <div className="min-h-full bg-background">
      {/* Toolbar — hidden on print */}
      <div className="print:hidden sticky top-0 z-10 flex items-center gap-3 border-b border-border bg-card px-4 py-2.5">
        <Link
          to={`/projects/${id}/track`}
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <AppIcons.chevronRight className="h-4 w-4 rotate-180" />
          Back to tracker
        </Link>
        <span className="text-border">|</span>
        <Link
          to={`/projects/${id}`}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          Project overview
        </Link>
        <div className="ml-auto">
          <Button size="sm" onClick={() => window.print()}>
            <AppIcons.print className="h-4 w-4 mr-1.5" />
            Print
          </Button>
        </div>
      </div>

      {/* Report body */}
      <div className="mx-auto max-w-3xl px-6 py-8 space-y-8 print:px-0 print:py-4 print:space-y-6">
        {/* Report header */}
        <div className="border-b border-border pb-4">
          <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Warping Plan</p>
          <h1 className="text-2xl font-bold">{plan.draft_name}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {plan.project_type === "lift" ? "Lift tracking" : "Treadle tracking"}
            {" · "}
            Generated {new Date().toLocaleDateString()}
          </p>
        </div>

        {/* Summary */}
        <section>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-3 print:text-black">
            Loom Setup
          </h2>
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-3 text-sm">
            <div>
              <dt className="text-xs text-muted-foreground">Warp ends</dt>
              <dd className="font-semibold mt-0.5">{plan.warp_threads ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Total picks</dt>
              <dd className="font-semibold mt-0.5">{plan.total_picks ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Shafts</dt>
              <dd className="font-semibold mt-0.5">{plan.num_shafts ?? "—"}</dd>
            </div>
            {plan.project_type === "treadle" && (
              <div>
                <dt className="text-xs text-muted-foreground">Treadles</dt>
                <dd className="font-semibold mt-0.5">{plan.num_treadles ?? "—"}</dd>
              </div>
            )}
            {plan.epi != null && (
              <div>
                <dt className="text-xs text-muted-foreground">EPI</dt>
                <dd className="font-semibold mt-0.5">{plan.epi}</dd>
              </div>
            )}
            {warpLengthM != null && (
              <div>
                <dt className="text-xs text-muted-foreground">Warp length</dt>
                <dd className="font-semibold mt-0.5">{warpLengthM} m</dd>
              </div>
            )}
          </dl>
        </section>

        <ColorTable rows={plan.warp_color_summary} label="Warp Colors" />
        <ColorTable rows={plan.weft_color_summary} label="Weft Colors" />
        <TieUpSection plan={plan} />
        <ColorRuns plan={plan} />
        <ThreadingTable plan={plan} />

        {!plan.has_threading && (
          <p className="text-sm text-muted-foreground italic">
            Threading sequence not available — this WIF file does not contain a [THREADING] section.
          </p>
        )}
      </div>
    </div>
  );
}
