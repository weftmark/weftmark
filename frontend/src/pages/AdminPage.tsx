import React, { useState, useEffect, useRef } from "react";
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
} from "@/api/admin";
import { getHealthDetailed, type ReadinessResponse, type ReadinessService } from "@/api/health";
import { EulaContent } from "@/components/EulaContent";
import { CopyEmail } from "@/components/admin/CopyEmail";
import { formatBytes } from "@/lib/image-utils";

type Tab = "users" | "invites" | "stats" | "health" | "services" | "audit" | "superuser";

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

export function AdminPage() {
  const [tab, setTab] = useState<Tab>("users");
  const { user: currentUser } = useAuth();

  return (
    <div className="p-6 max-w-4xl mx-auto w-full space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">Admin</h1>
        {currentUser?.is_superuser && (
          <span className="text-xs border rounded px-1.5 py-0.5 text-muted-foreground">superuser</span>
        )}
      </div>
        <div className="flex gap-2 border-b pb-2 flex-wrap">
          {(["users", "invites", "stats", "health", "services", "audit"] as Tab[]).map((t) => (
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
          {currentUser?.is_superuser && (
            <button
              onClick={() => setTab("superuser")}
              className={`px-3 py-1.5 text-sm rounded capitalize ${
                tab === "superuser"
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              superuser
            </button>
          )}
        </div>

        {tab === "users" && <UsersTab />}
        {tab === "invites" && <InvitesTab />}
        {tab === "stats" && <StatsTab />}
        {tab === "health" && <HealthTab />}
        {tab === "services" && <ServicesTab />}
        {tab === "audit" && <AuditLogTab />}
        {tab === "superuser" && <SuperuserTab />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Users tab — helpers
// ---------------------------------------------------------------------------

type SortKey =
  | "name" | "status" | "role" | "drafts" | "activities"
  | "looms" | "storage" | "last_login" | "joined";

interface UserRow {
  id: string;
  display_name: string;
  email: string;
  status: "active" | "inactive" | "banned" | "pending" | "errored" | "deleting";
  role: "superuser" | "admin" | "user";
  drafts: number;
  activities: number;
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
      activities: u.counts.projects_active + u.counts.projects_completed,
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
      activities: 0,
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
      case "activities": cmp = a.activities - b.activities; break;
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
              <SortTh label="Projects" k="activities" sort={sortKey} dir={sortDir} onSort={handleSort} />
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
                  {row.activities || "—"}
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

      <VersionsTable />
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
    { label: "PostgreSQL", value: `${data.postgres} · ${data.postgres_source}` },
    { label: "Redis", value: data.redis_server },
    { label: "Celery", value: data.celery },
  ];

  const deps = [
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
    <div className="space-y-4">
      <div>
        <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Versions</h2>
        <InfoTable rows={versions} />
      </div>
      <div>
        <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Dependencies</h2>
        <InfoTable rows={deps} />
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
// Superuser tab
// ---------------------------------------------------------------------------

type SuperuserSubTab = "eula" | "storage" | "deletion" | "reconcile";

function SuperuserTab() {
  const [sub, setSub] = useState<SuperuserSubTab>("eula");

  return (
    <div className="space-y-4">
      <div className="flex gap-2 border-b pb-2">
        {(["eula", "storage", "deletion", "reconcile"] as SuperuserSubTab[]).map((t) => (
          <button
            key={t}
            onClick={() => setSub(t)}
            className={`px-3 py-1.5 text-sm rounded capitalize ${
              sub === t
                ? "bg-foreground text-background"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {t === "eula" ? "EULA" : t}
          </button>
        ))}
      </div>

      {sub === "eula" && <EulaTab />}
      {sub === "storage" && <StorageAuditTab />}
      {sub === "deletion" && <DeletionTab />}
      {sub === "reconcile" && <ReconcileTab />}
    </div>
  );
}

function StorageAuditTab() {
  return (
    <div className="rounded-lg border border-dashed p-8 text-center">
      <p className="text-sm font-medium text-muted-foreground">Storage Audit</p>
      <p className="text-xs text-muted-foreground mt-1">Coming soon — per-user S3 storage breakdown.</p>
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
    const t = setTimeout(() => setDebouncedQ(q), 300);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => { setPage(1); }, [eventType, debouncedQ]); // eslint-disable-line react-hooks/set-state-in-effect

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
          onChange={(e) => setEventType(e.target.value)}
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
