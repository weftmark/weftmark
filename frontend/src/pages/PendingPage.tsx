import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth as useClerkAuth, useClerk, useUser } from "@clerk/clerk-react";
import { useAuth } from "@/hooks/useAuth";

const MAX_POLLS = 10;
const POLL_INTERVAL_MS = 3000;

export function PendingPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const { isSignedIn, isLoaded: clerkLoaded } = useClerkAuth();
  const { user: clerkUser } = useUser();
  const { signOut } = useClerk();
  const navigate = useNavigate();

  const [pollCount, setPollCount] = useState(0);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clerkStatus = clerkUser?.publicMetadata?.status as string | undefined;

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      navigate("/home", { replace: true });
    }
  }, [isAuthenticated, isLoading, navigate]);

  useEffect(() => {
    if (clerkLoaded && !isSignedIn) {
      navigate("/login", { replace: true });
    }
  }, [clerkLoaded, isSignedIn, navigate]);

  // Poll clerkUser.reload() until the webhook fires and sets status
  useEffect(() => {
    if (!clerkLoaded || !isSignedIn || !clerkUser) return;
    if (clerkStatus !== undefined) return;
    if (pollCount >= MAX_POLLS) return;

    pollTimer.current = setTimeout(async () => {
      await clerkUser.reload();
      setPollCount((c) => c + 1);
    }, POLL_INTERVAL_MS);

    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [clerkLoaded, isSignedIn, clerkUser, clerkStatus, pollCount]);

  if (!clerkLoaded || isLoading || (clerkStatus === undefined && pollCount < MAX_POLLS)) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="w-full max-w-sm space-y-4 px-4 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">WeftMark</h1>
          <p className="text-sm text-muted-foreground">Setting up your account…</p>
        </div>
      </div>
    );
  }

  const isDenied = clerkStatus === "denied" || clerkStatus === "banned";

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="w-full max-w-sm space-y-4 px-4 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">WeftMark</h1>
        {isDenied ? (
          <p className="text-sm text-muted-foreground">
            WeftMark is currently closed to new sign-ups, but your interest has been noted. We'll be in touch if that changes.
          </p>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              Your sign-up request has been received. You'll get an email when an admin approves your account.
            </p>
            <p className="text-xs text-muted-foreground">No action needed — sit tight.</p>
          </>
        )}
        <button
          onClick={() => signOut()}
          className="text-sm underline underline-offset-2 text-muted-foreground hover:text-foreground"
        >
          Sign out
        </button>
      </div>
    </div>
  );
}
