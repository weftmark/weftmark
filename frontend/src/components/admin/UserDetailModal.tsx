import { useState, type ReactNode } from "react";
import { CopyEmail } from "@/components/admin/CopyEmail";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { formatBytes } from "@/lib/image-utils";
import { useAuth } from "@/hooks/useAuth";
import {
  patchAdminUser,
  banUser,
  unbanUser,
  elevateToSuperuser,
  deleteUser,
  approvePendingSignup,
  dismissPendingSignup,
  banPendingSignup,
  type AdminUser,
  type PendingSignup,
  type ElevateContentSummary,
} from "@/api/admin";

export type UserDetailTarget =
  | { kind: "user"; user: AdminUser }
  | { kind: "pending"; signup: PendingSignup };

interface Props {
  target: UserDetailTarget;
  onClose: () => void;
}

type Confirm =
  | "deactivate" | "ban" | "delete" | "grant-admin" | "elevate" | "elevate-force"
  | "dismiss-signup" | "ban-signup"
  | null;

function InfoRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-4 text-sm">
      <span className="w-28 shrink-0 text-muted-foreground">{label}</span>
      <span className="flex-1">{children}</span>
    </div>
  );
}

function Pill({ label, cls }: { label: string; cls: string }) {
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${cls}`}>
      {label}
    </span>
  );
}

function ConfirmInline({
  message,
  destructive,
  confirmLabel,
  onConfirm,
  onCancel,
  busy,
}: {
  message: string;
  destructive?: boolean;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  busy: boolean;
}) {
  return (
    <div className="flex w-full items-center gap-2 rounded-md border border-destructive/20 bg-destructive/5 px-3 py-2">
      <span className="shrink text-sm">{message}</span>
      <Button
        type="button"
        size="sm"
        variant={destructive ? "destructive" : "default"}
        disabled={busy}
        onClick={onConfirm}
      >
        {confirmLabel}
      </Button>
      <Button type="button" size="sm" variant="outline" className="ml-auto" onClick={onCancel}>
        Cancel
      </Button>
    </div>
  );
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function formatRelative(iso: string | null) {
  if (!iso) return "Never";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 2) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function UserDetailModal({ target, onClose }: Props) {
  const qc = useQueryClient();
  const { user: currentUser } = useAuth();
  const [confirming, setConfirming] = useState<Confirm>(null);
  const [elevateContent, setElevateContent] = useState<ElevateContentSummary | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ["admin", "users"] });
    qc.invalidateQueries({ queryKey: ["admin", "pending-signups"] });
  };

  const done = () => { invalidateAll(); onClose(); };
  const fail = (err: unknown) => {
    setActionError(err instanceof Error ? err.message : "Action failed");
    setConfirming(null);
    setElevateContent(null);
  };

  const userId = target.kind === "user" ? target.user.id : "";
  const signupId = target.kind === "pending" ? target.signup.id : "";

  const patch = useMutation({
    mutationFn: (body: { is_active?: boolean; is_admin?: boolean }) =>
      patchAdminUser(userId, body),
    onSuccess: done,
    onError: fail,
  });
  const ban = useMutation({ mutationFn: () => banUser(userId), onSuccess: done, onError: fail });
  const unban = useMutation({ mutationFn: () => unbanUser(userId), onSuccess: done, onError: fail });
  const del = useMutation({ mutationFn: () => deleteUser(userId), onSuccess: done, onError: fail });

  const handleElevate = async (force: boolean) => {
    setActionError(null);
    try {
      await elevateToSuperuser(userId, force);
      done();
    } catch (err) {
      try {
        const body = JSON.parse((err as Error).message);
        if (body?.detail?.code === "has_content") {
          setElevateContent(body.detail.summary);
          setConfirming("elevate-force");
          return;
        }
      } catch {}
      fail(err);
    }
  };

  const approve = useMutation({
    mutationFn: () => approvePendingSignup(signupId),
    onSuccess: done,
    onError: fail,
  });
  const dismissSignup = useMutation({
    mutationFn: () => dismissPendingSignup(signupId),
    onSuccess: done,
    onError: fail,
  });
  const banSignup = useMutation({
    mutationFn: () => banPendingSignup(signupId),
    onSuccess: done,
    onError: fail,
  });

  const busy =
    patch.isPending || ban.isPending || unban.isPending || del.isPending ||
    approve.isPending || dismissSignup.isPending || banSignup.isPending;

  // ── Pending signup ──────────────────────────────────────────────────────────

  if (target.kind === "pending") {
    const s = target.signup;
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
        <div className="w-full max-w-lg rounded-lg border bg-background shadow-lg flex flex-col">
          <div className="flex items-start justify-between px-6 pt-5 pb-4 border-b">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold">{s.display_name || s.email}</h2>
                <Pill label="pending" cls="bg-copper-subtle text-copper-on-subtle" />
              </div>
              <p className="text-sm text-muted-foreground overflow-hidden"><CopyEmail email={s.email} /></p>
            </div>
            <button
              onClick={onClose}
              className="text-xl leading-none text-muted-foreground hover:text-foreground"
            >
              ×
            </button>
          </div>

          <div className="px-6 py-4 space-y-4">
            <InfoRow label="Signed up">{formatDate(s.created_at)}</InfoRow>

            <div className="border-t pt-4 space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Actions</p>
              <Button size="sm" disabled={busy} onClick={() => approve.mutate()}>
                Add user
              </Button>
              {confirming === "dismiss-signup" ? (
                <ConfirmInline
                  message="Dismiss this signup request?"
                  confirmLabel="Dismiss"
                  onConfirm={() => dismissSignup.mutate()}
                  onCancel={() => setConfirming(null)}
                  busy={busy}
                />
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={() => setConfirming("dismiss-signup")}
                >
                  Dismiss
                </Button>
              )}
              {confirming === "ban-signup" ? (
                <ConfirmInline
                  message={`Ban ${s.display_name || s.email}?`}
                  destructive
                  confirmLabel="Ban"
                  onConfirm={() => banSignup.mutate()}
                  onCancel={() => setConfirming(null)}
                  busy={busy}
                />
              ) : (
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={busy}
                  onClick={() => setConfirming("ban-signup")}
                >
                  Ban
                </Button>
              )}
            </div>

            {actionError && (
              <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {actionError}
              </p>
            )}
          </div>

          <div className="flex justify-end px-6 py-4 border-t">
            <Button variant="outline" size="sm" onClick={onClose}>
              Close
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // ── Regular user ────────────────────────────────────────────────────────────

  const u = target.user;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-lg border bg-background shadow-lg flex flex-col max-h-[90vh]">
        <div className="flex items-start justify-between px-6 pt-5 pb-4 border-b">
          <div>
            <h2 className="text-base font-semibold">{u.display_name}</h2>
            <p className="text-sm text-muted-foreground overflow-hidden"><CopyEmail email={u.email} /></p>
          </div>
          <button
            onClick={onClose}
            className="text-xl leading-none text-muted-foreground hover:text-foreground"
          >
            ×
          </button>
        </div>

        <div className="overflow-y-auto flex-1 px-6 py-4 space-y-4">
          {/* Badges */}
          <div className="flex flex-wrap gap-1.5">
            {u.is_superuser && <Pill label="superuser" cls="border text-muted-foreground" />}
            {u.is_admin && !u.is_superuser && <Pill label="admin" cls="border text-muted-foreground" />}
            {u.clerk_errored && (
              <Pill label="errored" cls="border border-destructive text-destructive" />
            )}
            {u.deletion_state && (
              <Pill
                label={`deleting: ${u.deletion_state}`}
                cls="border border-amber-500 text-amber-600"
              />
            )}
            {!u.clerk_errored && !u.deletion_state && u.clerk_banned && (
              <Pill label="banned" cls="border border-destructive text-destructive" />
            )}
            {!u.clerk_errored && !u.deletion_state && !u.clerk_banned && !u.is_active && (
              <Pill label="inactive" cls="border border-destructive text-destructive" />
            )}
          </div>

          {/* Info */}
          <div className="space-y-1.5">
            <InfoRow label="Joined">{formatDate(u.created_at)}</InfoRow>
            <InfoRow label="Last login">{formatRelative(u.last_active_at)}</InfoRow>
            <InfoRow label="Storage">{formatBytes(u.counts.storage_bytes)}</InfoRow>
            <InfoRow label="Drafts">{u.counts.drafts}</InfoRow>
            <InfoRow label="Projects">
              {u.counts.projects_active} active, {u.counts.projects_completed} completed
            </InfoRow>
            <InfoRow label="Looms">{u.counts.looms}</InfoRow>
            {u.approved_by_name && (
              <InfoRow label="Approved by">
                {u.approved_by_name}
                {u.approved_by_email ? ` (${u.approved_by_email})` : ""}
              </InfoRow>
            )}
          </div>

          {/* Actions */}
          {!u.deletion_state && !u.is_superuser && (
            <div className="border-t pt-4 space-y-4">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Actions
              </p>

              {/* ── Role (superuser only) ───────────────────────────── */}
              {currentUser?.is_superuser && !u.clerk_errored && (
                <div className="inline-flex flex-col gap-2">
                  <p className="text-xs text-muted-foreground">Role</p>

                  {/* Grant / revoke admin */}
                  {confirming === "grant-admin" ? (
                    <ConfirmInline
                      message={
                        u.is_admin
                          ? `Remove admin rights from ${u.display_name}?`
                          : `Grant admin rights to ${u.display_name}?`
                      }
                      confirmLabel={u.is_admin ? "Remove admin" : "Grant admin"}
                      onConfirm={() => patch.mutate({ is_admin: !u.is_admin })}
                      onCancel={() => setConfirming(null)}
                      busy={busy}
                    />
                  ) : (
                    <Button
                      size="sm"
                      variant={u.is_admin ? "outline" : "default"}
                      className={u.is_admin ? "border-amber-400 text-amber-700 hover:bg-amber-50 hover:text-amber-800" : ""}
                      disabled={busy || u.clerk_banned}
                      onClick={() => setConfirming("grant-admin")}
                    >
                      {u.is_admin ? "Remove admin" : "Grant admin"}
                    </Button>
                  )}

                  {/* Elevate to superuser */}
                  {u.is_admin && (
                    confirming === "elevate" ? (
                      <ConfirmInline
                        message={`Make ${u.display_name} a superuser?`}
                        confirmLabel="Make superuser"
                        onConfirm={() => handleElevate(false)}
                        onCancel={() => setConfirming(null)}
                        busy={busy}
                      />
                    ) : confirming === "elevate-force" && elevateContent ? (
                      <ConfirmInline
                        message={`This user has ${[
                          elevateContent.projects && `${elevateContent.projects} projects`,
                          elevateContent.looms && `${elevateContent.looms} looms`,
                          elevateContent.drafts && `${elevateContent.drafts} drafts`,
                          elevateContent.yarn && `${elevateContent.yarn} yarn`,
                        ]
                          .filter(Boolean)
                          .join(", ")} — all content will be permanently deleted.`}
                        destructive
                        confirmLabel="Delete content & elevate"
                        onConfirm={() => handleElevate(true)}
                        onCancel={() => {
                          setConfirming(null);
                          setElevateContent(null);
                        }}
                        busy={busy}
                      />
                    ) : (
                      <Button
                        size="sm"
                        variant="default"
                        disabled={busy || u.clerk_banned}
                        onClick={() => setConfirming("elevate")}
                      >
                        Make superuser
                      </Button>
                    )
                  )}
                </div>
              )}

              {/* ── Account management ──────────────────────────────── */}
              {!u.clerk_errored && (
                <div className="inline-flex flex-col gap-2">
                  {currentUser?.is_superuser && (
                    <p className="text-xs text-muted-foreground">Account</p>
                  )}

                  {/* Deactivate / reactivate */}
                  {!u.clerk_banned && (
                    confirming === "deactivate" ? (
                      <ConfirmInline
                        message={`${u.is_active ? "Deactivate" : "Reactivate"} ${u.display_name}?`}
                        confirmLabel={u.is_active ? "Deactivate" : "Reactivate"}
                        onConfirm={() => patch.mutate({ is_active: !u.is_active })}
                        onCancel={() => setConfirming(null)}
                        busy={busy}
                      />
                    ) : (
                      <Button
                        size="sm"
                        variant={u.is_active ? "outline" : "default"}
                        className={
                          u.is_active
                            ? "border-amber-400 text-amber-700 hover:bg-amber-50 hover:text-amber-800"
                            : "bg-green-600 hover:bg-green-700"
                        }
                        disabled={busy || (u.is_active && u.is_admin)}
                        title={
                          u.is_active && u.is_admin
                            ? "Remove admin rights before deactivating"
                            : undefined
                        }
                        onClick={() => setConfirming("deactivate")}
                      >
                        {u.is_active ? "Deactivate" : "Reactivate"}
                      </Button>
                    )
                  )}

                  {/* Ban / unban */}
                  {u.clerk_banned ? (
                    <Button
                      size="sm"
                      variant="default"
                      className="bg-green-600 hover:bg-green-700"
                      disabled={busy}
                      onClick={() => unban.mutate()}
                    >
                      Unban
                    </Button>
                  ) : confirming === "ban" ? (
                    <ConfirmInline
                      message={`Ban ${u.display_name}?`}
                      destructive
                      confirmLabel="Ban"
                      onConfirm={() => ban.mutate()}
                      onCancel={() => setConfirming(null)}
                      busy={busy}
                    />
                  ) : (
                    <Button
                      size="sm"
                      variant="destructive"
                      disabled={busy || u.is_admin}
                      title={u.is_admin ? "Remove admin rights before banning" : undefined}
                      onClick={() => setConfirming("ban")}
                    >
                      Ban
                    </Button>
                  )}

                  {/* Delete (superuser only) */}
                  {currentUser?.is_superuser && (
                    confirming === "delete" ? (
                      <ConfirmInline
                        message={`Delete ${u.display_name}? All data and S3 storage will be permanently removed.`}
                        destructive
                        confirmLabel="Delete"
                        onConfirm={() => del.mutate()}
                        onCancel={() => setConfirming(null)}
                        busy={busy}
                      />
                    ) : (
                      <Button
                        size="sm"
                        variant="destructive"
                        className=""
                        disabled={busy}
                        onClick={() => setConfirming("delete")}
                      >
                        Delete user
                      </Button>
                    )
                  )}
                </div>
              )}
            </div>
          )}

          {actionError && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {actionError}
            </p>
          )}
        </div>

        <div className="flex justify-end px-6 py-4 border-t">
          <Button variant="outline" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}
