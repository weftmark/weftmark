import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useClerk } from "@clerk/clerk-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";
import {
  listAdminUsers,
  getAdminStats,
  getAdminHealth,
  getAdminVersions,
  patchAdminUser,
  banUser,
  unbanUser,
  elevateToSuperuser,
  listInvites,
  createInvite,
  revokeInvite,
  listPendingSignups,
  approvePendingSignup,
  dismissPendingSignup,
  banPendingSignup,
  getAdminEula,
  createEulaVersion,
  type AdminHealth,
  type ElevateContentSummary,
  type InviteRecord,
  type PendingSignup,
} from "@/api/admin";
import { EulaContent } from "@/components/EulaContent";

type Tab = "users" | "invites" | "stats" | "health" | "eula";

function formatLastActive(iso: string | null): string {
  if (!iso) return "Never";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 2) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

export function AdminPage() {
  const [tab, setTab] = useState<Tab>("users");
  const { user: currentUser } = useAuth();
  const { signOut } = useClerk();

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          {!currentUser?.is_superuser && (
            <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">
              ← Dashboard
            </Link>
          )}
          <span className="font-semibold">Admin</span>
          {currentUser?.is_superuser && (
            <span className="text-xs border rounded px-1.5 py-0.5 text-muted-foreground">superuser</span>
          )}
        </div>
        {currentUser?.is_superuser && (
          <button
            onClick={() => signOut()}
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            Sign out
          </button>
        )}
      </header>

      <main className="flex-1 p-6 max-w-4xl mx-auto w-full space-y-6">
        <div className="flex gap-2 border-b pb-2">
          {(["users", "invites", "stats", "health", "eula"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 text-sm rounded capitalize ${
                tab === t
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        {tab === "users" && <UsersTab />}
        {tab === "invites" && <InvitesTab />}
        {tab === "stats" && <StatsTab />}
        {tab === "health" && <HealthTab />}
        {tab === "eula" && <EulaTab />}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Users tab
// ---------------------------------------------------------------------------

function UsersTab() {
  const qc = useQueryClient();
  const { user: currentUser } = useAuth();
  const [confirmBanId, setConfirmBanId] = useState<string | null>(null);
  const [elevateId, setElevateId] = useState<string | null>(null);
  const [elevateContent, setElevateContent] = useState<ElevateContentSummary | null>(null);

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["admin", "users"],
    queryFn: listAdminUsers,
  });

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { is_active?: boolean; is_admin?: boolean; is_superuser?: boolean } }) =>
      patchAdminUser(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });

  const ban = useMutation({
    mutationFn: (id: string) => banUser(id),
    onSuccess: () => { setConfirmBanId(null); qc.invalidateQueries({ queryKey: ["admin", "users"] }); },
    onError: () => setConfirmBanId(null),
  });

  const unban = useMutation({
    mutationFn: (id: string) => unbanUser(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });

  const elevate = useMutation({
    mutationFn: ({ id, force }: { id: string; force: boolean }) => elevateToSuperuser(id, force),
    onSuccess: () => {
      setElevateId(null);
      setElevateContent(null);
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
    },
    onError: (err: Error) => {
      try {
        const body = JSON.parse(err.message);
        if (body?.detail?.code === "has_content") {
          setElevateContent(body.detail.summary);
          return;
        }
      } catch {}
      setElevateId(null);
      setElevateContent(null);
    },
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground">{users.length} user{users.length !== 1 ? "s" : ""}</p>
      <div className="divide-y border rounded-lg overflow-hidden">
        {users.map((u) => (
          <div key={u.id} className="flex items-center justify-between px-4 py-3 bg-background gap-4">
            <div className="min-w-0">
              <p className="text-sm font-medium truncate">{u.display_name}</p>
              <p className="text-xs text-muted-foreground truncate">{u.email}</p>
              <p className="text-xs text-muted-foreground">
                Last active: {formatLastActive(u.last_active_at)}
                {" · "}
                {u.counts.projects}p · {u.counts.looms}l · {u.counts.activities_active} active / {u.counts.activities_completed} done
              </p>
              {u.approved_by_name && (
                <p className="text-xs text-muted-foreground">
                  Approved by {u.approved_by_name}{u.approved_by_email ? ` (${u.approved_by_email})` : ""}
                </p>
              )}
            </div>
            <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
              {u.is_superuser && (
                <span className="text-xs border rounded px-1.5 py-0.5 text-muted-foreground">superuser</span>
              )}
              {u.is_admin && !u.is_superuser && (
                <span className="text-xs border rounded px-1.5 py-0.5 text-muted-foreground">admin</span>
              )}
              {u.clerk_banned ? (
                <span className="text-xs border border-destructive rounded px-1.5 py-0.5 text-destructive">banned</span>
              ) : !u.is_active ? (
                <span className="text-xs border border-destructive rounded px-1.5 py-0.5 text-destructive">deactivated</span>
              ) : null}

              {confirmBanId === u.id ? (
                <>
                  <span className="text-xs text-destructive font-medium">Ban {u.display_name}?</span>
                  <Button size="sm" variant="destructive" disabled={ban.isPending} onClick={() => ban.mutate(u.id)}>
                    Confirm
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setConfirmBanId(null)}>Cancel</Button>
                </>
              ) : elevateId === u.id ? (
                <>
                  {elevateContent ? (
                    <span className="text-xs text-destructive font-medium">
                      Has {[
                        elevateContent.activities && `${elevateContent.activities} activities`,
                        elevateContent.looms && `${elevateContent.looms} looms`,
                        elevateContent.projects && `${elevateContent.projects} projects`,
                        elevateContent.yarn && `${elevateContent.yarn} yarn`,
                      ].filter(Boolean).join(", ")} — all will be deleted.
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground font-medium">Make {u.display_name} a superuser?</span>
                  )}
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={elevate.isPending}
                    onClick={() => elevate.mutate({ id: u.id, force: !!elevateContent })}
                  >
                    Confirm
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => { setElevateId(null); setElevateContent(null); }}>
                    Cancel
                  </Button>
                </>
              ) : (
                <>
                  {currentUser?.is_superuser && (
                    <>
                      {!u.is_superuser && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={patch.isPending || u.clerk_banned}
                          onClick={() => patch.mutate({ id: u.id, body: { is_admin: !u.is_admin } })}
                        >
                          {u.is_admin ? "Remove admin" : "Make admin"}
                        </Button>
                      )}
                      {!u.is_superuser && u.is_admin && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={elevate.isPending || u.clerk_banned}
                          onClick={() => { setElevateId(u.id); elevate.mutate({ id: u.id, force: false }); }}
                        >
                          Make superuser
                        </Button>
                      )}
                    </>
                  )}
                  {!u.is_superuser && (
                    u.clerk_banned ? (
                      <Button size="sm" variant="outline" disabled={unban.isPending} onClick={() => unban.mutate(u.id)}>
                        Unban
                      </Button>
                    ) : (
                      <>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={patch.isPending || (u.is_active && u.is_admin)}
                          title={u.is_active && u.is_admin ? "Remove admin rights before deactivating" : undefined}
                          onClick={() => patch.mutate({ id: u.id, body: { is_active: !u.is_active } })}
                        >
                          {u.is_active ? "Deactivate" : "Reactivate"}
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          disabled={u.is_admin}
                          title={u.is_admin ? "Remove admin rights before banning" : undefined}
                          onClick={() => setConfirmBanId(u.id)}
                        >
                          Ban
                        </Button>
                      </>
                    )
                  )}
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Invites tab
// ---------------------------------------------------------------------------

const INVITE_HISTORY_PAGE_SIZE = 20;

function InvitesTab() {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);
  const [historyPage, setHistoryPage] = useState(0);

  const { data: invites = [], isLoading } = useQuery({
    queryKey: ["admin", "invites"],
    queryFn: listInvites,
  });

  const { data: pendingSignups = [] } = useQuery({
    queryKey: ["admin", "pending-signups"],
    queryFn: listPendingSignups,
  });

  const send = useMutation({
    mutationFn: (addr: string) => createInvite(addr),
    onSuccess: (_, addr) => {
      setSent(addr);
      setEmail("");
      setError(null);
      qc.invalidateQueries({ queryKey: ["admin", "invites"] });
    },
    onError: (err: Error) => setError(err.message),
  });

  const removePending = (id: string) =>
    qc.setQueryData(["admin", "pending-signups"], (old: PendingSignup[] | undefined) =>
      old ? old.filter((p) => p.id !== id) : []
    );

  const approve = useMutation({
    mutationFn: (id: string) => approvePendingSignup(id),
    onSuccess: (_, id) => { removePending(id); qc.invalidateQueries({ queryKey: ["admin", "users"] }); },
  });

  const dismiss = useMutation({
    mutationFn: (id: string) => dismissPendingSignup(id),
    onSuccess: (_, id) => removePending(id),
  });

  const banSignup = useMutation({
    mutationFn: (id: string) => banPendingSignup(id),
    onSuccess: (_, id) => removePending(id),
  });

  const revoke = useMutation({
    mutationFn: (id: string) => revokeInvite(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "invites"] }),
  });

  const pending = invites.filter((i) => !i.accepted_at && !i.revoked_at && new Date(i.expires_at) > new Date());
  const past = invites.filter((i) => i.accepted_at || i.revoked_at || new Date(i.expires_at) <= new Date());

  return (
    <div className="space-y-6">
      {pendingSignups.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-medium">Waiting to join ({pendingSignups.length})</h2>
          <p className="text-xs text-muted-foreground">
            These users signed up through Clerk but have no invite. Add them to the database or dismiss.
          </p>
          <div className="divide-y border rounded-lg overflow-hidden">
            {pendingSignups.map((ps) => (
              <PendingSignupRow
                key={ps.id}
                signup={ps}
                onApprove={() => approve.mutate(ps.id)}
                onDismiss={() => dismiss.mutate(ps.id)}
                onBan={() => banSignup.mutate(ps.id)}
                isWorking={approve.isPending || dismiss.isPending || banSignup.isPending}
              />
            ))}
          </div>
        </div>
      )}

      <div className="border rounded-lg p-4 space-y-3">
        <h2 className="text-sm font-medium">Send invite</h2>
        <div className="flex gap-2">
          <input
            type="email"
            placeholder="email@example.com"
            value={email}
            onChange={(e) => { setEmail(e.target.value); setSent(null); setError(null); }}
            onKeyDown={(e) => e.key === "Enter" && email && send.mutate(email)}
            className="flex-1 text-sm border rounded px-3 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <Button size="sm" disabled={!email || send.isPending} onClick={() => send.mutate(email)}>
            Send
          </Button>
        </div>
        {sent && <p className="text-xs text-green-600">Invite sent to {sent}</p>}
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <>
          {pending.length > 0 && (
            <div className="space-y-2">
              <h2 className="text-sm font-medium">Pending ({pending.length})</h2>
              <div className="divide-y border rounded-lg overflow-hidden">
                {pending.map((inv) => (
                  <InviteRow key={inv.id} invite={inv} onRevoke={() => revoke.mutate(inv.id)} />
                ))}
              </div>
            </div>
          )}
          {past.length > 0 && (
            <div className="space-y-2">
              <h2 className="text-sm font-medium text-muted-foreground">
                Past invites ({past.length})
              </h2>
              <div className="divide-y border rounded-lg overflow-hidden opacity-60">
                {past.slice(historyPage * INVITE_HISTORY_PAGE_SIZE, (historyPage + 1) * INVITE_HISTORY_PAGE_SIZE).map((inv) => (
                  <InviteRow key={inv.id} invite={inv} />
                ))}
              </div>
              {past.length > INVITE_HISTORY_PAGE_SIZE && (
                <div className="flex items-center justify-between pt-1">
                  <button
                    className="text-xs text-muted-foreground hover:text-foreground disabled:opacity-40"
                    disabled={historyPage === 0}
                    onClick={() => setHistoryPage((p) => p - 1)}
                  >
                    ← Previous
                  </button>
                  <span className="text-xs text-muted-foreground">
                    {historyPage + 1} / {Math.ceil(past.length / INVITE_HISTORY_PAGE_SIZE)}
                  </span>
                  <button
                    className="text-xs text-muted-foreground hover:text-foreground disabled:opacity-40"
                    disabled={(historyPage + 1) * INVITE_HISTORY_PAGE_SIZE >= past.length}
                    onClick={() => setHistoryPage((p) => p + 1)}
                  >
                    Next →
                  </button>
                </div>
              )}
            </div>
          )}
          {invites.length === 0 && <p className="text-sm text-muted-foreground">No invites yet.</p>}
        </>
      )}
    </div>
  );
}

