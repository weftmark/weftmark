import React, { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getWarpingPlan, getProject, type WarpingPlan, type ColorStat, type ProjectDetail } from "@/api/projects";
import { AppIcons } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { TieUpDiagram } from "@/components/TieUpDiagram";
import { convertLength, formatApproxLength, type LengthUnit } from "@/lib/units";

type ReportTab = "summary" | "winding" | "tieup" | "threading";

const TABS: { id: ReportTab; label: string }[] = [
  { id: "summary", label: "Summary" },
  { id: "winding", label: "Warping Board" },
  { id: "tieup", label: "Tie-Up" },
  { id: "threading", label: "Threading" },
];

function approximateColorName(hex: string): string {
  if (!hex || hex.length < 7) return "";
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const delta = max - min;
  const l = (max + min) / 2;

  if (delta < 0.06) {
    if (l < 0.08) return "Black";
    if (l < 0.22) return "Very Dark Grey";
    if (l < 0.42) return "Dark Grey";
    if (l < 0.62) return "Grey";
    if (l < 0.82) return "Light Grey";
    if (l < 0.93) return "Off White";
    return "White";
  }

  let h: number;
  if (max === r) h = ((g - b) / delta + 6) % 6 * 60;
  else if (max === g) h = ((b - r) / delta + 2) * 60;
  else h = ((r - g) / delta + 4) * 60;

  const s = l > 0.5 ? delta / (2 - max - min) : delta / (max + min);

  // Browns: orange-ish hue, low-medium saturation, darker lightness
  if (h >= 10 && h <= 52 && s < 0.55 && l < 0.48) {
    if (l < 0.12) return "Very Dark Brown";
    if (l < 0.24) return "Dark Brown";
    if (l < 0.36) return "Brown";
    return "Tan";
  }

  const prefix =
    l < 0.18 ? "Very Dark " :
    l < 0.32 ? "Dark " :
    l > 0.78 ? "Pale " :
    l > 0.63 ? "Light " : "";

  let name: string;
  if (h < 12 || h >= 348) name = "Red";
  else if (h < 26) name = "Red Orange";
  else if (h < 46) name = "Orange";
  else if (h < 65) name = "Yellow";
  else if (h < 80) name = "Yellow Green";
  else if (h < 155) name = "Green";
  else if (h < 178) name = "Teal";
  else if (h < 200) name = "Cyan";
  else if (h < 255) name = "Blue";
  else if (h < 290) name = "Purple";
  else if (h < 325) name = "Violet";
  else name = "Pink";

  return `${prefix}${name}`.trim();
}

interface WarpSetup {
  itemLengthCm: number | null;
  numItems: number;
  wasteBetweenCm: number | null;
  warpWasteCm: number | null;
  approxWarpLengthCm: number | null;
  displayUnit: LengthUnit;
  missingItemLength: boolean;
  missingWarpWaste: boolean;
  missingWasteBetween: boolean;
}

function computeWarpSetup(project: ProjectDetail): WarpSetup {
  const displayUnit = (project.length_unit as LengthUnit) || "cm";
  const itemLengthCm = project.finished_length_per_item != null ? parseFloat(project.finished_length_per_item) : null;
  const wasteBetweenCm = project.waste_between_items != null ? parseFloat(project.waste_between_items) : null;
  const numItems = project.num_items || 1;

  let warpWasteCm: number | null = null;
  if (project.warp_waste_allowance != null) {
    warpWasteCm = parseFloat(project.warp_waste_allowance);
  } else if (project.loom_warp_waste_allowance != null && project.loom_warp_waste_unit) {
    warpWasteCm = convertLength(
      parseFloat(project.loom_warp_waste_allowance),
      project.loom_warp_waste_unit as LengthUnit,
      "cm",
    );
  }

  // Require item length at minimum; warp waste defaults to 0 if unset but shows a warning
  const approxWarpLengthCm =
    itemLengthCm != null
      ? itemLengthCm * numItems
        + (wasteBetweenCm ?? 0) * Math.max(0, numItems - 1)
        + (warpWasteCm ?? 0)
      : null;

  return {
    itemLengthCm,
    numItems,
    wasteBetweenCm,
    warpWasteCm,
    approxWarpLengthCm,
    displayUnit,
    missingItemLength: itemLengthCm == null,
    missingWarpWaste: warpWasteCm == null,
    missingWasteBetween: numItems > 1 && wasteBetweenCm == null,
  };
}

