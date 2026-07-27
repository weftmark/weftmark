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
  readonly target: UserDetailTarget;
  readonly onClose: () => void;
}

type Confirm =
  | "deactivate" | "ban" | "delete" | "grant-admin" | "elevate" | "elevate-force"
  | "dismiss-signup" | "ban-signup"
  | null;

type CurrentUser = ReturnType<typeof useAuth>["user"];

function InfoRow({ label, children }: { readonly label: string; readonly children: ReactNode }) {
  return (
    <div className="flex gap-4 text-sm">
      <span className="w-28 shrink-0 text-muted-foreground">{label}</span>
      <span className="flex-1">{children}</span>
    </div>
  );
}

function Pill({ label, cls }: { readonly label: string; readonly cls: string }) {
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
  readonly message: string;
  readonly destructive?: boolean;
  readonly confirmLabel: string;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
  readonly busy: boolean;
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

function formatDateTime(iso: string | null) {
  if (!iso) return "Never";
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

// ── Pending signup ────────────────────────────────────────────────────────

function PendingSignupView({
  signup,
  onClose,
  busy,
  confirming,
  setConfirming,
  onApprove,
  onDismiss,
  onBan,
  actionError,
}: {
  readonly signup: PendingSignup;
  readonly onClose: () => void;
  readonly busy: boolean;
  readonly confirming: Confirm;
  readonly setConfirming: (c: Confirm) => void;
  readonly onApprove: () => void;
  readonly onDismiss: () => void;
  readonly onBan: () => void;
  readonly actionError: string | null;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-lg border bg-background shadow-lg flex flex-col">
        <div className="flex items-start justify-between px-6 pt-5 pb-4 border-b">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold">{signup.display_name || signup.email}</h2>
              <Pill label="pending" cls="bg-copper-subtle text-copper-on-subtle" />
            </div>
            <p className="text-sm text-muted-foreground overflow-hidden"><CopyEmail email={signup.email} /></p>
          </div>
          <button type="button"
            onClick={onClose}
            className="text-xl leading-none text-muted-foreground hover:text-foreground"
          >
            ×
          </button>
        </div>

        <div className="px-6 py-4 space-y-4">
          <InfoRow label="Signed up">{formatDate(signup.created_at)}</InfoRow>

          <div className="border-t pt-4 space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Actions</p>
            <Button size="sm" disabled={busy} onClick={onApprove}>
              Add user
            </Button>
            {confirming === "dismiss-signup" ? (
              <ConfirmInline
                message="Dismiss this signup request?"
                confirmLabel="Dismiss"
                onConfirm={onDismiss}
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
                message={`Ban ${signup.display_name || signup.email}?`}
                destructive
                confirmLabel="Ban"
                onConfirm={onBan}
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

// ── Regular user ─────────────────────────────────────────────────────────

function ElevateControls({
  confirming,
  elevateContent,
  user,
  busy,
  onStart,
  onConfirm,
  onConfirmForce,
  onCancel,
  onCancelForce,
}: {
  readonly confirming: Confirm;
  readonly elevateContent: ElevateContentSummary | null;
  readonly user: AdminUser;
  readonly busy: boolean;
  readonly onStart: () => void;
  readonly onConfirm: () => void;
  readonly onConfirmForce: () => void;
  readonly onCancel: () => void;
  readonly onCancelForce: () => void;
}) {
  if (confirming === "elevate") {
    return (
      <ConfirmInline
        message={`Make ${user.display_name} a superuser?`}
        confirmLabel="Make superuser"
        onConfirm={onConfirm}
        onCancel={onCancel}
        busy={busy}
      />
    );
  }
  if (confirming === "elevate-force" && elevateContent) {
    return (
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
        onConfirm={onConfirmForce}
        onCancel={onCancelForce}
        busy={busy}
      />
    );
  }
  return (
    <Button
      size="sm"
      variant="default"
      disabled={busy || user.clerk_banned}
      onClick={onStart}
    >
      Make superuser
    </Button>
  );
}

function StorageQuotaBar({ used, quota }: { readonly used: number; readonly quota: number }) {
  const pct = Math.min(Math.round((used / quota) * 100), 100);
  let barColor = "bg-primary";
  if (pct >= 90) barColor = "bg-red-500";
  else if (pct >= 75) barColor = "bg-amber-500";
  return (
    <>
      <div className="flex justify-between mb-1">
        <span>{formatBytes(used)}</span>
        <span className="text-muted-foreground">{formatBytes(quota)} · {pct}%</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
    </>
  );
}

function UserBadges({ user }: { readonly user: AdminUser }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {user.is_superuser && <Pill label="superuser" cls="border text-muted-foreground" />}
      {user.is_admin && !user.is_superuser && <Pill label="admin" cls="border text-muted-foreground" />}
      {user.clerk_errored && (
        <Pill label="errored" cls="border border-destructive text-destructive" />
      )}
      {user.deletion_state && (
        <Pill
          label={`deleting: ${user.deletion_state}`}
          cls="border border-amber-500 text-amber-600"
        />
      )}
      {!user.clerk_errored && !user.deletion_state && user.clerk_banned && (
        <Pill label="banned" cls="border border-destructive text-destructive" />
      )}
      {!user.clerk_errored && !user.deletion_state && !user.clerk_banned && !user.is_active && (
        <Pill label="inactive" cls="border border-destructive text-destructive" />
      )}
    </div>
  );
}

function UserInfoSection({ user }: { readonly user: AdminUser }) {
  return (
    <div className="space-y-1.5">
      <InfoRow label="Joined">{formatDate(user.created_at)}</InfoRow>
      <InfoRow label="Last login">{formatDateTime(user.last_active_at)}</InfoRow>
      <div className="flex gap-4 text-sm">
        <span className="w-28 shrink-0 text-muted-foreground">Storage</span>
        <div className="flex-1">
          <StorageQuotaBar used={user.counts.storage_bytes} quota={user.counts.storage_quota_bytes} />
        </div>
      </div>
      <InfoRow label="Drafts">{user.counts.drafts}</InfoRow>
      <InfoRow label="Projects">
        {user.counts.projects_active} active, {user.counts.projects_completed} completed
      </InfoRow>
      <InfoRow label="Looms">{user.counts.looms}</InfoRow>
      {user.approved_by_name && (
        <InfoRow label="Approved by">
          {user.approved_by_name}
          {user.approved_by_email ? ` (${user.approved_by_email})` : ""}
        </InfoRow>
      )}
      <InfoRow label="EULA">
        {user.eula_accepted_version
          ? `v${user.eula_accepted_version} · ${formatDateTime(user.eula_accepted_at)}`
          : <span className="text-muted-foreground">Not accepted</span>}
      </InfoRow>
    </div>
  );
}

function RoleActions({
  user,
  confirming,
  setConfirming,
  busy,
  onGrantAdmin,
  elevateControls,
}: {
  readonly user: AdminUser;
  readonly confirming: Confirm;
  readonly setConfirming: (c: Confirm) => void;
  readonly busy: boolean;
  readonly onGrantAdmin: () => void;
  readonly elevateControls: ReactNode;
}) {
  return (
    <div className="inline-flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">Role</p>

      {confirming === "grant-admin" ? (
        <ConfirmInline
          message={
            user.is_admin
              ? `Remove admin rights from ${user.display_name}?`
              : `Grant admin rights to ${user.display_name}?`
          }
          confirmLabel={user.is_admin ? "Remove admin" : "Grant admin"}
          onConfirm={onGrantAdmin}
          onCancel={() => setConfirming(null)}
          busy={busy}
        />
      ) : (
        <Button
          size="sm"
          variant={user.is_admin ? "outline" : "default"}
          className={user.is_admin ? "border-amber-400 text-amber-700 hover:bg-amber-50 hover:text-amber-800" : ""}
          disabled={busy || user.clerk_banned}
          onClick={() => setConfirming("grant-admin")}
        >
          {user.is_admin ? "Remove admin" : "Grant admin"}
        </Button>
      )}

      {user.is_admin && elevateControls}
    </div>
  );
}

function DeactivateReactivateAction({
  user,
  confirming,
  setConfirming,
  busy,
  deactivateBtnClass,
  onDeactivate,
}: {
  readonly user: AdminUser;
  readonly confirming: Confirm;
  readonly setConfirming: (c: Confirm) => void;
  readonly busy: boolean;
  readonly deactivateBtnClass: string;
  readonly onDeactivate: () => void;
}) {
  if (user.clerk_banned) return null;

  if (confirming === "deactivate") {
    return (
      <ConfirmInline
        message={`${user.is_active ? "Deactivate" : "Reactivate"} ${user.display_name}?`}
        confirmLabel={user.is_active ? "Deactivate" : "Reactivate"}
        onConfirm={onDeactivate}
        onCancel={() => setConfirming(null)}
        busy={busy}
      />
    );
  }

  return (
    <Button
      size="sm"
      variant={user.is_active ? "outline" : "default"}
      className={deactivateBtnClass}
      disabled={busy || (user.is_active && user.is_admin)}
      title={
        user.is_active && user.is_admin
          ? "Remove admin rights before deactivating"
          : undefined
      }
      onClick={() => setConfirming("deactivate")}
    >
      {user.is_active ? "Deactivate" : "Reactivate"}
    </Button>
  );
}

function BanUnbanAction({
  user,
  confirming,
  setConfirming,
  busy,
  onBan,
  onUnban,
}: {
  readonly user: AdminUser;
  readonly confirming: Confirm;
  readonly setConfirming: (c: Confirm) => void;
  readonly busy: boolean;
  readonly onBan: () => void;
  readonly onUnban: () => void;
}) {
  if (user.clerk_banned) {
    return (
      <Button
        size="sm"
        variant="default"
        className="bg-green-600 hover:bg-green-700"
        disabled={busy}
        onClick={onUnban}
      >
        Unban
      </Button>
    );
  }

  if (confirming === "ban") {
    return (
      <ConfirmInline
        message={`Ban ${user.display_name}?`}
        destructive
        confirmLabel="Ban"
        onConfirm={onBan}
        onCancel={() => setConfirming(null)}
        busy={busy}
      />
    );
  }

  return (
    <Button
      size="sm"
      variant="destructive"
      disabled={busy || user.is_admin}
      title={user.is_admin ? "Remove admin rights before banning" : undefined}
      onClick={() => setConfirming("ban")}
    >
      Ban
    </Button>
  );
}

function DeleteAction({
  user,
  confirming,
  setConfirming,
  busy,
  onDelete,
}: {
  readonly user: AdminUser;
  readonly confirming: Confirm;
  readonly setConfirming: (c: Confirm) => void;
  readonly busy: boolean;
  readonly onDelete: () => void;
}) {
  if (confirming === "delete") {
    return (
      <ConfirmInline
        message={`Delete ${user.display_name}? All data and S3 storage will be permanently removed.`}
        destructive
        confirmLabel="Delete"
        onConfirm={onDelete}
        onCancel={() => setConfirming(null)}
        busy={busy}
      />
    );
  }

  return (
    <Button
      size="sm"
      variant="destructive"
      className=""
      disabled={busy}
      onClick={() => setConfirming("delete")}
    >
      Delete user
    </Button>
  );
}

function AccountActions({
  user,
  currentUserIsSuperuser,
  confirming,
  setConfirming,
  busy,
  deactivateBtnClass,
  onDeactivate,
  onBan,
  onUnban,
  onDelete,
}: {
  readonly user: AdminUser;
  readonly currentUserIsSuperuser: boolean;
  readonly confirming: Confirm;
  readonly setConfirming: (c: Confirm) => void;
  readonly busy: boolean;
  readonly deactivateBtnClass: string;
  readonly onDeactivate: () => void;
  readonly onBan: () => void;
  readonly onUnban: () => void;
  readonly onDelete: () => void;
}) {
  return (
    <div className="inline-flex flex-col gap-2">
      {currentUserIsSuperuser && (
        <p className="text-xs text-muted-foreground">Account</p>
      )}

      <DeactivateReactivateAction
        user={user}
        confirming={confirming}
        setConfirming={setConfirming}
        busy={busy}
        deactivateBtnClass={deactivateBtnClass}
        onDeactivate={onDeactivate}
      />

      <BanUnbanAction
        user={user}
        confirming={confirming}
        setConfirming={setConfirming}
        busy={busy}
        onBan={onBan}
        onUnban={onUnban}
      />

      {currentUserIsSuperuser && (
        <DeleteAction
          user={user}
          confirming={confirming}
          setConfirming={setConfirming}
          busy={busy}
          onDelete={onDelete}
        />
      )}
    </div>
  );
}

function UserActionsSection({
  user,
  currentUser,
  confirming,
  setConfirming,
  busy,
  elevateControls,
  deactivateBtnClass,
  onGrantAdmin,
  onDeactivate,
  onBan,
  onUnban,
  onDelete,
}: {
  readonly user: AdminUser;
  readonly currentUser: CurrentUser;
  readonly confirming: Confirm;
  readonly setConfirming: (c: Confirm) => void;
  readonly busy: boolean;
  readonly elevateControls: ReactNode;
  readonly deactivateBtnClass: string;
  readonly onGrantAdmin: () => void;
  readonly onDeactivate: () => void;
  readonly onBan: () => void;
  readonly onUnban: () => void;
  readonly onDelete: () => void;
}) {
  if (user.deletion_state || user.is_superuser) return null;

  return (
    <div className="border-t pt-4 space-y-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Actions
      </p>

      {currentUser?.is_superuser && !user.clerk_errored && (
        <RoleActions
          user={user}
          confirming={confirming}
          setConfirming={setConfirming}
          busy={busy}
          onGrantAdmin={onGrantAdmin}
          elevateControls={elevateControls}
        />
      )}

      {!user.clerk_errored && (
        <AccountActions
          user={user}
          currentUserIsSuperuser={!!currentUser?.is_superuser}
          confirming={confirming}
          setConfirming={setConfirming}
          busy={busy}
          deactivateBtnClass={deactivateBtnClass}
          onDeactivate={onDeactivate}
          onBan={onBan}
          onUnban={onUnban}
          onDelete={onDelete}
        />
      )}
    </div>
  );
}

function RegularUserView({
  user,
  currentUser,
  onClose,
  busy,
  confirming,
  setConfirming,
  elevateControls,
  deactivateBtnClass,
  onGrantAdmin,
  onDeactivate,
  onBan,
  onUnban,
  onDelete,
  actionError,
}: {
  readonly user: AdminUser;
  readonly currentUser: CurrentUser;
  readonly onClose: () => void;
  readonly busy: boolean;
  readonly confirming: Confirm;
  readonly setConfirming: (c: Confirm) => void;
  readonly elevateControls: ReactNode;
  readonly deactivateBtnClass: string;
  readonly onGrantAdmin: () => void;
  readonly onDeactivate: () => void;
  readonly onBan: () => void;
  readonly onUnban: () => void;
  readonly onDelete: () => void;
  readonly actionError: string | null;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-lg border bg-background shadow-lg flex flex-col max-h-[90vh]">
        <div className="flex items-start justify-between px-6 pt-5 pb-4 border-b">
          <div>
            <h2 className="text-base font-semibold">{user.display_name}</h2>
            <p className="text-sm text-muted-foreground overflow-hidden"><CopyEmail email={user.email} /></p>
          </div>
          <button type="button"
            onClick={onClose}
            className="text-xl leading-none text-muted-foreground hover:text-foreground"
          >
            ×
          </button>
        </div>

        <div className="overflow-y-auto flex-1 px-6 py-4 space-y-4">
          <UserBadges user={user} />
          <UserInfoSection user={user} />
          <UserActionsSection
            user={user}
            currentUser={currentUser}
            confirming={confirming}
            setConfirming={setConfirming}
            busy={busy}
            elevateControls={elevateControls}
            deactivateBtnClass={deactivateBtnClass}
            onGrantAdmin={onGrantAdmin}
            onDeactivate={onDeactivate}
            onBan={onBan}
            onUnban={onUnban}
            onDelete={onDelete}
          />

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

  if (target.kind === "pending") {
    const s = target.signup;
    return (
      <PendingSignupView
        signup={s}
        onClose={onClose}
        busy={busy}
        confirming={confirming}
        setConfirming={setConfirming}
        onApprove={() => approve.mutate()}
        onDismiss={() => dismissSignup.mutate()}
        onBan={() => banSignup.mutate()}
        actionError={actionError}
      />
    );
  }

  const u = target.user;

  const deactivateBtnClass = u.is_active
    ? "border-amber-400 text-amber-700 hover:bg-amber-50 hover:text-amber-800"
    : "bg-green-600 hover:bg-green-700";

  const elevateControls = (
    <ElevateControls
      confirming={confirming}
      elevateContent={elevateContent}
      user={u}
      busy={busy}
      onStart={() => setConfirming("elevate")}
      onConfirm={() => handleElevate(false)}
      onConfirmForce={() => handleElevate(true)}
      onCancel={() => setConfirming(null)}
      onCancelForce={() => {
        setConfirming(null);
        setElevateContent(null);
      }}
    />
  );

  return (
    <RegularUserView
      user={u}
      currentUser={currentUser}
      onClose={onClose}
      busy={busy}
      confirming={confirming}
      setConfirming={setConfirming}
      elevateControls={elevateControls}
      deactivateBtnClass={deactivateBtnClass}
      onGrantAdmin={() => patch.mutate({ is_admin: !u.is_admin })}
      onDeactivate={() => patch.mutate({ is_active: !u.is_active })}
      onBan={() => ban.mutate()}
      onUnban={() => unban.mutate()}
      onDelete={() => del.mutate()}
      actionError={actionError}
    />
  );
}
