import React, { useState, useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import { CveBanner } from "@/components/admin/CveBanner";
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
  getAdminServices,
  getAdminDbInfo,
  sendTestEmail,
  testWebhook,
  getAuditLog,
  getServerEvents,
  listProjectSlugs,
  adminRevokeSlug,
  listProjectSteps,
  type AdminProjectStep,
  type AdminSlugRecord,
  type AdminUser,
  type AdminHealth,
  type AdminDbInfo,
  type AuditLogEntry,
  type InviteRecord,
  type PendingSignup,
  type ServiceCheck,
  type ServicePermCheck,
  type WebhookProbeResult,
  type ServerEvent,
} from "@/api/admin";
import {
  listAdminFeedback,
  softDeleteFeedback,
  recoverFeedback,
  retryFeedbackDispatch,
  SUBMISSION_TYPE_LABELS,
  type FeedbackRecord,
  type SubmissionType,
} from "@/api/feedback";
import { getHealthDetailed, type ReadinessResponse, type ReadinessService } from "@/api/health";
import { CopyEmail } from "@/components/admin/CopyEmail";
import { formatBytes } from "@/lib/image-utils";
import {
  adminListLoomCatalog,
  adminCreateLoomReference,
  adminUpdateLoomReference,
  adminDeleteLoomReference,
  type LoomReferenceDetail,
} from "@/api/looms";

type Tab = "users" | "invites" | "stats" | "health" | "services" | "deps" | "audit" | "slugs" | "feedback" | "looms";

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
      {tab === "feedback" && <FeedbackTab />}
      {tab === "slugs" && <SlugsTab />}
      {tab === "looms" && <LoomDatabaseTab />}
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
    <div className="space-y-6">
      <div className="space-y-1 pb-2 border-b">
        <h1 className="text-lg font-semibold">Users</h1>
        <p className="text-sm text-muted-foreground">Manage all registered accounts — approve, adjust roles, and ban or delete users.</p>
      </div>
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
      <div className="space-y-1 pb-2 border-b">
        <h1 className="text-lg font-semibold">Invites</h1>
        <p className="text-sm text-muted-foreground">Create invite codes for new users and manage pending self-registration requests.</p>
      </div>
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
    <div className="space-y-6">
      <div className="space-y-1 pb-2 border-b">
        <h1 className="text-lg font-semibold">Stats</h1>
        <p className="text-sm text-muted-foreground">Aggregate counts across users and content in the database.</p>
      </div>
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
      <div className="space-y-1 pb-2 border-b">
        <h1 className="text-lg font-semibold">System Health</h1>
        <p className="text-sm text-muted-foreground">Live metrics for CPU, memory, and database response time, sampled every 3 seconds.</p>
      </div>
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
    <div className="space-y-6">
      <div className="space-y-1 pb-2 border-b">
        <h1 className="text-lg font-semibold">Dependencies</h1>
        <p className="text-sm text-muted-foreground">Installed package versions for the backend runtime and worker.</p>
      </div>
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
    <div className="space-y-6">
      <div className="space-y-1 pb-2 border-b">
        <h1 className="text-lg font-semibold">Services</h1>
        <p className="text-sm text-muted-foreground">Connectivity checks and diagnostics for external services and infrastructure components.</p>
      </div>
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
// Slugs tab
// ---------------------------------------------------------------------------

