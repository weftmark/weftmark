import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getSharedProject } from "@/api/projects";
import { PROJECT_STATUS_LABELS } from "@/api/projects";
import { WeftmarkLogo } from "@/components/WeftmarkLogo";
import { PublicFooter } from "@/components/PublicFooter";

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    created: "bg-stone-100 text-stone-600",
    active: "bg-amber-100 text-amber-800",
    completed: "bg-emerald-100 text-emerald-800",
    abandoned: "bg-rose-100 text-rose-700",
  };
  const label = PROJECT_STATUS_LABELS[status as keyof typeof PROJECT_STATUS_LABELS] ?? status;
  return (
    <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${colors[status] ?? "bg-stone-100 text-stone-600"}`}>
      {label}
    </span>
  );
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2.5 border-b border-stone-100 last:border-0">
      <span className="text-sm text-stone-500 shrink-0">{label}</span>
      <span className="text-sm text-stone-800 text-right">{value}</span>
    </div>
  );
}

export function SharedProjectPage() {
  const { slug } = useParams<{ slug: string }>();

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["shared-project", slug],
    queryFn: () => getSharedProject(slug!),
    enabled: !!slug,
    retry: false,
  });

  const isExpired = (error as { status?: number } | null)?.status === 410;
  const isNotFound = (error as { status?: number } | null)?.status === 404;

  return (
    <div className="flex min-h-screen flex-col bg-stone-50 text-stone-900">
      <header className="border-b border-stone-200 bg-stone-50 px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center gap-3">
          <Link to="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
            <WeftmarkLogo className="h-8 w-auto text-amber-800" />
            <span className="text-lg font-semibold tracking-tight" style={{ fontFamily: '"Segoe UI", system-ui, sans-serif' }}>
              weftmark
            </span>
          </Link>
        </div>
      </header>

      <main className="flex-1 px-6 py-12">
        <div className="mx-auto max-w-2xl">
          {isLoading && (
            <div className="text-sm text-stone-400 text-center mt-16">Loading…</div>
          )}

          {isError && isExpired && (
            <div className="text-center space-y-3 mt-16">
              <h1 className="text-2xl font-bold text-stone-800">Link expired</h1>
              <p className="text-stone-500 text-sm">This share link is no longer active.</p>
            </div>
          )}

          {isError && isNotFound && !isExpired && (
            <div className="text-center space-y-3 mt-16">
              <h1 className="text-2xl font-bold text-stone-800">Not found</h1>
              <p className="text-stone-500 text-sm">This share link does not exist or has been revoked.</p>
            </div>
          )}

          {isError && !isExpired && !isNotFound && (
            <div className="text-center space-y-3 mt-16">
              <h1 className="text-2xl font-bold text-stone-800">Something went wrong</h1>
              <p className="text-stone-500 text-sm">Unable to load this shared project.</p>
            </div>
          )}

          {data && (
            <div className="space-y-6">
              <div className="space-y-1">
                <div className="flex items-center gap-3 flex-wrap">
                  <h1 className="text-2xl font-bold tracking-tight text-stone-900">{data.project_name}</h1>
                  <StatusBadge status={data.project_status} />
                </div>
                <p className="text-sm text-stone-500">
                  Shared by <span className="font-medium text-stone-700">{data.owner_display_name}</span>
                  {" · "}
                  <span className="capitalize">{data.project_type} tracking</span>
                </p>
              </div>

              <div className="rounded-lg border border-stone-200 bg-white px-4 py-1 divide-y divide-stone-50">
                <InfoRow label="Draft" value={data.draft_name} />
                {data.draft_num_shafts != null && (
                  <InfoRow label="Shafts" value={data.draft_num_shafts} />
                )}
                {data.draft_num_treadles != null && data.project_type === "treadle" && (
                  <InfoRow label="Treadles" value={data.draft_num_treadles} />
                )}
                <InfoRow label="Total picks" value={data.total_picks.toLocaleString()} />
                <InfoRow label="Items" value={data.num_items} />
                {data.project_status === "active" && (
                  <InfoRow
                    label="Progress"
                    value={`Pick ${data.current_pick.toLocaleString()} of ${data.total_picks.toLocaleString()}${data.num_items > 1 ? ` (item ${data.current_item} of ${data.num_items})` : ""}`}
                  />
                )}
                {data.completed_at && (
                  <InfoRow
                    label="Completed"
                    value={new Date(data.completed_at).toLocaleDateString()}
                  />
                )}
                {data.abandoned_at && (
                  <InfoRow
                    label="Abandoned"
                    value={new Date(data.abandoned_at).toLocaleDateString()}
                  />
                )}
                <InfoRow
                  label="Started"
                  value={new Date(data.created_at).toLocaleDateString()}
                />
              </div>

              {data.share_expires_at && (
                <p className="text-xs text-stone-400 text-center">
                  Link expires {new Date(data.share_expires_at).toLocaleDateString()}
                </p>
              )}
            </div>
          )}
        </div>
      </main>

      <PublicFooter />
    </div>
  );
}
