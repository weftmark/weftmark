import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import {
  listAdminUsers,
  getAdminStats,
  patchAdminUser,
  listInvites,
  createInvite,
  revokeInvite,
  type InviteRecord,
} from "@/api/admin";

type Tab = "users" | "invites" | "stats";

export function AdminPage() {
  const [tab, setTab] = useState<Tab>("users");

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">
            ← Dashboard
          </Link>
          <span className="font-semibold">Admin</span>
        </div>
      </header>

      <main className="flex-1 p-6 max-w-4xl mx-auto w-full space-y-6">
        <div className="flex gap-2 border-b pb-2">
          {(["users", "invites", "stats"] as Tab[]).map((t) => (
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
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Users tab
// ---------------------------------------------------------------------------

function UsersTab() {
  const qc = useQueryClient();
  const { data: users = [], isLoading } = useQuery({
    queryKey: ["admin", "users"],
    queryFn: listAdminUsers,
  });

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { is_active?: boolean; is_admin?: boolean } }) =>
      patchAdminUser(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
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
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {u.is_admin && (
                <span className="text-xs border rounded px-1.5 py-0.5 text-muted-foreground">admin</span>
              )}
              {!u.is_active && (
                <span className="text-xs border border-destructive rounded px-1.5 py-0.5 text-destructive">
                  deactivated
                </span>
              )}
              <Button
                size="sm"
                variant="outline"
                disabled={patch.isPending}
                onClick={() => patch.mutate({ id: u.id, body: { is_admin: !u.is_admin } })}
              >
                {u.is_admin ? "Remove admin" : "Make admin"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={patch.isPending}
                onClick={() => patch.mutate({ id: u.id, body: { is_active: !u.is_active } })}
              >
                {u.is_active ? "Deactivate" : "Reactivate"}
              </Button>
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

function InvitesTab() {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);

  const { data: invites = [], isLoading } = useQuery({
    queryKey: ["admin", "invites"],
    queryFn: listInvites,
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

  const revoke = useMutation({
    mutationFn: (id: string) => revokeInvite(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "invites"] }),
  });

  const pending = invites.filter((i) => !i.accepted_at && !i.revoked_at && new Date(i.expires_at) > new Date());
  const past = invites.filter((i) => i.accepted_at || i.revoked_at || new Date(i.expires_at) <= new Date());

  return (
    <div className="space-y-6">
      {/* Send invite form */}
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
          <Button
            size="sm"
            disabled={!email || send.isPending}
            onClick={() => send.mutate(email)}
          >
            Send
          </Button>
        </div>
        {sent && <p className="text-xs text-green-600">Invite sent to {sent}</p>}
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>

      {/* Pending invites */}
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
              <h2 className="text-sm font-medium text-muted-foreground">Past invites</h2>
              <div className="divide-y border rounded-lg overflow-hidden opacity-60">
                {past.map((inv) => (
                  <InviteRow key={inv.id} invite={inv} />
                ))}
              </div>
            </div>
          )}

          {invites.length === 0 && (
            <p className="text-sm text-muted-foreground">No invites yet.</p>
          )}
        </>
      )}
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

  const rows = [
    { label: "Total users", value: data.total_users },
    { label: "Active users", value: data.active_users },
    { label: "Projects", value: data.total_projects },
    { label: "Activities", value: data.total_activities },
    { label: "Looms", value: data.total_looms },
    { label: "Yarn entries", value: data.total_yarn },
    { label: "Pending invites", value: data.pending_invites },
  ];

  return (
    <div className="border rounded-lg divide-y overflow-hidden">
      {rows.map(({ label, value }) => (
        <div key={label} className="flex items-center justify-between px-4 py-3 bg-background">
          <span className="text-sm">{label}</span>
          <span className="text-sm font-medium tabular-nums">{value}</span>
        </div>
      ))}
    </div>
  );
}