function SlugsTab() {
  const queryClient = useQueryClient();

  const { data: slugs = [], isLoading } = useQuery({
    queryKey: ["admin", "project-slugs"],
    queryFn: listProjectSlugs,
  });

  const revokeMutation = useMutation({
    mutationFn: (slug: string) => adminRevokeSlug(slug),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "project-slugs"] }),
  });

  return (
    <div className="space-y-6">
      <div className="space-y-1 pb-2 border-b">
        <h1 className="text-lg font-semibold">Share Links</h1>
        <p className="text-sm text-muted-foreground">All active project share links across users, with options to revoke.</p>
      </div>
      {isLoading && <div className="text-sm text-muted-foreground py-8 text-center">Loading…</div>}
      {!isLoading && slugs.length === 0 && <div className="text-sm text-muted-foreground py-8 text-center">No active share links.</div>}
      {!isLoading && slugs.length > 0 && (<div className="space-y-3">
      <div className="flex items-center justify-end">
        <span className="text-xs text-muted-foreground">{slugs.length} link{slugs.length !== 1 ? "s" : ""}</span>
      </div>
      <div className="rounded-lg border border-border overflow-x-auto">
        <table className="w-full text-sm min-w-[700px]">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              {["Slug", "Project", "Owner", "Visibility", "Status", "Expires", ""].map((h) => (
                <th key={h} className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {slugs.map((row: AdminSlugRecord) => {
              const expired = row.share_expires_at ? new Date(row.share_expires_at) <= new Date() : false;
              return (
                <tr key={row.slug} className="border-b border-border last:border-0 hover:bg-muted/20">
                  <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">
                    <a
                      href={`/p/${row.slug}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:underline"
                    >
                      {row.slug}
                    </a>
                  </td>
                  <td className="px-3 py-2.5 max-w-[200px] truncate">{row.project_name}</td>
                  <td className="px-3 py-2.5 text-xs text-muted-foreground">{row.owner_email}</td>
                  <td className="px-3 py-2.5 text-xs capitalize">{row.share_visibility}</td>
                  <td className="px-3 py-2.5 text-xs capitalize">{row.project_status}</td>
                  <td className="px-3 py-2.5 text-xs">
                    {row.share_expires_at ? (
                      <span className={expired ? "text-destructive" : ""}>
                        {new Date(row.share_expires_at).toLocaleDateString()}
                        {expired && " (expired)"}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">Never</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive h-7 px-2"
                      onClick={() => {
                        if (confirm(`Revoke share link for "${row.project_name}"?`)) {
                          revokeMutation.mutate(row.slug);
                        }
                      }}
                      disabled={revokeMutation.isPending}
                    >
                      Revoke
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>)}
      <StepLogSection />
    </div>
  );
}

function StepLogSection() {
  const [projectId, setProjectId] = useState("");
  const [submittedId, setSubmittedId] = useState<string | null>(null);

  const { data: steps, isLoading, isError } = useQuery({
    queryKey: ["admin", "project-steps", submittedId],
    queryFn: () => listProjectSteps(submittedId!, 200),
    enabled: !!submittedId,
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = projectId.trim();
    if (trimmed) setSubmittedId(trimmed);
  }

  function formatDwell(ms: number | null) {
    if (ms == null) return "—";
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  }

  return (
    <div className="space-y-3 mt-8">
      <h2 className="text-base font-semibold">Project step log</h2>
      <form onSubmit={handleSubmit} className="flex gap-2 items-center">
        <input
          className="border border-border rounded px-2 py-1 text-sm bg-input flex-1 max-w-sm"
          placeholder="Project ID (UUID)"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
        />
        <Button type="submit" size="sm" variant="secondary">Load</Button>
      </form>
      {isLoading && <div className="text-sm text-muted-foreground">Loading…</div>}
      {isError && <div className="text-sm text-destructive">Failed to load steps.</div>}
      {steps && steps.length === 0 && (
        <div className="text-sm text-muted-foreground">No steps recorded for this project.</div>
      )}
      {steps && steps.length > 0 && (
        <div className="rounded-lg border border-border overflow-x-auto">
          <table className="w-full text-sm min-w-[560px]">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="px-3 py-2 font-medium">Timestamp</th>
                <th className="px-3 py-2 font-medium">Event</th>
                <th className="px-3 py-2 font-medium">Pick</th>
                <th className="px-3 py-2 font-medium">Dwell</th>
              </tr>
            </thead>
            <tbody>
              {steps.map((s: AdminProjectStep) => (
                <tr key={s.id} className="border-b border-border last:border-0 hover:bg-muted/20">
                  <td className="px-3 py-1.5 font-mono text-xs text-muted-foreground whitespace-nowrap">
                    {new Date(s.created_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-1.5">
                    <span className={s.event_type === "advance" ? "text-green-600 dark:text-green-400" : "text-amber-600 dark:text-amber-400"}>
                      {s.event_type}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 font-mono text-xs">
                    {s.from_pick} → {s.to_pick}
                  </td>
                  <td className="px-3 py-1.5 text-xs text-muted-foreground">{formatDwell(s.dwell_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Feedback tab
// ---------------------------------------------------------------------------

function FeedbackTab() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [typeFilter, setTypeFilter] = useState<SubmissionType | "">("");
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [detail, setDetail] = useState<FeedbackRecord | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["admin", "feedback", page, typeFilter, includeDeleted],
    queryFn: () =>
      listAdminFeedback({
        page,
        page_size: 25,
        submission_type: typeFilter || undefined,
        include_deleted: includeDeleted,
      }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => softDeleteFeedback(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "feedback"] });
      setDetail(null);
    },
  });

  const retryMutation = useMutation({
    mutationFn: (id: string) => retryFeedbackDispatch(id),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["admin", "feedback"] });
      setDetail(updated);
    },
  });

  const recoverMutation = useMutation({
    mutationFn: (id: string) => recoverFeedback(id),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["admin", "feedback"] });
      setDetail(updated);
    },
  });

  const STATUS_COLORS: Record<string, string> = {
    sent: "text-green-600 dark:text-green-400",
    failed: "text-destructive",
    pending: "text-amber-600 dark:text-amber-400",
    skipped: "text-muted-foreground",
  };

  return (
    <div className="space-y-6">
      <div className="space-y-1 pb-2 border-b">
        <h1 className="text-lg font-semibold">Feedback</h1>
        <p className="text-sm text-muted-foreground">Review all user-submitted feedback, bug reports, and feature requests.</p>
      </div>
      <div className="flex items-center justify-end flex-wrap gap-2">
        <div className="flex items-center gap-2 text-sm">
          <select
            className="rounded-md border border-border bg-background px-2 py-1 text-sm"
            value={typeFilter}
            onChange={(e) => { setTypeFilter(e.target.value as SubmissionType | ""); setPage(1); }}
          >
            <option value="">All types</option>
            {(Object.entries(SUBMISSION_TYPE_LABELS) as [SubmissionType, string][]).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          <label className="flex items-center gap-1.5 cursor-pointer text-muted-foreground">
            <input type="checkbox" checked={includeDeleted} onChange={(e) => setIncludeDeleted(e.target.checked)} />
            Show deleted
          </label>
        </div>
      </div>

      {isLoading && <div className="text-sm text-muted-foreground py-8 text-center">Loading…</div>}
      {data && data.items.length === 0 && (
        <div className="text-sm text-muted-foreground py-8 text-center">No submissions found.</div>
      )}
      {data && data.items.length > 0 && (
        <div className="rounded-lg border border-border overflow-x-auto">
          <table className="w-full text-sm min-w-[600px]">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="px-3 py-2 font-medium">Date</th>
                <th className="px-3 py-2 font-medium">Type</th>
                <th className="px-3 py-2 font-medium">Subject</th>
                <th className="px-3 py-2 font-medium">User</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item: FeedbackRecord) => (
                <tr
                  key={item.id}
                  className={`border-b border-border last:border-0 hover:bg-muted/20 ${item.deleted_at ? "opacity-50" : ""}`}
                >
                  <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">
                    {new Date(item.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {SUBMISSION_TYPE_LABELS[item.submission_type as SubmissionType] ?? item.submission_type}
                  </td>
                  <td className="px-3 py-2 max-w-[200px] truncate text-muted-foreground">
                    {item.subject ?? item.body.slice(0, 60)}
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {item.is_anonymous ? "Anonymous" : (item.user_email ?? "—")}
                  </td>
                  <td className={`px-3 py-2 text-xs ${STATUS_COLORS[item.dispatch_status] ?? ""}`}>
                    {item.dispatch_status}
                  </td>
                  <td className="px-3 py-2">
                    <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => setDetail(item)}>
                      View
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-end gap-2 text-sm">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</Button>
          <span className="text-muted-foreground">{page} / {data.pages}</span>
          <Button variant="outline" size="sm" disabled={page >= data.pages} onClick={() => setPage(p => p + 1)}>Next</Button>
        </div>
      )}

      {/* Detail modal */}
      {detail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setDetail(null)}>
          <div className="w-full max-w-lg rounded-lg border border-border bg-background shadow-xl p-6 space-y-4 max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">
                {SUBMISSION_TYPE_LABELS[detail.submission_type as SubmissionType] ?? detail.submission_type}
              </h3>
              <button onClick={() => setDetail(null)} className="rounded-md p-1 text-muted-foreground hover:bg-muted">
                <span className="text-xs">✕</span>
              </button>
            </div>

            {detail.subject && <p className="font-medium text-sm">{detail.subject}</p>}
            <p className="text-sm whitespace-pre-wrap border border-border rounded p-3 bg-muted/30">{detail.body}</p>

            {detail.diagnostics && Object.keys(detail.diagnostics).length > 0 && (
              <div className="text-xs text-muted-foreground space-y-1">
                <p className="font-medium text-foreground">Diagnostics</p>
                {Object.entries(detail.diagnostics).map(([k, v]) =>
                  v ? <p key={k}><span className="font-mono">{k}:</span> {String(v)}</p> : null
                )}
              </div>
            )}

            <div className="text-xs text-muted-foreground space-y-1">
              <p>Submitted: {new Date(detail.created_at).toLocaleString()}</p>
              <p>User: {detail.is_anonymous ? "Anonymous" : (detail.user_email ?? "Unauthenticated")}</p>
              <p>Dispatch: <span className={STATUS_COLORS[detail.dispatch_status] ?? ""}>{detail.dispatch_status}</span></p>
              {detail.github_discussion_url && (
                <p>
                  <a href={detail.github_discussion_url} target="_blank" rel="noopener noreferrer" className="underline text-primary">
                    View on GitHub
                  </a>
                </p>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-2 flex-wrap">
              {/* Retry dispatch: shown for failed or pending submissions */}
              {!detail.deleted_at && (detail.dispatch_status === "failed" || detail.dispatch_status === "pending") && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={retryMutation.isPending}
                  onClick={() => retryMutation.mutate(detail.id)}
                >
                  {retryMutation.isPending ? "Retrying…" : "Retry dispatch"}
                </Button>
              )}
              {detail.deleted_at ? (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={recoverMutation.isPending}
                  onClick={() => recoverMutation.mutate(detail.id)}
                >
                  {recoverMutation.isPending ? "Recovering…" : "Recover"}
                </Button>
              ) : (
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive hover:text-destructive"
                  disabled={deleteMutation.isPending}
                  onClick={() => {
                    if (confirm("Soft-delete this submission?")) deleteMutation.mutate(detail.id);
                  }}
                >
                  {deleteMutation.isPending ? "Deleting…" : "Delete"}
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={() => setDetail(null)}>Close</Button>
            </div>
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
    <div className="space-y-6">
      <div className="space-y-1 pb-2 border-b">
        <h1 className="text-lg font-semibold">Audit Log</h1>
        <p className="text-sm text-muted-foreground">Immutable record of admin actions and significant account events.</p>
      </div>

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
// Loom Database tab
// ---------------------------------------------------------------------------

const LOOM_CATEGORY_OPTIONS = [
  { value: "floor_loom", label: "Floor Loom" },
  { value: "table_loom", label: "Table Loom" },
  { value: "rigid_heddle", label: "Rigid Heddle" },
  { value: "inkle", label: "Inkle" },
  { value: "dobby_floor_loom", label: "Dobby Floor Loom" },
  { value: "tapestry_loom", label: "Tapestry Loom" },
  { value: "rug_loom", label: "Rug Loom" },
  { value: "frame_loom", label: "Frame Loom" },
  { value: "other", label: "Other" },
];

const SHEDDING_OPTIONS = [
  "jack_rising", "counterbalance", "countermarch", "dobby_mechanical",
  "dobby_electronic", "tapestry", "other",
];

function parseIntArray(s: string): number[] | undefined {
  const parts = s.split(",").map((p) => p.trim()).filter(Boolean).map(Number).filter((n) => !isNaN(n));
  return parts.length > 0 ? parts : undefined;
}

function parseFloatArray(s: string): number[] | undefined {
  const parts = s.split(",").map((p) => p.trim()).filter(Boolean).map(Number).filter((n) => !isNaN(n));
  return parts.length > 0 ? parts : undefined;
}

function formatArray(arr: number[] | null | undefined): string {
  return arr ? arr.join(", ") : "";
}

interface LoomRefForm {
  brand: string;
  model_name: string;
  model_series: string;
  loom_category: string;
  shedding_mechanism: string;
  shaft_count_options: string;
  treadle_count: string;
  weaving_width_options_inches: string;
  weaving_width_options_cm: string;
  foldable: "" | "true" | "false";
  origin_country: string;
}

function emptyForm(): LoomRefForm {
  return {
    brand: "", model_name: "", model_series: "", loom_category: "floor_loom",
    shedding_mechanism: "", shaft_count_options: "", treadle_count: "",
    weaving_width_options_inches: "", weaving_width_options_cm: "",
    foldable: "", origin_country: "",
  };
}

function formFromRef(ref: LoomReferenceDetail): LoomRefForm {
  return {
    brand: ref.brand,
    model_name: ref.model_name,
    model_series: ref.model_series ?? "",
    loom_category: ref.loom_category,
    shedding_mechanism: ref.shedding_mechanism ?? "",
    shaft_count_options: formatArray(ref.shaft_count_options),
    treadle_count: formatArray(ref.treadle_count),
    weaving_width_options_inches: formatArray(ref.weaving_width_options_inches),
    weaving_width_options_cm: formatArray(ref.weaving_width_options_cm),
    foldable: ref.foldable === null ? "" : ref.foldable ? "true" : "false",
    origin_country: ref.origin_country ?? "",
  };
}

function buildPayload(form: LoomRefForm): Partial<LoomReferenceDetail> {
  return {
    brand: form.brand.trim(),
    model_name: form.model_name.trim(),
    model_series: form.model_series.trim() || undefined,
    loom_category: form.loom_category,
    shedding_mechanism: form.shedding_mechanism || undefined,
    shaft_count_options: parseIntArray(form.shaft_count_options) ?? null,
    treadle_count: parseIntArray(form.treadle_count) ?? null,
    weaving_width_options_inches: parseFloatArray(form.weaving_width_options_inches) ?? null,
    weaving_width_options_cm: parseFloatArray(form.weaving_width_options_cm) ?? null,
    foldable: form.foldable === "" ? null : form.foldable === "true",
    origin_country: form.origin_country.trim() || undefined,
  };
}

function LoomRefFormModal({
  title,
  form,
  onChange,
  onSave,
  onCancel,
  saving,
  error,
}: {
  title: string;
  form: LoomRefForm;
  onChange: (f: LoomRefForm) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
  error: string | null;
}) {
  const inputCls = "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring";
  const labelCls = "mb-1 block text-sm font-medium";

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 overflow-y-auto">
      <div className="w-full max-w-lg rounded-lg border bg-background shadow-lg p-6 space-y-4 my-8">
        <h3 className="font-semibold">{title}</h3>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelCls}>Brand <span className="text-destructive">*</span></label>
            <input className={inputCls} value={form.brand} onChange={(e) => onChange({ ...form, brand: e.target.value })} placeholder="Schacht" />
          </div>
          <div>
            <label className={labelCls}>Model name <span className="text-destructive">*</span></label>
            <input className={inputCls} value={form.model_name} onChange={(e) => onChange({ ...form, model_name: e.target.value })} placeholder="Baby Wolf" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelCls}>Series <span className="text-muted-foreground font-normal text-xs">(optional)</span></label>
            <input className={inputCls} value={form.model_series} onChange={(e) => onChange({ ...form, model_series: e.target.value })} placeholder="Wolf Family" />
          </div>
          <div>
            <label className={labelCls}>Category</label>
            <select className={inputCls} value={form.loom_category} onChange={(e) => onChange({ ...form, loom_category: e.target.value })}>
              {LOOM_CATEGORY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelCls}>Shedding mechanism</label>
            <select className={inputCls} value={form.shedding_mechanism} onChange={(e) => onChange({ ...form, shedding_mechanism: e.target.value })}>
              <option value="">—</option>
              {SHEDDING_OPTIONS.map((o) => <option key={o} value={o}>{o.replace(/_/g, " ")}</option>)}
            </select>
          </div>
          <div>
            <label className={labelCls}>Origin country</label>
            <input className={inputCls} value={form.origin_country} onChange={(e) => onChange({ ...form, origin_country: e.target.value })} placeholder="USA" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelCls}>Shaft count options <span className="text-muted-foreground font-normal text-xs">comma-separated</span></label>
            <input className={inputCls} value={form.shaft_count_options} onChange={(e) => onChange({ ...form, shaft_count_options: e.target.value })} placeholder="4, 8" />
          </div>
          <div>
            <label className={labelCls}>Treadle count options <span className="text-muted-foreground font-normal text-xs">parallel to shafts</span></label>
            <input className={inputCls} value={form.treadle_count} onChange={(e) => onChange({ ...form, treadle_count: e.target.value })} placeholder="6, 10" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelCls}>Weaving width (inches) <span className="text-muted-foreground font-normal text-xs">comma-separated</span></label>
            <input className={inputCls} value={form.weaving_width_options_inches} onChange={(e) => onChange({ ...form, weaving_width_options_inches: e.target.value })} placeholder="26" />
          </div>
          <div>
            <label className={labelCls}>Weaving width (cm) <span className="text-muted-foreground font-normal text-xs">comma-separated</span></label>
            <input className={inputCls} value={form.weaving_width_options_cm} onChange={(e) => onChange({ ...form, weaving_width_options_cm: e.target.value })} placeholder="66" />
          </div>
        </div>

        <div>
          <label className={labelCls}>Foldable</label>
          <select className={inputCls} value={form.foldable} onChange={(e) => onChange({ ...form, foldable: e.target.value as LoomRefForm["foldable"] })}>
            <option value="">Unknown</option>
            <option value="true">Yes</option>
            <option value="false">No</option>
          </select>
        </div>

        {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="outline" onClick={onCancel} disabled={saving}>Cancel</Button>
          <Button onClick={onSave} disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
        </div>
      </div>
    </div>
  );
}


function LoomDatabaseTab() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<LoomReferenceDetail | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<LoomReferenceDetail | null>(null);
  const [form, setForm] = useState<LoomRefForm>(emptyForm());
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setDebouncedSearch(search), 300);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [search]);

  const { data: refs = [], isLoading } = useQuery({
    queryKey: ["admin", "loom-catalog", debouncedSearch],
    queryFn: () => adminListLoomCatalog(debouncedSearch || undefined),
  });

  function openAdd() {
    setForm(emptyForm());
    setFormError(null);
    setAdding(true);
  }

  function openEdit(ref: LoomReferenceDetail) {
    setForm(formFromRef(ref));
    setFormError(null);
    setEditing(ref);
  }

  function closeForm() { setAdding(false); setEditing(null); setFormError(null); }

  async function handleSave() {
    if (!form.brand.trim()) { setFormError("Brand is required"); return; }
    if (!form.model_name.trim()) { setFormError("Model name is required"); return; }
    setSaving(true); setFormError(null);
    try {
      const payload = buildPayload(form);
      if (adding) {
        await adminCreateLoomReference(payload);
      } else if (editing) {
        await adminUpdateLoomReference(editing.id, payload);
      }
      queryClient.invalidateQueries({ queryKey: ["admin", "loom-catalog"] });
      closeForm();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await adminDeleteLoomReference(deleteTarget.id);
      queryClient.invalidateQueries({ queryKey: ["admin", "loom-catalog"] });
      setDeleteTarget(null);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Failed to delete");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="space-y-1 pb-2 border-b flex-1 mr-4">
          <h1 className="text-lg font-semibold">Loom Database</h1>
          <p className="text-sm text-muted-foreground">Admin-maintained catalog of commercially available looms, used for typeahead in loom creation.</p>
        </div>
        <Button size="sm" onClick={openAdd}>Add loom</Button>
      </div>

      <input
        type="search"
        placeholder="Search brand or model…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full max-w-xs rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
      />

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : refs.length === 0 ? (
        <p className="text-sm text-muted-foreground py-4 text-center">
          {debouncedSearch ? "No looms match that search." : "No looms in the catalog yet."}
        </p>
      ) : (
        <div className="rounded-md border border-border overflow-x-auto">
          <table className="w-full text-sm min-w-[700px]">
            <thead className="bg-muted/50">
              <tr>
                {["Brand", "Model", "Category", "Shafts", "Widths (in)", "Foldable", "Origin", ""].map((h) => (
                  <th key={h} className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {refs.map((ref) => (
                <tr key={ref.id} className="hover:bg-muted/30">
                  <td className="px-3 py-2.5 font-medium whitespace-nowrap">{ref.brand}</td>
                  <td className="px-3 py-2.5">
                    <span>{ref.model_name}</span>
                    {ref.model_series && (
                      <span className="ml-1.5 text-xs text-muted-foreground">{ref.model_series}</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                    {LOOM_CATEGORY_OPTIONS.find((o) => o.value === ref.loom_category)?.label ?? ref.loom_category}
                  </td>
                  <td className="px-3 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                    {ref.shaft_count_options ? ref.shaft_count_options.join(", ") : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                    {ref.weaving_width_options_inches ? ref.weaving_width_options_inches.join(", ") : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-xs text-muted-foreground">
                    {ref.foldable === null ? "—" : ref.foldable ? "Yes" : "No"}
                  </td>
                  <td className="px-3 py-2.5 text-xs text-muted-foreground">{ref.origin_country ?? "—"}</td>
                  <td className="px-3 py-2.5 text-right whitespace-nowrap">
                    <button className="text-xs text-muted-foreground hover:text-foreground mr-3" onClick={() => openEdit(ref)}>
                      Edit
                    </button>
                    <button className="text-xs text-destructive hover:text-destructive/80" onClick={() => setDeleteTarget(ref)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {refs.length > 0 && (
        <p className="text-xs text-muted-foreground">{refs.length} {refs.length === 1 ? "entry" : "entries"}</p>
      )}

      {(adding || editing) && (
        <LoomRefFormModal
          title={adding ? "Add loom" : `Edit — ${editing?.brand} ${editing?.model_name}`}
          form={form}
          onChange={setForm}
          onSave={handleSave}
          onCancel={closeForm}
          saving={saving}
          error={formError}
        />
      )}

      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-lg border bg-background shadow-lg p-6 space-y-4">
            <h3 className="font-semibold">Delete loom?</h3>
            <p className="text-sm text-muted-foreground">
              Permanently remove <strong>{deleteTarget.brand} {deleteTarget.model_name}</strong> from the catalog.
              Existing user looms linked to this entry will be unlinked automatically.
            </p>
            {formError && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{formError}</p>}
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
