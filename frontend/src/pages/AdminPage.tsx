import React, { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { UserDetailModal, type UserDetailTarget } from "@/components/admin/UserDetailModal";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";
import {
  listAdminUsers,
  getAdminStats,
  getAdminHealth,
  getAdminVersions,
  listInvites,
  createInvite,
  revokeInvite,
  listPendingSignups,
  approvePendingSignup,
  dismissPendingSignup,
  banPendingSignup,
  getAdminEula,
  createEulaVersion,
  getAdminServices,
  getAdminDbInfo,
  sendTestEmail,
  testWebhook,
  getAuditLog,
  getReconcileReport,
  backfillClerkUser,
  startS3AuditScan,
  getS3AuditTask,
  cleanupS3Orphans,
  startCveScan,
  getCveScanTask,
  getCveScanSummary,
  getWorkerStatus,
  startDebugSleep,
  getTaskHistory,
  revokeTask,
  runPurgeSoftDeleted,
  listScheduledTasks,
  patchScheduledTask,
  getServerEvents,
  listCredentials,
  createCredential,
  patchCredential,
  deleteCredential,
  type CredentialExpiry,
  type CredentialResource,
  type ScheduledTask,
  type TaskHistoryItem,
  type AdminUser,
  type AdminHealth,
  type AdminDbInfo,
  type AuditLogEntry,
  type InviteRecord,
  type PendingSignup,
  type ServiceCheck,
  type ServicePermCheck,
  type ReconcileReport,
  type WebhookProbeResult,
  type S3AuditResult,
  type CveScanResult,
  type CveFinding,
  type WorkerStatus,
  type WorkerInfo,
  type ServerEvent,
} from "@/api/admin";
import { getHealthDetailed, type ReadinessResponse, type ReadinessService } from "@/api/health";
import { EulaContent } from "@/components/EulaContent";
import { CopyEmail } from "@/components/admin/CopyEmail";
import { formatBytes } from "@/lib/image-utils";

type Tab = "users" | "invites" | "stats" | "health" | "services" | "deps" | "audit" | "credentials" | "superuser";

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
  const parts: string[] = [];
  if (d > 0) parts.push(`${d} day${d !== 1 ? "s" : ""}`);
  if (h > 0) parts.push(`${h} hour${h !== 1 ? "s" : ""}`);
  parts.push(`${m} minute${m !== 1 ? "s" : ""}`);
  return parts.join(", ");
}

function CveBanner() {
  const navigate = useNavigate();
  const [dismissed, setDismissed] = useState(false);
  const { data } = useQuery({
    queryKey: ["admin", "cve-summary"],
    queryFn: getCveScanSummary,
    staleTime: 5 * 60_000,
  });

  if (dismissed || !data || data.finding_count == null || data.finding_count === 0) return null;

  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm">
      <span className="text-amber-700 dark:text-amber-300 font-medium">
        {data.finding_count} CVE {data.finding_count === 1 ? "vulnerability" : "vulnerabilities"} found
        {data.scanned_at && (
          <span className="font-normal text-amber-600 dark:text-amber-400 ml-2">
            · last scanned {new Date(data.scanned_at).toLocaleString()}
          </span>
        )}
      </span>
      <div className="flex items-center gap-2 shrink-0">
        <button
          className="text-xs text-amber-700 dark:text-amber-300 underline hover:no-underline"
          onClick={() => navigate("/admin/superuser")}
        >
          View report
        </button>
        <button
          className="text-xs text-muted-foreground hover:text-foreground"
          onClick={() => setDismissed(true)}
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}

