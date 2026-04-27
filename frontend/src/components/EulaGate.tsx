import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { acceptEula, deleteAccount } from "@/api/users";
import { Button } from "@/components/ui/button";
import { EulaContent } from "@/components/EulaContent";
import type { ReactNode } from "react";

interface Props {
  children: ReactNode;
}

export function EulaGate({ children }: Props) {
  const { user, isLoading, refetch } = useAuth();
  const [accepting, setAccepting] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (isLoading || !user) return <>{children}</>;

  const eulaRequired = user.eula_accepted_version !== user.current_eula_version;
  if (!eulaRequired) return <>{children}</>;

  const isNewUser = user.eula_accepted_version === null;

  async function handleAccept() {
    if (!user) return;
    setAccepting(true);
    setError(null);
    try {
      await acceptEula(user.current_eula_version);
      refetch();
    } catch {
      setError("Failed to record acceptance. Please try again.");
    } finally {
      setAccepting(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    setError(null);
    try {
      await deleteAccount("DELETE MY ACCOUNT");
      window.location.href = "/login";
    } catch {
      setError("Failed to delete account. Please try again or contact support.");
      setDeleting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-start justify-center bg-background py-8 px-4">
      <div className="w-full max-w-2xl space-y-6">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">WeftMark Terms of Service</h1>
          <p className="text-sm text-muted-foreground">
            {isNewUser
              ? "Please read and accept the Terms of Service to continue."
              : "The Terms of Service have been updated. Please review and accept to continue."}
          </p>
        </div>

        <div className="rounded-lg border bg-card p-6 max-h-[60vh] overflow-y-auto">
          <EulaContent />
        </div>

        {error && (
          <p className="rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">{error}</p>
        )}

        <div className="flex flex-col gap-3">
          <Button onClick={handleAccept} disabled={accepting} className="w-full">
            {accepting ? "Recording acceptance…" : "I Accept the Terms of Service"}
          </Button>

          {!showDelete ? (
            <Button
              variant="ghost"
              className="w-full text-muted-foreground text-sm"
              onClick={() => setShowDelete(true)}
            >
              I do not accept
            </Button>
          ) : (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 space-y-3">
              <p className="text-sm font-medium text-destructive">Delete your account</p>
              <p className="text-sm text-muted-foreground">
                If you do not accept the Terms of Service, you may delete your account. This will
                permanently remove all your WIF files, photos, activity records, looms, yarn, and
                projects. This cannot be undone.
              </p>
              <div className="flex gap-2">
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={handleDelete}
                  disabled={deleting}
                >
                  {deleting ? "Deleting…" : "Permanently delete my account"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowDelete(false)}
                  disabled={deleting}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>

        <p className="text-center text-xs text-muted-foreground">
          WeftMark v{user.current_eula_version} Terms of Service
        </p>
      </div>
    </div>
  );
}