function MissingParamsBanner({
  setup,
  projectId,
  loomId,
}: {
  setup: WarpSetup;
  projectId: string;
  loomId: string | null;
}) {
  const items: React.ReactNode[] = [];

  if (setup.missingItemLength) {
    items.push(
      <li key="item-length">
        <span className="font-medium">Item length</span> is not set —{" "}
        <Link
          to={`/projects/${projectId}`}
          className="underline underline-offset-2 hover:text-foreground"
        >
          set it in project warp setup
        </Link>
      </li>,
    );
  }

  if (setup.missingWarpWaste) {
    if (loomId) {
      items.push(
        <li key="warp-waste">
          <span className="font-medium">Warp waste allowance</span> is not set —{" "}
          <Link
            to={`/looms/${loomId}`}
            className="underline underline-offset-2 hover:text-foreground"
          >
            set a default on your loom
          </Link>
          {" "}or{" "}
          <Link
            to={`/projects/${projectId}`}
            className="underline underline-offset-2 hover:text-foreground"
          >
            add a project override
          </Link>
        </li>,
      );
    } else {
      items.push(
        <li key="warp-waste">
          <span className="font-medium">Warp waste allowance</span> is not set —{" "}
          <Link
            to={`/projects/${projectId}`}
            className="underline underline-offset-2 hover:text-foreground"
          >
            set a project override
          </Link>
          {" "}or{" "}
          <Link
            to={`/projects/${projectId}`}
            className="underline underline-offset-2 hover:text-foreground"
          >
            assign a loom
          </Link>
          {" "}with a warp waste default
        </li>,
      );
    }
  }

  if (setup.missingWasteBetween) {
    items.push(
      <li key="waste-between">
        <span className="font-medium">Waste between items</span> is not set for this{" "}
        {setup.numItems}-item project —{" "}
        <Link
          to={`/projects/${projectId}`}
          className="underline underline-offset-2 hover:text-foreground"
        >
          set it in project warp setup
        </Link>
      </li>,
    );
  }

  if (items.length === 0) return null;

  const lengthColAffected = setup.missingItemLength || (setup.missingWarpWaste && setup.approxWarpLengthCm == null);

  return (
    <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm print:hidden">
      <p className="font-medium text-foreground mb-1.5">
        {lengthColAffected
          ? "Approx length cannot be calculated — missing parameters:"
          : "Length calculation is incomplete — some parameters are missing:"}
      </p>
      <ul className="space-y-1 text-muted-foreground list-disc list-inside">
        {items}
      </ul>
    </div>
  );
}

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

function SummarySection({ plan }: { plan: WarpingPlan }) {
  const warpLengthM = plan.warp_length_cm != null ? (plan.warp_length_cm / 100).toFixed(2) : null;
  return (
    <div className="space-y-8">
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
      <WarpColorSummary rows={plan.warp_color_summary} />
    </div>
  );
}