export function AdminPage() {
  const { section = "users" } = useParams<{ section: string }>();
  const { user: currentUser } = useAuth();
  const tab = section as Tab;

  return (
    <div className="p-6 max-w-4xl mx-auto w-full space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">Admin</h1>
        {currentUser?.is_superuser && (
          <span className="text-xs border rounded px-1.5 py-0.5 text-muted-foreground">superuser</span>
        )}
      </div>

      {currentUser?.is_superuser && <CveBanner />}

      {tab === "users" && <UsersTab />}
      {tab === "invites" && <InvitesTab />}
      {tab === "stats" && <StatsTab />}
      {tab === "health" && <HealthTab />}
      {tab === "services" && <ServicesTab />}
      {tab === "deps" && <DepsTab />}
      {tab === "audit" && <AuditLogTab />}
      {tab === "credentials" && <CredentialsTab />}
      {tab === "superuser" && <SuperuserTab />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Users tab — helpers
// ---------------------------------------------------------------------------

type SortKey =
  | "name" | "status" | "role" | "drafts" | "projects"
  | "looms" | "storage" | "last_login" | "joined";

interface UserRow {
  id: string;
  display_name: string;
  email: string;
  status: "active" | "inactive" | "banned" | "pending" | "errored" | "deleting";
  role: "superuser" | "admin" | "user";
  drafts: number;
  projects: number;
  looms: number;
  storage_bytes: number;
  last_active_at: string | null;
  created_at: string;
  _target: UserDetailTarget;
}

function deriveStatus(u: AdminUser): UserRow["status"] {
  if (u.deletion_state) return "deleting";
  if (u.clerk_errored) return "errored";
  if (u.clerk_banned) return "banned";
  if (!u.is_active) return "inactive";
  return "active";
}

function deriveRole(u: AdminUser): UserRow["role"] {
  if (u.is_superuser) return "superuser";
  if (u.is_admin) return "admin";
  return "user";
}

function formatShortDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

const STATUS_PILL: Record<UserRow["status"], string> = {
  active: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300",
  inactive: "bg-muted text-muted-foreground",
  banned: "bg-destructive/10 text-destructive",
  pending: "bg-copper-subtle text-copper-on-subtle",
  errored: "bg-destructive/10 text-destructive",
  deleting: "bg-copper-subtle text-copper-on-subtle",
};

function StatusPill({ status }: { status: UserRow["status"] }) {
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_PILL[status]}`}>
      {status}
    </span>
  );
}

function SortTh({
  label, k, sort, dir, onSort,
}: {
  label: string; k: SortKey; sort: SortKey; dir: "asc" | "desc"; onSort: (k: SortKey) => void;
}) {
  const active = sort === k;
  return (
    <th
      className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground cursor-pointer select-none hover:text-foreground whitespace-nowrap"
      onClick={() => onSort(k)}
    >
      {label}{active ? (dir === "asc" ? " ↑" : " ↓") : ""}
    </th>
  );
}

// ---------------------------------------------------------------------------
// Users tab
// ---------------------------------------------------------------------------

const f = "text-sm border rounded px-2 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-ring";

function UsersTab() {
  const { data: users = [], isLoading: usersLoading } = useQuery({
    queryKey: ["admin", "users"],
    queryFn: listAdminUsers,
  });
  const { data: pendingSignups = [], isLoading: pendingLoading } = useQuery({
    queryKey: ["admin", "pending-signups"],
    queryFn: listPendingSignups,
  });

  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<"all" | "admin" | "superuser" | "user">("all");
  const [statusFilter, setStatusFilter] = useState<
    "all" | "active" | "inactive" | "banned" | "pending" | "errored" | "deleting"
  >("all");
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [selected, setSelected] = useState<UserDetailTarget | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const rows: UserRow[] = [
    ...users.map((u) => ({
      id: u.id,
      display_name: u.display_name,
      email: u.email,
      status: deriveStatus(u),
      role: deriveRole(u),
      drafts: u.counts.drafts,
      projects: u.counts.projects_active + u.counts.projects_completed,
      looms: u.counts.looms,
      storage_bytes: u.counts.storage_bytes,
      last_active_at: u.last_active_at,
      created_at: u.created_at,
      _target: { kind: "user" as const, user: u },
    })),
    ...pendingSignups.map((p) => ({
      id: p.id,
      display_name: p.display_name || p.email,
      email: p.email,
      status: "pending" as const,
      role: "user" as const,
      drafts: 0,
      projects: 0,
      looms: 0,
      storage_bytes: 0,
      last_active_at: null,
      created_at: p.created_at,
      _target: { kind: "pending" as const, signup: p },
    })),
  ];

  const q = debouncedSearch.toLowerCase();
  const filtered = rows.filter((r) => {
    if (q && !r.display_name.toLowerCase().includes(q) && !r.email.toLowerCase().includes(q))
      return false;
    if (roleFilter !== "all" && r.role !== roleFilter) return false;
    if (statusFilter !== "all" && r.status !== statusFilter) return false;
    return true;
  });

  const ROLE_ORDER: Record<UserRow["role"], number> = { superuser: 0, admin: 1, user: 2 };
  const sorted = [...filtered].sort((a, b) => {
    let cmp = 0;
    switch (sortKey) {
      case "name": cmp = a.display_name.localeCompare(b.display_name); break;
      case "status": cmp = a.status.localeCompare(b.status); break;
      case "role": cmp = ROLE_ORDER[a.role] - ROLE_ORDER[b.role]; break;
      case "drafts": cmp = a.drafts - b.drafts; break;
      case "projects": cmp = a.projects - b.projects; break;
      case "looms": cmp = a.looms - b.looms; break;
      case "storage": cmp = a.storage_bytes - b.storage_bytes; break;
      case "last_login":
        cmp = (a.last_active_at ?? "").localeCompare(b.last_active_at ?? ""); break;
      case "joined": cmp = a.created_at.localeCompare(b.created_at); break;
    }
    return sortDir === "asc" ? cmp : -cmp;
  });

  const handleSort = (k: SortKey) => {
    if (sortKey === k) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir("asc"); }
  };

  if (usersLoading || pendingLoading)
    return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <div className="space-y-3">
      {/* Filter bar */}
      <div className="flex flex-wrap gap-2">
        <input
          type="search"
          placeholder="Search name or email…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className={`flex-1 min-w-40 ${f}`}
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
          className={f}
        >
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
          <option value="banned">Banned</option>
          <option value="pending">Pending</option>
          <option value="errored">Errored</option>
          <option value="deleting">Deleting</option>
        </select>
        <select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value as typeof roleFilter)}
          className={f}
        >
          <option value="all">All roles</option>
          <option value="superuser">Superuser</option>
          <option value="admin">Admin</option>
          <option value="user">User</option>
        </select>
      </div>

      <p className="text-xs text-muted-foreground">
        {sorted.length === rows.length
          ? `${rows.length} user${rows.length !== 1 ? "s" : ""}`
          : `${sorted.length} of ${rows.length} users`}
      </p>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm min-w-[700px]">
          <thead>
            <tr className="border-b bg-muted/40">
              <SortTh label="Name" k="name" sort={sortKey} dir={sortDir} onSort={handleSort} />
              <SortTh label="Status" k="status" sort={sortKey} dir={sortDir} onSort={handleSort} />
              <SortTh label="Role" k="role" sort={sortKey} dir={sortDir} onSort={handleSort} />
              <SortTh label="Drafts" k="drafts" sort={sortKey} dir={sortDir} onSort={handleSort} />
              <SortTh label="Projects" k="projects" sort={sortKey} dir={sortDir} onSort={handleSort} />
              <SortTh label="Looms" k="looms" sort={sortKey} dir={sortDir} onSort={handleSort} />
              <SortTh label="Storage" k="storage" sort={sortKey} dir={sortDir} onSort={handleSort} />
              <SortTh label="Last login" k="last_login" sort={sortKey} dir={sortDir} onSort={handleSort} />
              <SortTh label="Joined" k="joined" sort={sortKey} dir={sortDir} onSort={handleSort} />
            </tr>
          </thead>
          <tbody className="divide-y">
            {sorted.map((row) => (
              <tr
                key={row.id}
                className="cursor-pointer hover:bg-muted/30"
                onClick={() => setSelected(row._target)}
              >
                <td className="px-3 py-2.5 min-w-[160px]">
                  <p className="max-w-[180px] truncate font-medium leading-tight">
                    {row.display_name}
                  </p>
                  <p className="max-w-[180px] overflow-hidden text-xs text-muted-foreground">
                    <CopyEmail email={row.email} />
                  </p>
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  <StatusPill status={row.status} />
                </td>
                <td className="px-3 py-2.5 capitalize text-muted-foreground whitespace-nowrap">
                  {row.role}
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums">
                  {row.drafts || "—"}
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums">
                  {row.projects || "—"}
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums">
                  {row.looms || "—"}
                </td>
                <td className="px-3 py-2.5 text-right text-xs tabular-nums">
                  {row.storage_bytes ? formatBytes(row.storage_bytes) : "—"}
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap text-xs text-muted-foreground">
                  {formatLastActive(row.last_active_at)}
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap text-xs text-muted-foreground">
                  {formatShortDate(row.created_at)}
                </td>
              </tr>
            ))}
            {sorted.length === 0 && (
              <tr>
                <td
                  colSpan={9}
                  className="px-3 py-8 text-center text-sm text-muted-foreground"
                >
                  No users match the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {selected && (
        <UserDetailModal target={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Invites tab
// ---------------------------------------------------------------------------

const INVITE_HISTORY_PAGE_SIZE = 20;

function InvitesTab() {
  const qc = useQueryClient();
  const { user: currentUser } = useAuth();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"user" | "admin">("user");
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
    mutationFn: () => createInvite(email, role),
    onSuccess: () => {
      setSent(email);
      setEmail("");
      setRole("user");
      setError(null);
      qc.invalidateQueries({ queryKey: ["admin", "invites"] });
    },
    onError: (err: Error) => {
      try {
        const parsed = JSON.parse(err.message);
        if (parsed?.detail?.reason === "pending_signup_exists") {
          setError("This email already has a pending signup request. Use the Approve button in the list above.");
          return;
        }
        setError(parsed?.detail?.message ?? parsed?.detail ?? err.message);
      } catch {
        setError(err.message);
      }
    },
  });

  const removePending = (id: string) =>
    qc.setQueryData(["admin", "pending-signups"], (old: PendingSignup[] | undefined) =>
      old ? old.filter((p) => p.id !== id) : []
    );

  const approve = useMutation({
    mutationFn: (id: string) => approvePendingSignup(id),
    onSuccess: (_, id) => {
      removePending(id);
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
      qc.invalidateQueries({ queryKey: ["admin", "invites"] });
    },
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
            These users signed up through Clerk but have no invite. Approve them or dismiss.
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
            onKeyDown={(e) => e.key === "Enter" && email && send.mutate()}
            className="flex-1 text-sm border rounded px-3 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-ring"
          />
          {currentUser?.is_superuser && (
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as "user" | "admin")}
              className="text-sm border rounded px-2 py-1.5 bg-background focus:outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="user">User</option>
              <option value="admin">Admin</option>
            </select>
          )}
          <Button size="sm" disabled={!email || send.isPending} onClick={() => send.mutate()}>
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
        <p className="text-xs text-muted-foreground overflow-hidden"><CopyEmail email={signup.email} /></p>
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
            <Button size="sm" disabled={isWorking} onClick={onApprove} className="bg-green-600 hover:bg-green-700 text-white">
              Approve
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
        <p className="text-sm font-medium overflow-hidden"><CopyEmail email={invite.email} /></p>
        <p className="text-xs text-muted-foreground">
          {invite.role} · {status} · expires {new Date(invite.expires_at).toLocaleDateString()}
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
    { label: "Drafts", value: data.total_drafts },
    { label: "Projects", value: data.total_projects },
    { label: "Looms", value: data.total_looms },
    { label: "Yarn entries", value: data.total_yarn },
    { label: "Total storage (photos)", value: formatBytes(data.total_storage_bytes) },
  ];

  return (
    <div className="space-y-4">
      <StatTable title="Users" rows={userRows} />
      <StatTable title="Content" rows={contentRows} />
    </div>
  );
}

function StatTable({ title, rows }: { title: string; rows: { label: string; value: number | string }[] }) {
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
          Live · 3s interval · {history.length}/{MAX_HEALTH_POINTS} samples
        </span>
      </div>

      <div className="border rounded-lg p-4 space-y-1">
        <div className="flex items-baseline justify-between">
          <span className="text-sm font-medium">Uptime</span>
          <span className="text-sm tabular-nums text-muted-foreground">{formatUptime(latest.uptime_seconds)}</span>
        </div>
        <div className="flex items-baseline justify-between">
          <span className="text-xs text-muted-foreground">Last reboot</span>
          <span className="text-xs font-mono text-muted-foreground">
            {new Date(latest.started_at).toLocaleString()}
          </span>
        </div>
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

    </div>
  );
}

declare const __APP_VERSION__: string;

function InfoTable({ rows }: { rows: { label: string; value: string }[] }) {
  return (
    <div className="border rounded-lg divide-y overflow-hidden">
      {rows.map(({ label, value }) => (
        <div key={label} className="flex items-center justify-between px-4 py-2 bg-background">
          <span className="text-sm">{label}</span>
          <span className="text-xs font-mono text-muted-foreground">{value}</span>
        </div>
      ))}
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

  const versions = [
    { label: "Frontend", value: __APP_VERSION__ },
    { label: "API", value: data.app },
    { label: "Worker", value: data.worker ?? "not reported" },
    { label: "PostgreSQL", value: `${data.postgres} · ${data.postgres_source}` },
    { label: "Redis", value: data.redis_server },
    { label: "Celery", value: data.celery },
    { label: "Python", value: data.python },
  ];

  const backendRows = Object.entries(data.backend_packages).map(([k, v]) => ({ label: k, value: v }));
  const frontendRows = Object.entries(__FRONTEND_DEPS__).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => ({ label: k, value: v }));
  const devRows = Object.entries(__FRONTEND_DEV_DEPS__).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => ({ label: k, value: v }));

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Runtime</h2>
        <InfoTable rows={versions} />
      </div>
      <div>
        <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Backend packages</h2>
        <div className="rounded-md border overflow-auto max-h-72">
          <table className="w-full text-xs">
            <tbody>
              {backendRows.map(({ label, value }) => (
                <tr key={label} className="border-t first:border-t-0">
                  <td className="px-3 py-1.5 font-mono text-muted-foreground w-1/2">{label}</td>
                  <td className="px-3 py-1.5 tabular-nums">{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div>
        <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Frontend dependencies</h2>
        <div className="rounded-md border overflow-auto max-h-72">
          <table className="w-full text-xs">
            <tbody>
              {frontendRows.map(({ label, value }) => (
                <tr key={label} className="border-t first:border-t-0">
                  <td className="px-3 py-1.5 font-mono text-muted-foreground w-1/2">{label}</td>
                  <td className="px-3 py-1.5 tabular-nums">{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <details className="text-xs">
        <summary className="cursor-pointer text-muted-foreground hover:text-foreground py-1">Dev dependencies ({devRows.length})</summary>
        <div className="rounded-md border overflow-auto max-h-60 mt-2">
          <table className="w-full text-xs">
            <tbody>
              {devRows.map(({ label, value }) => (
                <tr key={label} className="border-t first:border-t-0">
                  <td className="px-3 py-1.5 font-mono text-muted-foreground w-1/2">{label}</td>
                  <td className="px-3 py-1.5 tabular-nums">{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

function DepsTab() {
  return (
    <div className="space-y-4">
      <VersionsTable />
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
// Services tab
// ---------------------------------------------------------------------------

function StatusDot({ status, small }: { status: "ok" | "error"; small?: boolean }) {
  return (
    <span
      className={`inline-block rounded-full shrink-0 ${small ? "w-2 h-2" : "w-2.5 h-2.5"} ${
        status === "ok" ? "bg-green-500" : "bg-red-500"
      }`}
    />
  );
}

function CombinedServiceRow({ service, detail }: { service: ReadinessService; detail?: ServiceCheck }) {
  const [open, setOpen] = useState(false);
  const [webhookResult, setWebhookResult] = useState<WebhookProbeResult | null>(null);
  const [webhookTesting, setWebhookTesting] = useState(false);
  const [emailResult, setEmailResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [emailSending, setEmailSending] = useState(false);
  const isWebhook = service.name === "Clerk Webhook";
  const isSmtp = service.name === "SMTP";
  const metaEntries = Object.entries(detail?.meta ?? {});
  const hasDetail = detail && (metaEntries.length > 0 || detail.checks.length > 0);

  async function handleTestWebhook(e: React.MouseEvent) {
    e.stopPropagation();
    setWebhookTesting(true);
    setWebhookResult(null);
    try {
      const result = await testWebhook();
      setWebhookResult(result);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Request failed";
      setWebhookResult({ status: "error", latency_ms: null, message: msg });
    } finally {
      setWebhookTesting(false);
    }
  }

  async function handleTestEmail(e: React.MouseEvent) {
    e.stopPropagation();
    setEmailSending(true);
    setEmailResult(null);
    try {
      const result = await sendTestEmail();
      setEmailResult({ ok: true, msg: `Sent to ${result.to}` });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Request failed";
      setEmailResult({ ok: false, msg });
    } finally {
      setEmailSending(false);
    }
  }

  return (
    <div className="bg-background">
      <button
        className={`w-full flex items-center gap-3 px-4 py-3 text-left ${hasDetail ? "hover:bg-muted/40 cursor-pointer" : "cursor-default"}`}
        onClick={hasDetail ? () => setOpen((o) => !o) : undefined}
      >
        <StatusDot status={service.ok ? "ok" : "error"} />
        <span className="text-sm font-medium w-32 shrink-0">{service.name}</span>
        <span className={`text-sm flex-1 ${!service.ok ? "text-destructive" : "text-muted-foreground"}`}>
          {service.message || (service.ok ? "ok" : "failed")}
        </span>
        {isWebhook && (
          <Button
            size="sm"
            variant="outline"
            className="h-6 px-2 text-xs"
            disabled={webhookTesting}
            onClick={handleTestWebhook}
          >
            {webhookTesting ? "Testing…" : "Test"}
          </Button>
        )}
        {isSmtp && (
          <Button
            size="sm"
            variant="outline"
            className="h-6 px-2 text-xs"
            disabled={emailSending}
            onClick={handleTestEmail}
          >
            {emailSending ? "Sending…" : "Send Test"}
          </Button>
        )}
        {!service.critical && <span className="text-xs text-muted-foreground">non-critical</span>}
        {hasDetail && <span className="text-xs text-muted-foreground">{open ? "▲" : "▼"}</span>}
      </button>
      {webhookResult && (
        <div className={`px-4 py-2 border-t text-xs font-mono ${webhookResult.status === "ok" ? "text-green-600" : "text-destructive"}`}>
          {webhookResult.status === "ok"
            ? `✓ Round-trip: ${webhookResult.latency_ms}ms`
            : `✗ ${webhookResult.message}`}
        </div>
      )}
      {emailResult && (
        <div className={`px-4 py-2 border-t text-xs ${emailResult.ok ? "text-green-600" : "text-destructive"}`}>
          {emailResult.ok ? `✓ ${emailResult.msg}` : `✗ ${emailResult.msg}`}
        </div>
      )}
      {open && hasDetail && (
        <div className="border-t">
          {metaEntries.length > 0 && (
            <div className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 pl-10 pr-4 py-2.5 bg-muted/10 border-b">
              {metaEntries.map(([k, v]) => (
                <React.Fragment key={k}>
                  <span className="text-xs text-muted-foreground">{k}</span>
                  <span className="text-xs font-mono break-all">{v}</span>
                </React.Fragment>
              ))}
            </div>
          )}
          {detail!.checks.length > 0 && (
            <div className="divide-y">
              {detail!.checks.map((c: ServicePermCheck) => (
                <div key={c.name} className="flex items-center gap-3 pl-10 pr-4 py-2 bg-muted/20">
                  <StatusDot status={c.status} small />
                  <span className="text-xs text-muted-foreground w-32 shrink-0">{c.name}</span>
                  <span className={`text-xs ${c.status === "error" ? "text-destructive" : "text-muted-foreground"}`}>
                    {c.message}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DbInfoPanel() {
  const { data } = useQuery<AdminDbInfo>({
    queryKey: ["admin", "db-info"],
    queryFn: getAdminDbInfo,
    staleTime: 60_000,
  });

  if (!data) return null;

  const rows = [
    { label: "Revision", value: data.revision ?? "unknown" },
    { label: "At head", value: data.is_at_head ? "yes" : "no", warn: !data.is_at_head },
    { label: "Last squash", value: data.last_squash_at ?? "—" },
    {
      label: "Last migrated",
      value: data.last_migrated_at ? new Date(data.last_migrated_at).toLocaleString() : "—",
    },
  ];

  return (
    <div>
      <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Database</h2>
      <div className="border rounded-lg divide-y overflow-hidden">
        {rows.map(({ label, value, warn }) => (
          <div key={label} className="flex items-center justify-between px-4 py-2 bg-background">
            <span className="text-sm">{label}</span>
            <span className={`text-xs font-mono ${warn ? "text-destructive font-semibold" : "text-muted-foreground"}`}>
              {value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ServicesTab() {
  // Live status from /health/detailed — auto-refreshes every 30s
  const [detailed, setDetailed] = useState<ReadinessResponse | null>(null);
  const [detailedAt, setDetailedAt] = useState<Date | null>(null);

  useEffect(() => {
    const poll = () =>
      getHealthDetailed()
        .then((d) => { setDetailed(d); setDetailedAt(new Date()); })
        .catch(() => {});
    poll();
    const id = setInterval(poll, 30_000);
    return () => clearInterval(id);
  }, []);

  // Detailed diagnostics — runs on mount, re-runnable via button
  const { data: diagnostics, isFetching: diagFetching, refetch: runDiag, dataUpdatedAt: diagAt } = useQuery({
    queryKey: ["admin", "services"],
    queryFn: getAdminServices,
    staleTime: Infinity,
    enabled: true,
  });

  const diagTime = diagAt ? new Date(diagAt).toLocaleTimeString() : null;
  const getDetail = (name: string) => diagnostics?.find((d) => d.service === name);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <span className="text-xs text-muted-foreground">
            {detailedAt
              ? `Updated ${detailedAt.toLocaleTimeString()} · auto-refreshes every 30s`
              : "Loading…"}
          </span>
        </div>
        <Button size="sm" variant="outline" disabled={diagFetching} onClick={() => runDiag()}>
          {diagFetching ? "Running…" : diagTime ? `Re-run · ${diagTime}` : "Running…"}
        </Button>
      </div>

      {!detailed || detailed.status === "starting" ? (
        <p className="text-sm text-muted-foreground">Checking services…</p>
      ) : (
        <div className="border rounded-lg divide-y overflow-hidden">
          {detailed.services.map((svc) => (
            <CombinedServiceRow key={svc.name} service={svc} detail={getDetail(svc.name)} />
          ))}
        </div>
      )}

      <DbInfoPanel />
      <ServerEventsPanel />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Server events panel (inside ServicesTab)
// ---------------------------------------------------------------------------

const SERVER_EVENT_TYPES = [
  "stack.startup",
  "stack.shutdown",
  "health.degraded",
  "health.error",
  "health.check",
];

function severityBadge(severity: ServerEvent["severity"]) {
  if (severity === "error") return <span className="px-1.5 py-0.5 rounded text-xs bg-destructive/15 text-destructive font-medium">error</span>;
  if (severity === "warn") return <span className="px-1.5 py-0.5 rounded text-xs bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300 font-medium">warn</span>;
  return <span className="px-1.5 py-0.5 rounded text-xs bg-muted text-muted-foreground font-medium">info</span>;
}

function formatElapsed(ms: number | null) {
  if (ms === null) return "—";
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return `${m}m ${rem}s`;
}

function ServerEventsPanel() {
  const [page, setPage] = useState(1);
  const [eventType, setEventType] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["server-events", page, eventType],
    queryFn: () => getServerEvents({ page, page_size: 25, event_type: eventType || undefined }),
    refetchInterval: 60_000,
  });

  return (
    <div className="space-y-3 pt-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Server Events Log</h3>
        <div className="flex items-center gap-2">
          <select
            value={eventType}
            onChange={(e) => { setEventType(e.target.value); setPage(1); }}
            className="text-xs border rounded px-2 py-1 bg-background"
          >
            <option value="">All types</option>
            {SERVER_EVENT_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          {data && (
            <span className="text-xs text-muted-foreground">
              {data.total.toLocaleString()} event{data.total !== 1 ? "s" : ""}
            </span>
          )}
        </div>
      </div>

      {isLoading && <p className="text-xs text-muted-foreground">Loading…</p>}
      {isError && <p className="text-xs text-destructive">Failed to load server events.</p>}

      {data && data.items.length === 0 && (
        <p className="text-xs text-muted-foreground">No events recorded yet.</p>
      )}

      {data && data.items.length > 0 && (
        <div className="rounded-lg border overflow-hidden overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="text-left px-3 py-2">Time</th>
                <th className="text-left px-3 py-2">Type</th>
                <th className="text-left px-3 py-2">Severity</th>
                <th className="text-left px-3 py-2">Status</th>
                <th className="text-left px-3 py-2">Elapsed</th>
                <th className="text-left px-3 py-2">Version</th>
                <th className="text-left px-3 py-2">Message</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {data.items.map((evt) => (
                <tr key={evt.id} className="hover:bg-muted/30">
                  <td className="px-3 py-2 whitespace-nowrap text-muted-foreground font-mono">
                    {new Date(evt.started_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2 font-mono">{evt.event_type}</td>
                  <td className="px-3 py-2">{severityBadge(evt.severity)}</td>
                  <td className="px-3 py-2 text-muted-foreground">{evt.status}</td>
                  <td className="px-3 py-2 font-mono whitespace-nowrap">{formatElapsed(evt.elapsed_ms)}</td>
                  <td className="px-3 py-2 font-mono text-muted-foreground">{evt.app_version}</td>
                  <td className="px-3 py-2 text-muted-foreground max-w-xs truncate">{evt.message ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.pages > 1 && (
        <div className="flex items-center gap-2 justify-center text-xs">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="px-2 py-1 border rounded disabled:opacity-40"
          >
            ←
          </button>
          <span className="text-muted-foreground">Page {data.page} of {data.pages}</span>
          <button
            disabled={page >= data.pages}
            onClick={() => setPage((p) => p + 1)}
            className="px-2 py-1 border rounded disabled:opacity-40"
          >
            →
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// EULA tab
// ---------------------------------------------------------------------------

type LintIssue = { level: "error" | "warning"; message: string };
type LintResult = { ok: boolean; issues: LintIssue[] };

function lintHtml(html: string): LintResult {
  const issues: LintIssue[] = [];
  if (!html.trim()) return { ok: false, issues: [{ level: "error", message: "HTML is empty" }] };

  const doc = new DOMParser().parseFromString(html, "text/html");

  // Parser error nodes (browsers inject these for severely malformed markup)
  if (doc.querySelector("parseerror")) {
    issues.push({ level: "error", message: "HTML parse error — check for malformed tags" });
  }

  // Disallowed elements
  for (const tag of ["script", "iframe", "object", "embed", "form"]) {
    if (doc.body.querySelector(tag)) {
      issues.push({ level: "error", message: `Disallowed element: <${tag}>` });
    }
  }

  // Inline event handlers
  for (const el of doc.body.querySelectorAll("*")) {
    for (const attr of el.attributes) {
      if (attr.name.startsWith("on")) {
        issues.push({ level: "error", message: `Inline event handler: ${attr.name} on <${el.tagName.toLowerCase()}>` });
        break;
      }
    }
  }

  // javascript: hrefs
  for (const a of doc.body.querySelectorAll("a[href]")) {
    if ((a.getAttribute("href") ?? "").toLowerCase().startsWith("javascript:")) {
      issues.push({ level: "error", message: "javascript: URL in <a> href" });
    }
  }

  // Inline <style> blocks (warning only)
  if (doc.body.querySelector("style")) {
    issues.push({ level: "warning", message: "<style> tag found — may affect page layout" });
  }

  return { ok: issues.every((i) => i.level !== "error"), issues };
}

function EulaTab() {
  const qc = useQueryClient();
  const { data: current, isLoading } = useQuery({
    queryKey: ["admin", "eula"],
    queryFn: getAdminEula,
  });

  const currentVersion = current?.version ?? null;
  const nextVersion = React.useMemo(() => {
    if (!currentVersion) return "";
    const [major, minor] = currentVersion.split(".").map(Number);
    return `${major}.${(minor ?? 0) + 1}`;
  }, [currentVersion]);
  const [versionOverride, setVersionOverride] = useState<string | null>(null);
  const version = versionOverride ?? nextVersion;
  const setVersion = setVersionOverride;
  const [bodyHtml, setBodyHtml] = useState("");
  const [effectiveDate, setEffectiveDate] = useState(
    () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16)
  );
  const [showCurrent, setShowCurrent] = useState(false);
  const [lintResult, setLintResult] = useState<LintResult | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState(false);

  const versionValid = /^\d+\.\d+$/.test(version.trim());

  function handleBodyHtmlChange(val: string) {
    setBodyHtml(val);
    setLintResult(null); // reset lint when content changes
  }

  const { mutate: publish, isPending } = useMutation({
    mutationFn: () => createEulaVersion(
      version.trim(),
      bodyHtml.trim(),
      effectiveDate ? new Date(effectiveDate).toISOString() : undefined,
    ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "eula"] });
      qc.invalidateQueries({ queryKey: ["eula", "current"] });
      setFormSuccess(true);
      setVersionOverride(null);
      setBodyHtml("");
      setEffectiveDate(new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16));
      setLintResult(null);
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
    if (!versionValid) { setFormError("Version must be in x.y format (e.g. 0.4)"); return; }
    if (!bodyHtml.trim()) { setFormError("Body HTML is required"); return; }
    if (!lintResult?.ok) { setFormError("HTML must pass lint before publishing"); return; }
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
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" type="button" onClick={() => setShowCurrent((v) => !v)}>
            {showCurrent ? "Hide" : "View"} current EULA
          </Button>
        </div>
        {showCurrent && current && (
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
            className={`w-full rounded border bg-background px-3 py-1.5 text-sm ${version && !versionValid ? "border-destructive" : ""}`}
            placeholder="e.g. 0.4"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
          />
          {version && !versionValid && (
            <p className="text-xs text-destructive">Must be x.y format (e.g. 0.4)</p>
          )}
        </div>

        <div className="space-y-1">
          <label className="text-xs font-medium">Effective date</label>
          <input
            type="datetime-local"
            className="w-full rounded border bg-background px-3 py-1.5 text-sm"
            value={effectiveDate}
            onChange={(e) => setEffectiveDate(e.target.value)}
          />
        </div>

        <div className="space-y-1">
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium">Body HTML</label>
            {current && (
              <Button variant="outline" size="sm" type="button" onClick={() => {
                const html = current.body_html.replace(/Version \d+\.\d+/, `Version ${version}`);
                setBodyHtml(html);
                setLintResult(null);
              }}>
                Copy to editor
              </Button>
            )}
          </div>
          <textarea
            className="w-full rounded border bg-background px-3 py-1.5 text-sm font-mono min-h-[240px]"
            placeholder="<p>Paste full EULA HTML here…</p>"
            value={bodyHtml}
            onChange={(e) => handleBodyHtmlChange(e.target.value)}
          />
        </div>

        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!bodyHtml.trim()}
          onClick={() => setLintResult(lintHtml(bodyHtml))}
        >
          Lint &amp; preview
        </Button>

        {/* Lint results */}
        {lintResult && (
          <div className={`rounded-lg border p-3 space-y-1 ${lintResult.ok ? "border-green-500/40 bg-green-500/5" : "border-destructive/40 bg-destructive/5"}`}>
            {lintResult.issues.length === 0 ? (
              <p className="text-xs text-green-600 font-medium">✓ No issues found</p>
            ) : (
              lintResult.issues.map((issue, i) => (
                <p key={i} className={`text-xs ${issue.level === "error" ? "text-destructive" : "text-yellow-600"}`}>
                  {issue.level === "error" ? "✗" : "⚠"} {issue.message}
                </p>
              ))
            )}
            {lintResult.ok && (
              <p className="text-xs text-green-600 font-medium">✓ Lint passed — HTML is safe to publish</p>
            )}
          </div>
        )}

        {/* New EULA preview */}
        {lintResult?.ok && bodyHtml.trim() && (
          <div className="space-y-1">
            <p className="text-xs font-medium">Preview</p>
            <div className="rounded-lg border p-4 max-h-[40vh] overflow-y-auto">
              <EulaContent bodyHtml={bodyHtml} />
            </div>
          </div>
        )}

        {formError && (
          <p className="text-sm text-destructive">{formError}</p>
        )}
        {formSuccess && (
          <p className="text-sm text-green-600">EULA version published.</p>
        )}

        {lintResult?.ok && (
          <Button type="submit" disabled={isPending}>
            {isPending ? "Publishing…" : "Publish new version"}
          </Button>
        )}
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Credentials tab
// ---------------------------------------------------------------------------

const RESOURCE_LABELS: Record<CredentialResource, string> = {
  smtp: "SMTP",
  s3: "S3 / R2",
  clerk: "Clerk",
  postgres: "PostgreSQL",
  app: "App Secret",
};

const RESOURCE_OPTIONS: CredentialResource[] = ["smtp", "s3", "clerk", "postgres", "app"];

function credentialStatus(daysRemaining: number | null): { label: string; cls: string } {
  if (daysRemaining === null) return { label: "No expiry", cls: "bg-muted text-muted-foreground" };
  if (daysRemaining < 0) return { label: "Expired", cls: "bg-destructive/10 text-destructive" };
  if (daysRemaining <= 7) return { label: "Critical", cls: "bg-destructive/10 text-destructive" };
  if (daysRemaining <= 30) return { label: "Warning", cls: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300" };
  return { label: "OK", cls: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300" };
}

function CredentialsTab() {
  const { user: currentUser } = useAuth();
  const queryClient = useQueryClient();
  const isSuperuser = currentUser?.is_superuser ?? false;

  const { data: credentials = [], isLoading } = useQuery({
    queryKey: ["admin", "credentials"],
    queryFn: listCredentials,
  });

  const [editing, setEditing] = useState<CredentialExpiry | null>(null);
  const [adding, setAdding] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<CredentialExpiry | null>(null);
  const [formName, setFormName] = useState("");
  const [formResource, setFormResource] = useState<CredentialResource>("smtp");
  const [formExpiry, setFormExpiry] = useState("");
  const [formNotes, setFormNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function openAdd() {
    setFormName(""); setFormResource("smtp"); setFormExpiry(""); setFormNotes("");
    setError(null); setAdding(true);
  }

  function openEdit(c: CredentialExpiry) {
    setFormName(c.name);
    setFormResource(c.resource);
    setFormExpiry(c.expires_on ?? "");
    setFormNotes(c.notes ?? "");
    setError(null);
    setEditing(c);
  }

  function closeForm() { setAdding(false); setEditing(null); setError(null); }

  async function handleSave() {
    if (!formName.trim()) { setError("Name is required"); return; }
    setSaving(true); setError(null);
    try {
      const body = {
        name: formName.trim(),
        resource: formResource,
        expires_on: formExpiry || null,
        notes: formNotes.trim() || null,
      };
      if (adding) {
        await createCredential(body);
      } else if (editing) {
        await patchCredential(editing.id, body);
      }
      queryClient.invalidateQueries({ queryKey: ["admin", "credentials"] });
      closeForm();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteCredential(deleteTarget.id);
      queryClient.invalidateQueries({ queryKey: ["admin", "credentials"] });
      setDeleteTarget(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete");
    } finally {
      setDeleting(false);
    }
  }

  const sorted = [...credentials].sort((a, b) => {
    if (a.days_remaining === null && b.days_remaining === null) return 0;
    if (a.days_remaining === null) return 1;
    if (b.days_remaining === null) return -1;
    return a.days_remaining - b.days_remaining;
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold">Managed credentials</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Track expiration dates for secrets and service credentials.</p>
        </div>
        {isSuperuser && (
          <Button size="sm" onClick={openAdd}>Add credential</Button>
        )}
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : sorted.length === 0 ? (
        <p className="text-sm text-muted-foreground">No credentials tracked yet.</p>
      ) : (
        <div className="rounded-md border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">Name</th>
                <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">Service</th>
                <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">Expires</th>
                <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">Status</th>
                {isSuperuser && <th className="px-3 py-2" />}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {sorted.map((c) => {
                const { label, cls } = credentialStatus(c.days_remaining);
                return (
                  <tr key={c.id} className="hover:bg-muted/50">
                    <td className="px-3 py-2.5 font-medium">{c.name}</td>
                    <td className="px-3 py-2.5 text-muted-foreground">{RESOURCE_LABELS[c.resource]}</td>
                    <td className="px-3 py-2.5 text-muted-foreground">
                      {c.expires_on
                        ? <>
                            {new Date(c.expires_on).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}
                            {c.days_remaining !== null && (
                              <span className="ml-1.5 text-xs text-muted-foreground">
                                ({c.days_remaining < 0 ? `${Math.abs(c.days_remaining)}d ago` : `${c.days_remaining}d`})
                              </span>
                            )}
                          </>
                        : <span className="text-muted-foreground">Never</span>}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${cls}`}>{label}</span>
                    </td>
                    {isSuperuser && (
                      <td className="px-3 py-2.5 text-right">
                        <button className="text-xs text-muted-foreground hover:text-foreground mr-3" onClick={() => openEdit(c)}>Edit</button>
                        <button className="text-xs text-destructive hover:text-destructive/80" onClick={() => setDeleteTarget(c)}>Delete</button>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {(adding || editing) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-lg border bg-background shadow-lg p-6 space-y-4">
            <h3 className="font-semibold">{adding ? "Add credential" : "Edit credential"}</h3>
            <div>
              <label className="mb-1 block text-sm font-medium">Name <span className="text-destructive">*</span></label>
              <input className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring" value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="Clerk Secret Key" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Service</label>
              <select className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring" value={formResource} onChange={(e) => setFormResource(e.target.value as CredentialResource)}>
                {RESOURCE_OPTIONS.map((r) => <option key={r} value={r}>{RESOURCE_LABELS[r]}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Expiration date <span className="text-muted-foreground font-normal">(optional)</span></label>
              <input type="date" className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring" value={formExpiry} onChange={(e) => setFormExpiry(e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Notes <span className="text-muted-foreground font-normal">(optional)</span></label>
              <textarea className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring" rows={2} value={formNotes} onChange={(e) => setFormNotes(e.target.value)} placeholder="Rotation instructions, link to vault, etc." />
            </div>
            {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
            <div className="flex justify-end gap-2 pt-1">
              <Button type="button" variant="outline" onClick={closeForm} disabled={saving}>Cancel</Button>
              <Button onClick={handleSave} disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
            </div>
          </div>
        </div>
      )}

      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-lg border bg-background shadow-lg p-6 space-y-4">
            <h3 className="font-semibold">Delete credential?</h3>
            <p className="text-sm text-muted-foreground">This will permanently remove <strong>{deleteTarget.name}</strong> from the tracking list.</p>
            {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setDeleteTarget(null)} disabled={deleting}>Cancel</Button>
              <Button variant="destructive" onClick={handleDelete} disabled={deleting}>{deleting ? "Deleting…" : "Delete"}</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Superuser tab
// ---------------------------------------------------------------------------

type SuperuserSubTab = "eula" | "storage" | "cve" | "workers" | "deletion" | "reconcile" | "maintenance" | "schedule";

const SUPERUSER_TAB_LABELS: Record<SuperuserSubTab, string> = {
  eula: "EULA",
  storage: "Storage",
  cve: "CVE Scan",
  workers: "Workers",
  deletion: "Deletion",
  reconcile: "Reconcile",
  maintenance: "Maintenance",
  schedule: "Scheduled Tasks",
};

function SuperuserTab() {
  const [sub, setSub] = useState<SuperuserSubTab>("eula");

  return (
    <div className="space-y-4">
      <div className="flex gap-2 border-b pb-2 flex-wrap">
        {(["eula", "storage", "cve", "workers", "deletion", "reconcile", "maintenance", "schedule"] as SuperuserSubTab[]).map((t) => (
          <button
            key={t}
            onClick={() => setSub(t)}
            className={`px-3 py-1.5 text-sm rounded ${
              sub === t
                ? "bg-foreground text-background"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {SUPERUSER_TAB_LABELS[t]}
          </button>
        ))}
      </div>

      {sub === "eula" && <EulaTab />}
      {sub === "storage" && <StorageAuditTab />}
      {sub === "cve" && <CveScanTab />}
      {sub === "workers" && <WorkersTab />}
      {sub === "deletion" && <DeletionTab />}
      {sub === "reconcile" && <ReconcileTab />}
      {sub === "maintenance" && <MaintenanceTab />}
      {sub === "schedule" && <ScheduledTasksTab />}
    </div>
  );
}

function StorageAuditTab() {
  const [scanStatus, setScanStatus] = useState<"idle" | "running" | "complete" | "failed">("idle");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [result, setResult] = useState<S3AuditResult | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [cleaning, setCleaning] = useState(false);
  const [cleanupCount, setCleanupCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!taskId || scanStatus !== "running") return;
    pollRef.current = setInterval(async () => {
      try {
        const data = await getS3AuditTask(taskId);
        if (data.status === "complete" && data.result) {
          setResult(data.result);
          setScanStatus("complete");
          clearInterval(pollRef.current!);
        } else if (data.status === "failed") {
          setError(data.error ?? "Scan failed");
          setScanStatus("failed");
          clearInterval(pollRef.current!);
        }
      } catch {
        setError("Failed to poll scan status");
        setScanStatus("failed");
        clearInterval(pollRef.current!);
      }
    }, 2000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [taskId, scanStatus]);

  async function startScan() {
    setScanStatus("running");
    setResult(null);
    setSelected(new Set());
    setCleanupCount(null);
    setError(null);
    try {
      const { task_id } = await startS3AuditScan();
      setTaskId(task_id);
    } catch {
      setScanStatus("failed");
      setError("Failed to start scan");
    }
  }

  function toggleSelect(key: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) { next.delete(key); } else { next.add(key); }
      return next;
    });
  }

  function toggleAll() {
    if (!result) return;
    setSelected((prev) =>
      prev.size === result.orphaned_files.length
        ? new Set()
        : new Set(result.orphaned_files.map((f) => f.key))
    );
  }

  async function handleCleanup() {
    if (!selected.size || !result) return;
    const noun = selected.size === 1 ? "file" : "files";
    if (!window.confirm(`Permanently delete ${selected.size} ${noun} from S3? This cannot be undone.`)) return;
    setCleaning(true);
    setError(null);
    try {
      const { deleted } = await cleanupS3Orphans(Array.from(selected));
      setCleanupCount(deleted);
      setResult({
        ...result,
        orphaned_files: result.orphaned_files.filter((f) => !selected.has(f.key)),
        orphaned_count: result.orphaned_count - deleted,
      });
      setSelected(new Set());
    } catch {
      setError("Cleanup failed — check logs");
    } finally {
      setCleaning(false);
    }
  }

  const allSelected = !!result && selected.size === result.orphaned_files.length && result.orphaned_files.length > 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button onClick={startScan} disabled={scanStatus === "running"} size="sm">
          {scanStatus === "running" ? "Scanning…" : "Scan S3 for Orphaned Files"}
        </Button>
        {scanStatus === "running" && (
          <span className="text-xs text-muted-foreground animate-pulse">Running in background…</span>
        )}
        {selected.size > 0 && (
          <>
            <span className="text-xs text-destructive">
              {selected.size} file{selected.size !== 1 ? "s" : ""} selected — permanent delete, cannot be undone.
            </span>
            <Button variant="destructive" size="sm" onClick={handleCleanup} disabled={cleaning}>
              {cleaning ? "Deleting…" : "Delete Selected"}
            </Button>
          </>
        )}
        {cleanupCount !== null && (
          <span className="text-sm text-green-600 dark:text-green-400">
            Deleted {cleanupCount} file{cleanupCount !== 1 ? "s" : ""} from S3.
          </span>
        )}
        {error && <span className="text-sm text-destructive">{error}</span>}
      </div>

      {result && (
        <div className="space-y-3">
          {result.not_applicable ? (
            <p className="text-sm text-muted-foreground">
              Storage backend is not S3 — audit not applicable in this environment.
            </p>
          ) : (
            <>
              <div className="flex gap-6 text-sm">
                <span><span className="font-medium">{result.total_s3_keys}</span> S3 keys</span>
                <span><span className="font-medium">{result.total_db_paths}</span> DB-referenced paths</span>
                <span><span className="font-medium text-amber-600 dark:text-amber-400">{result.orphaned_count}</span> orphaned</span>
              </div>

              {result.orphaned_files.length === 0 ? (
                <p className="text-sm text-muted-foreground">No orphaned files found.</p>
              ) : (
                <div className="rounded-md border overflow-auto max-h-96">
                  <table className="w-full text-xs">
                    <thead className="bg-muted sticky top-0">
                      <tr>
                        <th className="p-2 text-left w-8">
                          <input
                            type="checkbox"
                            checked={allSelected}
                            onChange={toggleAll}
                            className="cursor-pointer"
                          />
                        </th>
                        <th className="p-2 text-left font-medium">Key</th>
                        <th className="p-2 text-right font-medium">Size</th>
                        <th className="p-2 text-right font-medium">Last Modified</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.orphaned_files.map((f) => (
                        <tr key={f.key} className="border-t hover:bg-muted/50">
                          <td className="p-2">
                            <input
                              type="checkbox"
                              checked={selected.has(f.key)}
                              onChange={() => toggleSelect(f.key)}
                              className="cursor-pointer"
                            />
                          </td>
                          <td className="p-2 font-mono break-all">{f.key}</td>
                          <td className="p-2 text-right whitespace-nowrap">{formatBytes(f.size)}</td>
                          <td className="p-2 text-right whitespace-nowrap text-muted-foreground">
                            {new Date(f.last_modified).toLocaleDateString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function CveFindingsTable({ title, findings }: { title: string; findings: CveFinding[] }) {
  if (findings.length === 0) return null;
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{title}</h3>
      <div className="rounded-md border overflow-auto max-h-96">
        <table className="w-full text-xs">
          <thead className="bg-muted sticky top-0">
            <tr>
              <th className="p-2 text-left font-medium">Package</th>
              <th className="p-2 text-left font-medium">Version</th>
              <th className="p-2 text-left font-medium">CVE ID</th>
              <th className="p-2 text-left font-medium">Fix</th>
              <th className="p-2 text-left font-medium">Summary</th>
            </tr>
          </thead>
          <tbody>
            {findings.flatMap((pkg) =>
              pkg.vulns.map((v, i) => (
                <tr key={`${pkg.name}-${v.id}-${i}`} className="border-t hover:bg-muted/50">
                  <td className="p-2 font-mono">{i === 0 ? pkg.name : ""}</td>
                  <td className="p-2 font-mono tabular-nums">{i === 0 ? pkg.version : ""}</td>
                  <td className="p-2 font-mono text-destructive">{v.id}</td>
                  <td className="p-2 font-mono">{v.fix_versions.length > 0 ? v.fix_versions.join(", ") : "—"}</td>
                  <td className="p-2 text-muted-foreground max-w-xs truncate" title={v.description}>
                    {v.description || "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CveScanTab() {
  const qc = useQueryClient();
  const [scanStatus, setScanStatus] = useState<"idle" | "running" | "complete" | "failed">("idle");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [result, setResult] = useState<CveScanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!taskId || scanStatus !== "running") return;
    pollRef.current = setInterval(async () => {
      try {
        const data = await getCveScanTask(taskId);
        if (data.status === "complete" && data.result) {
          setResult(data.result);
          setScanStatus("complete");
          qc.invalidateQueries({ queryKey: ["admin", "cve-summary"] });
          clearInterval(pollRef.current!);
        } else if (data.status === "failed") {
          setError(data.error ?? "Scan failed");
          setScanStatus("failed");
          clearInterval(pollRef.current!);
        }
      } catch {
        setError("Failed to poll scan status");
        setScanStatus("failed");
        clearInterval(pollRef.current!);
      }
    }, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [taskId, scanStatus, qc]);

  async function startScan() {
    setScanStatus("running");
    setResult(null);
    setError(null);
    try {
      const { task_id } = await startCveScan(__FRONTEND_DEPS__);
      setTaskId(task_id);
    } catch {
      setScanStatus("failed");
      setError("Failed to start scan");
    }
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <p className="text-xs text-muted-foreground">
          Scans Python dependencies via pip-audit and npm packages via OSV.dev.
          Results are stored and shown in the warning banner on all admin pages.
        </p>
      </div>
      <div className="flex items-center gap-3">
        <Button onClick={startScan} disabled={scanStatus === "running"} size="sm">
          {scanStatus === "running" ? "Scanning…" : "Run CVE Scan"}
        </Button>
        {scanStatus === "running" && (
          <span className="text-xs text-muted-foreground animate-pulse">Running in background…</span>
        )}
        {error && <span className="text-sm text-destructive">{error}</span>}
      </div>

      {result && (
        <div className="space-y-4">
          <div className="flex gap-6 text-sm">
            <span>
              <span className={`font-medium ${result.total_findings > 0 ? "text-destructive" : "text-green-600 dark:text-green-400"}`}>
                {result.total_findings}
              </span>
              {" "}total {result.total_findings === 1 ? "vulnerability" : "vulnerabilities"}
            </span>
            <span className="text-xs text-muted-foreground self-center">
              scanned {new Date(result.scanned_at).toLocaleString()}
            </span>
          </div>
          {result.total_findings === 0 && (
            <p className="text-sm text-green-600 dark:text-green-400">No vulnerabilities found.</p>
          )}
          <CveFindingsTable title="Backend (Python)" findings={result.backend_findings} />
          <CveFindingsTable title="Frontend (npm)" findings={result.frontend_findings} />
        </div>
      )}
    </div>
  );
}

function WorkerCard({ worker, apiVersion }: { worker: WorkerInfo; apiVersion: string }) {
  const isOnline = worker.status === "online";
  const hasActive = worker.active_tasks.length > 0;
  const hasReserved = worker.reserved_tasks.length > 0;
  const versionMismatch = isOnline && worker.version != null && worker.version !== apiVersion;

  return (
    <div className={`border rounded-lg overflow-hidden ${versionMismatch ? "border-amber-500/50" : ""}`}>
      <div className={`flex items-center gap-3 px-4 py-3 ${versionMismatch ? "bg-amber-500/10" : "bg-muted/20"}`}>
        <span className={`w-2 h-2 rounded-full shrink-0 ${isOnline ? "bg-green-500" : "bg-red-500"}`} />
        <span className="text-sm font-mono font-medium flex-1 truncate">{worker.name}</span>
        {isOnline && worker.version && (
          <span className={`text-xs px-2 py-0.5 rounded border font-mono ${
            versionMismatch
              ? "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300"
              : "border-border text-muted-foreground"
          }`} title={versionMismatch ? `Expected ${apiVersion}` : undefined}>
            {worker.version}{versionMismatch ? " ⚠" : ""}
          </span>
        )}
        {isOnline && worker.concurrency !== null && (
          <span className={`text-xs px-2 py-0.5 rounded border tabular-nums ${
            worker.active_tasks.length >= worker.concurrency
              ? "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300"
              : worker.active_tasks.length > 0
              ? "border-blue-500/30 text-blue-600 dark:text-blue-400"
              : "border-border text-muted-foreground"
          }`}>
            {worker.active_tasks.length}/{worker.concurrency} slots
          </span>
        )}
        <span className={`text-xs px-2 py-0.5 rounded border ${isOnline ? "border-green-500/30 text-green-600 dark:text-green-400" : "border-destructive/30 text-destructive"}`}>
          {worker.status}
        </span>
      </div>
      {isOnline && (
        <div className="divide-y">
          <div className="grid grid-cols-4 divide-x px-4 py-2.5 text-sm">
            <div className="flex flex-col gap-0.5 pr-4">
              <span className="text-xs text-muted-foreground">Concurrency</span>
              <span className="font-medium tabular-nums">{worker.concurrency ?? "—"}</span>
            </div>
            <div className="flex flex-col gap-0.5 px-4">
              <span className="text-xs text-muted-foreground">Completed</span>
              <span className="font-medium tabular-nums">{worker.completed_tasks?.toLocaleString() ?? "—"}</span>
            </div>
            <div className="flex flex-col gap-0.5 px-4">
              <span className="text-xs text-muted-foreground">Uptime</span>
              <span className="font-medium tabular-nums">{worker.uptime != null ? formatUptime(worker.uptime) : "—"}</span>
            </div>
            <div className="flex flex-col gap-0.5 pl-4">
              <span className="text-xs text-muted-foreground">Memory</span>
              <span className="font-medium tabular-nums">{worker.memory_mb != null ? `${worker.memory_mb} MB` : "—"}</span>
            </div>
          </div>
          {hasActive && (
            <div className="px-4 py-2.5 space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Active ({worker.active_tasks.length})
              </p>
              {worker.active_tasks.map((t) => (
                <div key={t.id} className="text-xs space-y-0.5">
                  <p className="font-mono text-foreground">{t.name}</p>
                  <p className="text-muted-foreground truncate">{t.args_repr}</p>
                  {t.time_start && (
                    <p className="text-muted-foreground">
                      started {new Date(t.time_start * 1000).toLocaleTimeString()}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
          {hasReserved && (
            <div className="px-4 py-2.5 space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Reserved ({worker.reserved_tasks.length})
              </p>
              {worker.reserved_tasks.map((t) => (
                <div key={t.id} className="text-xs">
                  <p className="font-mono text-foreground">{t.name}</p>
                  <p className="text-muted-foreground truncate">{t.args_repr}</p>
                </div>
              ))}
            </div>
          )}
          {!hasActive && !hasReserved && (
            <p className="px-4 py-2.5 text-xs text-muted-foreground">No active or reserved tasks.</p>
          )}
        </div>
      )}
    </div>
  );
}

function WorkersTab() {
  const [data, setData] = useState<WorkerStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sleeping, setSleeping] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const fetch = () =>
      getWorkerStatus()
        .then((d) => { setData(d); setError(null); })
        .catch(() => setError("Failed to fetch worker status"));
    fetch();
    intervalRef.current = setInterval(fetch, 3_000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, []);

  function triggerSleep() {
    setSleeping(true);
    startDebugSleep(45)
      .then(() => setSleeping(false))
      .catch(() => setSleeping(false));
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <span className="text-xs text-muted-foreground">
            {data
              ? `Updated ${new Date(data.checked_at).toLocaleTimeString()} · auto-refreshes every 3s`
              : "Loading…"}
          </span>
        </div>
        <Button size="sm" variant="outline" disabled={sleeping} onClick={triggerSleep}>
          {sleeping ? "Dispatching…" : "Run test task"}
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {data && (
        <>
          {data.queues.length > 0 && (
            <div>
              <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Queues</h3>
              <div className="border rounded-lg divide-y overflow-hidden">
                {data.queues.map((q) => (
                  <div key={q.name} className="flex items-center justify-between px-4 py-2.5 bg-background">
                    <span className="text-sm font-mono">{q.name}</span>
                    <span className={`text-sm font-medium tabular-nums ${q.depth > 0 ? "text-amber-600 dark:text-amber-400" : ""}`}>
                      {q.depth} pending
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div>
            <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
              Workers ({data.workers.length})
            </h3>
            <div className="space-y-3">
              {data.workers.map((w) => (
                <WorkerCard key={w.name} worker={w} apiVersion={data.api_version} />
              ))}
            </div>
          </div>
        </>
      )}

      <TaskHistoryTable />
    </div>
  );
}

const STATE_CLS: Record<string, string> = {
  queued: "text-muted-foreground",
  running: "text-blue-600 dark:text-blue-400",
  success: "text-green-600 dark:text-green-400",
  failed: "text-destructive",
  revoked: "text-amber-600 dark:text-amber-400",
};

function fmtSec(s: number | null): string {
  if (s === null) return "—";
  if (s < 1) return `${Math.round(s * 1000)}ms`;
  return `${s.toFixed(1)}s`;
}

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function shortName(name: string): string {
  const parts = name.split(".");
  return parts.length >= 2 ? parts.slice(-2).join(".") : name;
}

function TaskHistoryRow({ item, onRevoke }: { item: TaskHistoryItem; onRevoke: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const cancellable = item.state === "queued" || item.state === "running";
  return (
    <>
      <tr
        className={`border-t hover:bg-muted/30 text-xs ${item.error ? "cursor-pointer" : ""}`}
        onClick={() => item.error && setExpanded((v) => !v)}
      >
        <td className="px-3 py-2 font-mono text-muted-foreground whitespace-nowrap">{fmtTime(item.queued_at)}</td>
        <td className="px-3 py-2 font-mono" title={item.name}>{shortName(item.name)}</td>
        <td className="px-3 py-2 text-muted-foreground">{item.caller}</td>
        <td className={`px-3 py-2 font-medium ${STATE_CLS[item.state] ?? ""}`}>{item.state}</td>
        <td className="px-3 py-2 tabular-nums text-right">{fmtSec(item.wait_seconds)}</td>
        <td className="px-3 py-2 tabular-nums text-right">{fmtSec(item.run_seconds)}</td>
        <td className="px-3 py-2 tabular-nums text-right whitespace-nowrap">{fmtTime(item.completed_at)}</td>
        <td className="px-3 py-2 text-muted-foreground">{item.error ? (expanded ? "▲" : "▼ error") : "—"}</td>
        <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
          {cancellable && (
            <button
              className="text-xs text-destructive hover:underline"
              onClick={() => onRevoke(item.task_id)}
            >
              Cancel
            </button>
          )}
        </td>
      </tr>
      {expanded && item.error && (
        <tr className="border-t bg-destructive/5">
          <td colSpan={9} className="px-3 py-2">
            <pre className="text-xs font-mono text-destructive whitespace-pre-wrap">{item.error}</pre>
          </td>
        </tr>
      )}
    </>
  );
}

function TaskHistoryTable() {
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 25;
  const queryClient = useQueryClient();

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["admin", "task-history", page],
    queryFn: () => getTaskHistory(page, PAGE_SIZE),
    refetchInterval: 5_000,
  });

  const revokeMutation = useMutation({
    mutationFn: revokeTask,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["admin", "task-history"] }),
  });

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Task History {data ? `(${data.total})` : ""}
        </h3>
        <button
          className="text-xs text-muted-foreground hover:text-foreground"
          onClick={() => refetch()}
        >
          Refresh
        </button>
      </div>

      {isLoading && <p className="text-xs text-muted-foreground">Loading…</p>}

      {data && data.items.length === 0 && (
        <p className="text-xs text-muted-foreground">No task history yet. Dispatch a task to see it here.</p>
      )}

      {data && data.items.length > 0 && (
        <>
          <div className="rounded-md border overflow-auto max-h-[480px]">
            <table className="w-full text-xs min-w-[640px]">
              <thead className="bg-muted sticky top-0">
                <tr>
                  <th className="px-3 py-2 text-left font-medium whitespace-nowrap">Queued at</th>
                  <th className="px-3 py-2 text-left font-medium">Task</th>
                  <th className="px-3 py-2 text-left font-medium">Caller</th>
                  <th className="px-3 py-2 text-left font-medium">State</th>
                  <th className="px-3 py-2 text-right font-medium whitespace-nowrap">Wait</th>
                  <th className="px-3 py-2 text-right font-medium whitespace-nowrap">Run</th>
                  <th className="px-3 py-2 text-right font-medium whitespace-nowrap">Completed at</th>
                  <th className="px-3 py-2 text-left font-medium">Error</th>
                  <th className="px-3 py-2 text-left font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <TaskHistoryRow key={item.task_id} item={item} onRevoke={(id) => revokeMutation.mutate(id)} />
                ))}
              </tbody>
            </table>
          </div>

          {data.pages > 1 && (
            <div className="flex items-center justify-between text-xs text-muted-foreground pt-1">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                className="px-2 py-1 border rounded disabled:opacity-40 hover:bg-muted/40"
              >
                ← Prev
              </button>
              <span>Page {data.page} of {data.pages}</span>
              <button
                disabled={page >= data.pages}
                onClick={() => setPage((p) => p + 1)}
                className="px-2 py-1 border rounded disabled:opacity-40 hover:bg-muted/40"
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function DeletionTab() {
  return (
    <div className="rounded-lg border border-dashed p-8 text-center">
      <p className="text-sm font-medium text-muted-foreground">Deletion Queue</p>
      <p className="text-xs text-muted-foreground mt-1">Coming soon — in-progress and pending user deletion states.</p>
    </div>
  );
}

function MaintenanceTab() {
  const queryClient = useQueryClient();
  const [purging, setPurging] = useState(false);

  function triggerPurge() {
    setPurging(true);
    runPurgeSoftDeleted()
      .then(() => {
        setPurging(false);
        queryClient.invalidateQueries({ queryKey: ["admin", "task-history"] });
      })
      .catch(() => setPurging(false));
  }

  return (
    <div className="space-y-6">
      <div className="rounded-lg border p-5 space-y-3">
        <div>
          <p className="text-sm font-medium">Purge Soft-Deleted Records</p>
          <p className="text-xs text-muted-foreground mt-1">
            Hard-deletes drafts, looms, projects, and yarn that have been soft-deleted for longer than the
            configured retention period (<code className="font-mono">SOFT_DELETE_RETENTION_DAYS</code>, default 365 days).
            Associated storage files are removed at the same time. User deletion is handled separately by the
            deletion cascade task.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            size="sm"
            variant="destructive"
            disabled={purging}
            onClick={triggerPurge}
          >
            {purging ? "Queuing…" : "Run Purge Now"}
          </Button>
          <p className="text-xs text-muted-foreground">Results appear in the Workers → Task History table.</p>
        </div>
      </div>
    </div>
  );
}

function ReconcileTab() {
  const queryClient = useQueryClient();
  const [ran, setRan] = useState(false);
  const [report, setReport] = useState<ReconcileReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [backfilling, setBackfilling] = useState<string | null>(null);
  const [backfillResults, setBackfillResults] = useState<Record<string, string>>({});

  async function runReconcile() {
    setLoading(true);
    setError(null);
    try {
      const data = await getReconcileReport();
      setReport(data);
      setRan(true);
    } catch {
      setError("Failed to run reconciliation. Check that the Clerk API key is configured.");
    } finally {
      setLoading(false);
    }
  }

  async function handleBackfill(clerkUserId: string, role: "user" | "admin") {
    setBackfilling(clerkUserId);
    try {
      const result = await backfillClerkUser(clerkUserId, role);
      setBackfillResults((prev) => ({ ...prev, [clerkUserId]: result.status }));
      setReport((prev) =>
        prev
          ? { ...prev, clerk_only: prev.clerk_only.filter((u) => u.clerk_user_id !== clerkUserId) }
          : prev
      );
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    } catch {
      setBackfillResults((prev) => ({ ...prev, [clerkUserId]: "error" }));
    } finally {
      setBackfilling(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h2 className="text-sm font-medium">Clerk ↔ DB Reconciliation</h2>
        <p className="text-xs text-muted-foreground">
          Cross-references Clerk accounts against the database. Use this to backfill users created
          directly in the Clerk dashboard.
        </p>
      </div>

      <Button onClick={runReconcile} disabled={loading} size="sm">
        {loading ? "Running…" : ran ? "Re-run reconciliation" : "Run reconciliation"}
      </Button>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {report && (
        <div className="space-y-6">
          {/* In Clerk, not in DB */}
          <div className="space-y-2">
            <h3 className="text-sm font-medium">
              In Clerk, not in DB
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                ({report.clerk_only.length} {report.clerk_only.length === 1 ? "user" : "users"})
              </span>
            </h3>
            {report.clerk_only.length === 0 ? (
              <p className="text-xs text-muted-foreground">No unmatched Clerk accounts.</p>
            ) : (
              <div className="rounded-lg border divide-y text-sm">
                {report.clerk_only.map((u) => (
                  <div key={u.clerk_user_id} className="flex items-center justify-between px-3 py-2 gap-4">
                    <div className="min-w-0">
                      <p className="font-medium truncate">{u.display_name}</p>
                      <p className="text-xs text-muted-foreground overflow-hidden"><CopyEmail email={u.email} /></p>
                      <p className="text-xs text-muted-foreground font-mono">{u.clerk_user_id}</p>
                    </div>
                    <div className="flex gap-2 shrink-0">
                      {backfillResults[u.clerk_user_id] ? (
                        <span className="text-xs text-green-600 font-medium capitalize">
                          {backfillResults[u.clerk_user_id]}
                        </span>
                      ) : (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={backfilling === u.clerk_user_id}
                            onClick={() => handleBackfill(u.clerk_user_id, "user")}
                          >
                            Backfill as user
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={backfilling === u.clerk_user_id}
                            onClick={() => handleBackfill(u.clerk_user_id, "admin")}
                          >
                            Backfill as admin
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* In DB, not in Clerk */}
          <div className="space-y-2">
            <h3 className="text-sm font-medium">
              In DB, not in Clerk
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                ({report.db_only.length} {report.db_only.length === 1 ? "user" : "users"})
              </span>
            </h3>
            {report.db_only.length === 0 ? (
              <p className="text-xs text-muted-foreground">No orphaned DB records.</p>
            ) : (
              <div className="rounded-lg border divide-y text-sm">
                {report.db_only.map((u) => (
                  <div key={u.user_id} className="flex items-center justify-between px-3 py-2 gap-4">
                    <div className="min-w-0">
                      <p className="font-medium truncate">{u.display_name}</p>
                      <p className="text-xs text-muted-foreground overflow-hidden"><CopyEmail email={u.email} /></p>
                    </div>
                    {u.clerk_errored && (
                      <span className="text-xs bg-destructive/10 text-destructive px-2 py-0.5 rounded shrink-0">
                        clerk errored
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Audit log tab
// ---------------------------------------------------------------------------

const EVENT_TYPES = [
  "user.role_changed",
  "user.banned",
  "user.unbanned",
  "user.deleted",
  "user.elevated",
  "user.backfilled",
  "user.clerk_errored",
  "eula.accepted",
  "signup.approved",
  "signup.dismissed",
  "signup.banned",
  "invite.created",
  "invite.revoked",
  "eula.created",
] as const;

function eventBadgeClass(eventType: string): string {
  if (eventType.startsWith("user.ban") || eventType === "signup.banned") return "bg-destructive/10 text-destructive";
  if (eventType === "user.deleted") return "bg-destructive/10 text-destructive";
  if (eventType === "user.elevated" || eventType === "signup.approved") return "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400";
  if (eventType === "user.unbanned") return "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400";
  return "bg-muted text-muted-foreground";
}

function formatAuditTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "medium" });
}

function AuditLogTab() {
  const [page, setPage] = useState(1);
  const [eventType, setEventType] = useState<string>("");
  const [q, setQ] = useState<string>("");
  const [debouncedQ, setDebouncedQ] = useState<string>("");

  useEffect(() => {
    const t = setTimeout(() => { setDebouncedQ(q); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [q]);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["audit-log", page, eventType, debouncedQ],
    queryFn: () => getAuditLog({ page, page_size: 50, event_type: eventType || undefined, q: debouncedQ || undefined }),
  });

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Audit Log</h2>

      <div className="flex gap-2 flex-wrap">
        <select
          value={eventType}
          onChange={(e) => { setEventType(e.target.value); setPage(1); }}
          className="text-sm border rounded px-2 py-1.5 bg-background"
        >
          <option value="">All events</option>
          {EVENT_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Search by email…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="text-sm border rounded px-2 py-1.5 bg-background w-52"
        />
        {data && (
          <span className="text-xs text-muted-foreground self-center ml-auto">
            {data.total.toLocaleString()} event{data.total !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {isError && <p className="text-sm text-destructive">Failed to load audit log.</p>}

      {data && data.items.length === 0 && (
        <p className="text-sm text-muted-foreground">No events found.</p>
      )}

      {data && data.items.length > 0 && (
        <div className="rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-xs text-muted-foreground">
              <tr>
                <th className="text-left px-3 py-2">Time</th>
                <th className="text-left px-3 py-2">Event</th>
                <th className="text-left px-3 py-2">Actor</th>
                <th className="text-left px-3 py-2">Target</th>
                <th className="text-left px-3 py-2">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {data.items.map((entry) => (
                <AuditLogRow key={entry.id} entry={entry} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.pages > 1 && (
        <div className="flex items-center gap-2 justify-center text-sm">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="px-2 py-1 border rounded disabled:opacity-40"
          >
            ←
          </button>
          <span className="text-muted-foreground">Page {data.page} of {data.pages}</span>
          <button
            disabled={page >= data.pages}
            onClick={() => setPage((p) => p + 1)}
            className="px-2 py-1 border rounded disabled:opacity-40"
          >
            →
          </button>
        </div>
      )}
    </div>
  );
}

function AuditLogRow({ entry }: { entry: AuditLogEntry }) {
  const [expanded, setExpanded] = useState(false);
  const hasDetails = entry.details && Object.keys(entry.details).length > 0;

  return (
    <>
      <tr
        className={`hover:bg-muted/30 ${hasDetails ? "cursor-pointer" : ""}`}
        onClick={() => hasDetails && setExpanded((v) => !v)}
      >
        <td className="px-3 py-2 text-muted-foreground whitespace-nowrap">{formatAuditTime(entry.created_at)}</td>
        <td className="px-3 py-2">
          <span className={`inline-block text-xs font-medium px-1.5 py-0.5 rounded ${eventBadgeClass(entry.event_type)}`}>
            {entry.event_type}
          </span>
        </td>
        <td className="px-3 py-2 text-muted-foreground">{entry.actor_email ? <CopyEmail email={entry.actor_email} /> : <span className="italic">system</span>}</td>
        <td className="px-3 py-2 text-muted-foreground">{entry.target_email ? <CopyEmail email={entry.target_email} /> : "—"}</td>
        <td className="px-3 py-2 text-muted-foreground text-xs">
          {hasDetails ? (expanded ? "▲ hide" : "▼ show") : "—"}
        </td>
      </tr>
      {expanded && hasDetails && (
        <tr>
          <td colSpan={5} className="px-3 pb-2 bg-muted/20">
            <pre className="text-xs font-mono whitespace-pre-wrap">{JSON.stringify(entry.details, null, 2)}</pre>
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Scheduled Tasks tab
// ---------------------------------------------------------------------------

const CRON_PRESETS = [
  { label: "Hourly", value: "0 * * * *" },
  { label: "Daily (2 AM UTC)", value: "0 2 * * *" },
  { label: "Weekly (Sun 2 AM)", value: "0 2 * * 0" },
  { label: "Monthly (1st 2 AM)", value: "0 2 1 * *" },
  { label: "Custom", value: "custom" },
];

function ScheduledTaskCard({ task, onSaved }: { task: ScheduledTask; onSaved: () => void }) {
  const [enabled, setEnabled] = useState(task.enabled);
  const [preset, setPreset] = useState<string>(() => {
    const match = CRON_PRESETS.find((p) => p.value === task.cron && p.value !== "custom");
    return match ? match.value : "custom";
  });
  const [customCron, setCustomCron] = useState(task.cron);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const effectiveCron = preset === "custom" ? customCron : preset;
  const isDirty = enabled !== task.enabled || effectiveCron !== task.cron;

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await patchScheduledTask(task.name, { enabled, cron: effectiveCron });
      onSaved();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to save";
      setError(msg.includes("422") ? "Invalid cron expression" : msg);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="border rounded-lg p-3 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium text-sm">{task.display_name}</p>
          <p className="text-xs text-muted-foreground mt-0.5">{task.description}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <label className="flex items-center gap-2 cursor-pointer">
            <span className="text-xs text-muted-foreground">{enabled ? "Enabled" : "Disabled"}</span>
            <button
              role="switch"
              aria-checked={enabled}
              onClick={() => setEnabled((v) => !v)}
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                enabled ? "bg-primary" : "bg-muted"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                  enabled ? "translate-x-4" : "translate-x-0.5"
                }`}
              />
            </button>
          </label>
          {error && <p className="text-xs text-destructive">{error}</p>}
          <Button size="sm" disabled={!isDirty || saving} onClick={save}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-muted-foreground">Schedule:</span>
          <select
            value={preset}
            onChange={(e) => {
              setPreset(e.target.value);
              if (e.target.value !== "custom") setCustomCron(e.target.value);
            }}
            className="text-xs border rounded px-2 py-1 bg-background"
          >
            {CRON_PRESETS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
          {preset === "custom" && (
            <input
              type="text"
              value={customCron}
              onChange={(e) => setCustomCron(e.target.value)}
              placeholder="0 2 * * *"
              className="text-xs border rounded px-2 py-1 bg-background font-mono w-36"
            />
          )}
        </div>

        {task.next_runs.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Next: {task.next_runs.slice(0, 3).map((r) => new Date(r).toLocaleString()).join(" · ")}
          </p>
        )}
        {task.last_fired_at && (
          <p className="text-xs text-muted-foreground">
            Last fired: {new Date(task.last_fired_at).toLocaleString()}
          </p>
        )}
      </div>
    </div>
  );
}

function ScheduledTasksTab() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "scheduled-tasks"],
    queryFn: listScheduledTasks,
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error) return <p className="text-sm text-destructive">Failed to load scheduled tasks.</p>;

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        Configure recurring background tasks. Settings are stored in Postgres and survive restarts.
        The scheduler tick runs every 60 seconds via Celery Beat.
      </p>
      {data && data.length === 0 && (
        <p className="text-sm text-muted-foreground">No scheduled tasks configured.</p>
      )}
      {data?.map((task) => (
        <ScheduledTaskCard
          key={task.name}
          task={task}
          onSaved={() => qc.invalidateQueries({ queryKey: ["admin", "scheduled-tasks"] })}
        />
      ))}
    </div>
  );
}