function PendingSignupRow({
  signup,
  onApprove,
  onDismiss,
  onBan,
  isWorking,
}: {
  signup: PendingSignup;
  onApprove: () => void;
  onDismiss: () => void;
  onBan: () => void;
  isWorking: boolean;
}) {
  const [confirming, setConfirming] = useState<"dismiss" | "ban" | null>(null);

  return (
    <div className="flex items-center justify-between px-4 py-3 bg-background gap-4">
      <div className="min-w-0">
        <p className="text-sm font-medium truncate">{signup.display_name || signup.email}</p>
        <p className="text-xs text-muted-foreground truncate">{signup.email}</p>
        <p className="text-xs text-muted-foreground">
          Signed up {new Date(signup.created_at).toLocaleDateString()}
        </p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {confirming === "dismiss" ? (
          <>
            <span className="text-xs text-muted-foreground font-medium">Dismiss?</span>
            <Button size="sm" variant="outline" disabled={isWorking} onClick={() => { setConfirming(null); onDismiss(); }}>
              Confirm
            </Button>
            <Button size="sm" variant="outline" onClick={() => setConfirming(null)}>Cancel</Button>
          </>
        ) : confirming === "ban" ? (
          <>
            <span className="text-xs text-destructive font-medium">Ban?</span>
            <Button size="sm" variant="destructive" disabled={isWorking} onClick={() => { setConfirming(null); onBan(); }}>
              Confirm
            </Button>
            <Button size="sm" variant="outline" onClick={() => setConfirming(null)}>Cancel</Button>
          </>
        ) : (
          <>
            <Button size="sm" disabled={isWorking} onClick={onApprove}>
              Add user
            </Button>
            <Button size="sm" variant="outline" disabled={isWorking} onClick={() => setConfirming("dismiss")}>
              Dismiss
            </Button>
            <Button size="sm" variant="destructive" disabled={isWorking} onClick={() => setConfirming("ban")}>
              Ban
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

function InviteRow({ invite, onRevoke }: { invite: InviteRecord; onRevoke?: () => void }) {
  const isPending = !invite.accepted_at && !invite.revoked_at && new Date(invite.expires_at) > new Date();
  const status = invite.accepted_at
    ? "accepted"
    : invite.revoked_at
    ? "revoked"
    : new Date(invite.expires_at) <= new Date()
    ? "expired"
    : "pending";

  return (
    <div className="flex items-center justify-between px-4 py-3 bg-background gap-4">
      <div className="min-w-0">
        <p className="text-sm font-medium truncate">{invite.email}</p>
        <p className="text-xs text-muted-foreground">
          {status} · expires {new Date(invite.expires_at).toLocaleDateString()}
        </p>
      </div>
      {isPending && onRevoke && (
        <Button size="sm" variant="outline" onClick={onRevoke}>
          Revoke
        </Button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stats tab
// ---------------------------------------------------------------------------

function StatsTab() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "stats"],
    queryFn: getAdminStats,
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (!data) return null;

  const userRows = [
    { label: "Total users", value: data.total_users },
    { label: "Active users (account not deactivated)", value: data.active_users },
    { label: "Active last 7 days", value: data.active_7d },
    { label: "Active last 30 days", value: data.active_30d },
    { label: "Active last 90 days", value: data.active_90d },
    { label: "Pending invites", value: data.pending_invites },
  ];

  const contentRows = [
    { label: "Projects", value: data.total_projects },
    { label: "Activities", value: data.total_activities },
    { label: "Looms", value: data.total_looms },
    { label: "Yarn entries", value: data.total_yarn },
  ];

  return (
    <div className="space-y-4">
      <StatTable title="Users" rows={userRows} />
      <StatTable title="Content" rows={contentRows} />
    </div>
  );
}

function StatTable({ title, rows }: { title: string; rows: { label: string; value: number }[] }) {
  return (
    <div>
      <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">{title}</h2>
      <div className="border rounded-lg divide-y overflow-hidden">
        {rows.map(({ label, value }) => (
          <div key={label} className="flex items-center justify-between px-4 py-3 bg-background">
            <span className="text-sm">{label}</span>
            <span className="text-sm font-medium tabular-nums">{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Health tab
// ---------------------------------------------------------------------------

const MAX_HEALTH_POINTS = 60;
const POLL_INTERVAL_MS = 3000;

function Sparkline({ values, max, color }: { values: number[]; max: number; color: string }) {
  const W = 300;
  const H = 48;
  if (values.length < 2) {
    return <svg width={W} height={H} className="opacity-20" />;
  }
  const effectiveMax = max > 0 ? max : 1;
  const points = values
    .map((v, i) => {
      const x = (i / (MAX_HEALTH_POINTS - 1)) * W;
      const y = H - Math.min(v / effectiveMax, 1) * (H - 2) - 1;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  // Area fill path: line + close down to baseline
  const x0 = (0 / (MAX_HEALTH_POINTS - 1)) * W;
  const xN = ((values.length - 1) / (MAX_HEALTH_POINTS - 1)) * W;
  const y0 = H - Math.min(values[0] / effectiveMax, 1) * (H - 2) - 1;
  const area = `M${x0.toFixed(1)},${y0.toFixed(1)} ${points} L${xN.toFixed(1)},${H} L${x0.toFixed(1)},${H} Z`;

  return (
    <svg width={W} height={H} className="shrink-0">
      <path d={area} fill={color} fillOpacity={0.1} />
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  );
}

function HealthTab() {
  const [history, setHistory] = useState<AdminHealth[]>([]);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const latest = history[history.length - 1] ?? null;

  useEffect(() => {
    const fetch = () => {
      getAdminHealth()
        .then((d) => setHistory((prev) => [...prev.slice(-(MAX_HEALTH_POINTS - 1)), d]))
        .catch(() => {});
    };
    fetch();
    pollingRef.current = setInterval(fetch, POLL_INTERVAL_MS);
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  if (!latest) return <p className="text-sm text-muted-foreground">Loading…</p>;

  const cpuValues = history.map((h) => h.cpu_percent);
  const memValues = history.map((h) => h.memory_percent);
  const pingValues = history.map((h) => h.db_ping_ms);
  const pingMax = Math.max(...pingValues, 50); // floor at 50ms so flat line doesn't look odd

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <span className="inline-block w-2 h-2 rounded-full bg-green-500 animate-pulse" />
        <span className="text-xs text-muted-foreground">
          Live · 3s interval · {history.length}/{MAX_HEALTH_POINTS} samples · {formatUptime(latest.uptime_seconds)} uptime
        </span>
      </div>

      <HealthChart
        label="CPU"
        current={`${latest.cpu_percent}%`}
        values={cpuValues}
        max={100}
        color="rgb(99,102,241)"
      />
      <HealthChart
        label="Memory"
        current={`${latest.memory_percent}% · ${latest.memory_used_mb} MB / ${latest.memory_total_mb} MB`}
        values={memValues}
        max={100}
        color="rgb(16,185,129)"
      />
      <HealthChart
        label="DB ping"
        current={`${latest.db_ping_ms} ms`}
        values={pingValues}
        max={pingMax}
        color="rgb(245,158,11)"
      />

      <VersionsTable />
    </div>
  );
}

function VersionsTable() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "versions"],
    queryFn: getAdminVersions,
    staleTime: Infinity,
  });

  if (isLoading || !data) return null;

  const rows = [
    { label: "App", value: data.app },
    { label: "Python", value: data.python },
    { label: "FastAPI", value: data.fastapi },
    { label: "SQLAlchemy", value: data.sqlalchemy },
    { label: "Alembic", value: data.alembic },
    { label: "PyWeaving", value: data.pyweaving },
    { label: "Pillow", value: data.pillow },
    { label: "boto3", value: data.boto3 },
    { label: "psutil", value: data.psutil },
  ];

  return (
    <div>
      <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Versions</h2>
      <div className="border rounded-lg divide-y overflow-hidden">
        {rows.map(({ label, value }) => (
          <div key={label} className="flex items-center justify-between px-4 py-2 bg-background">
            <span className="text-sm">{label}</span>
            <span className="text-xs font-mono text-muted-foreground">{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function HealthChart({
  label,
  current,
  values,
  max,
  color,
}: {
  label: string;
  current: string;
  values: number[];
  max: number;
  color: string;
}) {
  return (
    <div className="border rounded-lg p-4 space-y-2">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium">{label}</span>
        <span className="text-sm tabular-nums text-muted-foreground">{current}</span>
      </div>
      <div className="overflow-hidden">
        <Sparkline values={values} max={max} color={color} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// EULA tab
// ---------------------------------------------------------------------------

function EulaTab() {
  const qc = useQueryClient();
  const { data: current, isLoading } = useQuery({
    queryKey: ["admin", "eula"],
    queryFn: getAdminEula,
  });

  const [version, setVersion] = useState("");
  const [bodyHtml, setBodyHtml] = useState("");
  const [effectiveDate, setEffectiveDate] = useState("");
  const [showPreview, setShowPreview] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState(false);

  const { mutate: publish, isPending } = useMutation({
    mutationFn: () => createEulaVersion(version.trim(), bodyHtml.trim(), effectiveDate || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "eula"] });
      qc.invalidateQueries({ queryKey: ["eula", "current"] });
      setFormSuccess(true);
      setVersion("");
      setBodyHtml("");
      setEffectiveDate("");
      setFormError(null);
      setTimeout(() => setFormSuccess(false), 3000);
    },
    onError: (e: unknown) => {
      setFormError(e instanceof Error ? e.message : "Failed to publish EULA version");
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setFormSuccess(false);
    if (!version.trim()) { setFormError("Version is required"); return; }
    if (!bodyHtml.trim()) { setFormError("Body HTML is required"); return; }
    publish();
  }

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <div className="space-y-6">
      {/* Current version */}
      <div className="space-y-2">
        <h2 className="text-sm font-medium">Current version: {current?.version}</h2>
        <p className="text-xs text-muted-foreground">
          Effective {current ? new Date(current.effective_date).toLocaleDateString() : "—"}
          {" · "}Published {current ? new Date(current.created_at).toLocaleString() : "—"}
        </p>
        <button
          className="text-xs text-muted-foreground underline"
          onClick={() => setShowPreview(!showPreview)}
          type="button"
        >
          {showPreview ? "Hide" : "Preview"} current HTML
        </button>
        {showPreview && current && (
          <div className="rounded-lg border p-4 max-h-[40vh] overflow-y-auto">
            <EulaContent bodyHtml={current.body_html} />
          </div>
        )}
      </div>

      <hr />

      {/* Publish new version */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <h2 className="text-sm font-medium">Publish new version</h2>
        <p className="text-xs text-muted-foreground">
          Publishing a new version will require all users to re-accept on next login.
        </p>

        <div className="space-y-1">
          <label className="text-xs font-medium">Version string</label>
          <input
            className="w-full rounded border bg-background px-3 py-1.5 text-sm"
            placeholder="e.g. 0.4"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
          />
        </div>

        <div className="space-y-1">
          <label className="text-xs font-medium">Effective date (optional, defaults to now)</label>
          <input
            type="datetime-local"
            className="w-full rounded border bg-background px-3 py-1.5 text-sm"
            value={effectiveDate}
            onChange={(e) => setEffectiveDate(e.target.value)}
          />
        </div>

        <div className="space-y-1">
          <label className="text-xs font-medium">Body HTML</label>
          <textarea
            className="w-full rounded border bg-background px-3 py-1.5 text-sm font-mono min-h-[240px]"
            placeholder="<p>Paste full EULA HTML here…</p>"
            value={bodyHtml}
            onChange={(e) => setBodyHtml(e.target.value)}
          />
        </div>

        {formError && (
          <p className="text-sm text-destructive">{formError}</p>
        )}
        {formSuccess && (
          <p className="text-sm text-green-600">EULA version published.</p>
        )}

        <Button type="submit" disabled={isPending}>
          {isPending ? "Publishing…" : "Publish new version"}
        </Button>
      </form>
    </div>
  );
}