function WarpColorSummary({ rows }: { rows: ColorStat[] }) {
  if (rows.length === 0) return null;
  return (
    <section>
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2 print:text-black">
        Warp Colors
      </h2>
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

function WindingSection({
  plan,
  project,
}: {
  plan: WarpingPlan;
  project?: ProjectDetail;
}) {
  const setup = project ? computeWarpSetup(project) : null;
  const hasMissing = setup
    ? setup.missingItemLength || setup.missingWarpWaste || setup.missingWasteBetween
    : false;

  if (!plan.warp_color_runs || plan.warp_color_runs.length === 0) {
    return <p className="text-sm text-muted-foreground italic">Winding sequence not available — no threading data found.</p>;
  }
  const hasOdd = plan.warp_color_runs.some((r) => r.count % 2 !== 0);
  const showLengthCol = setup?.approxWarpLengthCm != null;

  return (
    <div className="space-y-6">
      {setup && hasMissing && (
        <MissingParamsBanner
          setup={setup}
          projectId={plan.project_id}
          loomId={project?.loom_id ?? null}
        />
      )}
      {setup && (
        <section className="border border-border rounded-md p-4 bg-muted/30">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-3 print:text-black">
            Length Parameters
          </h2>
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-3 text-sm mb-3">
            {setup.warpWasteCm != null && (
              <div>
                <dt className="text-xs text-muted-foreground">Warp waste</dt>
                <dd className="font-semibold mt-0.5">
                  {formatApproxLength(setup.warpWasteCm, setup.displayUnit)}
                </dd>
              </div>
            )}
            {setup.itemLengthCm != null && (
              <div>
                <dt className="text-xs text-muted-foreground">Item length</dt>
                <dd className="font-semibold mt-0.5">
                  {formatApproxLength(setup.itemLengthCm, setup.displayUnit)}
                </dd>
              </div>
            )}
            <div>
              <dt className="text-xs text-muted-foreground">Number of items</dt>
              <dd className="font-semibold mt-0.5">{setup.numItems}</dd>
            </div>
            {setup.numItems > 1 && setup.wasteBetweenCm != null && (
              <div>
                <dt className="text-xs text-muted-foreground">Between items</dt>
                <dd className="font-semibold mt-0.5">
                  {formatApproxLength(setup.wasteBetweenCm, setup.displayUnit)}
                </dd>
              </div>
            )}
          </dl>
          {setup.approxWarpLengthCm != null && (
            <div className="border-t border-border pt-3 text-sm">
              <span className="text-muted-foreground">Approx warp length: </span>
              <span className="font-bold">{formatApproxLength(setup.approxWarpLengthCm, setup.displayUnit)}</span>
              {setup.missingWarpWaste && (
                <span className="ml-2 text-xs text-muted-foreground">(excludes warp waste)</span>
              )}
            </div>
          )}
        </section>
      )}
      <section>
        <h2 className="text-base font-semibold mb-1 print:text-black">Winding Sequence</h2>
        <p className="text-xs text-muted-foreground mb-3">
          Wind the warp left to right in this order.
          One loop = one back-and-forth pass on the warping board = 2 ends.
        </p>
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-border text-muted-foreground text-xs">
              <th className="py-1.5 text-left font-medium w-8">#</th>
              <th className="py-1.5 text-left font-medium w-8">Color</th>
              <th className="py-1.5 text-left font-medium">Hex / Name</th>
              <th className="py-1.5 text-right font-medium pr-4">Loops</th>
              <th className="py-1.5 text-right font-medium pr-4">Ends</th>
              {showLengthCol && <th className="py-1.5 text-right font-medium">Approx Length</th>}
              <th className="py-1.5 text-right font-medium">Position</th>
            </tr>
          </thead>
          <tbody>
            {plan.warp_color_runs.map((run, i) => {
              const loops = Math.floor(run.count / 2);
              const odd = run.count % 2 === 1;
              const stepLength =
                showLengthCol && loops > 0
                  ? formatApproxLength(loops * setup!.approxWarpLengthCm!, setup!.displayUnit)
                  : null;
              return (
                <tr key={i} className="border-b border-border/50">
                  <td className="py-2 text-muted-foreground text-xs">{i + 1}</td>
                  <td className="py-2"><Swatch hex={run.color} /></td>
                  <td className="py-2">
                    <span className="font-mono text-xs">{run.color ?? "—"}</span>
                    {run.color && (
                      <span className="ml-2 text-xs text-muted-foreground">
                        {run.color_name || approximateColorName(run.color)}
                      </span>
                    )}
                  </td>
                  <td className="py-2 text-right tabular-nums font-semibold pr-4">
                    {loops > 0 ? loops : ""}
                    {odd && <span className="text-muted-foreground font-normal text-xs ml-1">+1</span>}
                  </td>
                  <td className="py-2 text-right tabular-nums text-muted-foreground pr-4">{run.count}</td>
                  {showLengthCol && (
                    <td className="py-2 text-right tabular-nums text-muted-foreground">
                      {stepLength ?? "—"}
                    </td>
                  )}
                  <td className="py-2 text-right tabular-nums text-muted-foreground text-xs">
                    {run.start_end}–{run.end_end}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {hasOdd && (
          <p className="text-xs text-muted-foreground mt-2 italic">
            +1 = one extra single end at the end of that group (half-loop).
          </p>
        )}
      </section>
    </div>
  );
}

function TieUpSection({ plan }: { plan: WarpingPlan }) {
  if (!plan.has_tieup || !plan.tieup || !plan.tieup_num_shafts || !plan.tieup_num_treadles) {
    return (
      <p className="text-sm text-muted-foreground italic">
        {plan.project_type === "lift"
          ? "Tie-up not applicable for lift-plan projects."
          : "Tie-up not available — this WIF file does not contain a [TIEUP] section."}
      </p>
    );
  }
  return (
    <section>
      <h2 className="text-base font-semibold mb-1 print:text-black">Treadle Tie-Up</h2>
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

function ThreadingSection({ plan }: { plan: WarpingPlan }) {
  if (!plan.has_threading || !plan.threading || plan.threading.length === 0) {
    return (
      <p className="text-sm text-muted-foreground italic">
        Threading sequence not available — this WIF file does not contain a [THREADING] section.
      </p>
    );
  }
  return (
    <section>
      <h2 className="text-base font-semibold mb-1 print:text-black">Threading Sequence</h2>
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
              <th className="py-1.5 text-left font-medium">Hex / Name</th>
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
                <td className="py-0.5">
                  <span className="font-mono text-xs text-muted-foreground">{entry.color ?? "—"}</span>
                  {entry.color && (
                    <span className="ml-2 text-xs text-muted-foreground">
                      {approximateColorName(entry.color)}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function WarpingPlanPage() {
  const { id } = useParams<{ id: string }>();
  const [tab, setTab] = useState<ReportTab>("winding");
  const { data: plan, isLoading, isError } = useQuery({
    queryKey: ["warping-plan", id],
    queryFn: () => getWarpingPlan(id!),
    enabled: !!id,
  });
  const { data: project } = useQuery({
    queryKey: ["project", id],
    queryFn: () => getProject(id!),
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

  const activeLabel = TABS.find((t) => t.id === tab)?.label ?? "";

  return (
    <div className="h-full overflow-y-auto bg-background">
      {/* Toolbar — hidden on print */}
      <div className="print:hidden sticky top-0 z-10 border-b border-border bg-card">
        {/* Nav row */}
        <div className="flex items-center gap-3 px-4 py-2.5">
          <Link
            to={`/projects/${id}/track`}
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <AppIcons.chevronRight className="h-4 w-4 rotate-180" />
            Back to tracker
          </Link>
          <span className="text-border">|</span>
          <Link to={`/projects/${id}`} className="text-sm text-muted-foreground hover:text-foreground">
            Project overview
          </Link>
          <div className="ml-auto flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                const prev = document.title;
                document.title = `${plan.draft_name} - ${activeLabel} - Weave Plan`;
                window.print();
                document.title = prev;
              }}
            >
              <AppIcons.saveAsPdf className="h-4 w-4 mr-1.5" />
              Save as PDF
            </Button>
            <Button size="sm" onClick={() => window.print()}>
              <AppIcons.print className="h-4 w-4 mr-1.5" />
              Print
            </Button>
          </div>
        </div>
        {/* Tab row */}
        <div className="flex px-4 gap-0">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                tab === t.id
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Report body */}
      <div className="mx-auto max-w-3xl px-6 py-8 print:px-0 print:py-4">
        {/* Report header */}
        <div className="border-b border-border pb-4 mb-8">
          <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Warping Plan</p>
          <h1 className="text-2xl font-bold">{plan.draft_name}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            <span className="print:hidden">
              {plan.project_type === "lift" ? "Lift tracking" : "Treadle tracking"}
              {" · "}
              {activeLabel}
            </span>
            <span className="hidden print:inline">
              {activeLabel} · {plan.project_type === "lift" ? "Lift tracking" : "Treadle tracking"}
              {" · "}Generated {new Date().toLocaleDateString()}
            </span>
          </p>
        </div>

        {tab === "summary" && <SummarySection plan={plan} />}
        {tab === "winding" && <WindingSection plan={plan} project={project} />}
        {tab === "tieup" && <TieUpSection plan={plan} />}
        {tab === "threading" && <ThreadingSection plan={plan} />}
      </div>
    </div>
  );
}
