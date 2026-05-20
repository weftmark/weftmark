import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth as useClerkAuth, useClerk, useUser } from "@clerk/clerk-react";
import { useAuth } from "@/hooks/useAuth";
import { AuthCard } from "@/components/auth/AuthCard";

const MAX_POLLS = 10;
const POLL_INTERVAL_MS = 3000;

export function PendingPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const { isSignedIn, isLoaded: clerkLoaded } = useClerkAuth();
  const { user: clerkUser } = useUser();
  const { signOut } = useClerk();
  const navigate = useNavigate();
  const { t } = useTranslation();

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
      <AuthCard>
        <div className="text-center">
          <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-stone-200 border-t-zinc-800" />
          <h1 className="text-lg font-semibold text-zinc-800">{t("pendingPage.settingUp")}</h1>
          <p className="mt-2 text-sm text-stone-600">{t("pendingPage.justAMoment")}</p>
        </div>
      </AuthCard>
    );
  }

  const isDenied = clerkStatus === "denied" || clerkStatus === "banned";

  return (
    <AuthCard>
      <div className="text-center">
        {isDenied ? (
          <>
            <div className="mx-auto mb-4 flex h-10 w-10 items-center justify-center rounded-full bg-stone-100">
              <svg
                className="h-5 w-5 text-stone-500"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1.75}
                aria-hidden="true"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
              </svg>
            </div>
            <h1 className="text-lg font-semibold text-zinc-800">{t("pendingPage.accountNotApproved")}</h1>
            <p className="mt-2 text-sm text-stone-600">{t("pendingPage.deniedMessage")}</p>
          </>
        ) : (
          <>
            <div className="mx-auto mb-4 flex h-10 w-10 items-center justify-center rounded-full bg-amber-50">
              <svg
                className="h-5 w-5 text-amber-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1.75}
                aria-hidden="true"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6l4 2m6-2a10 10 0 11-20 0 10 10 0 0120 0z" />
              </svg>
            </div>
            <h1 className="text-lg font-semibold text-zinc-800">{t("pendingPage.requestReceived")}</h1>
            <p className="mt-2 text-sm text-stone-600">{t("pendingPage.submittedMessage")}</p>
            <p className="mt-3 text-xs text-stone-500">{t("pendingPage.noAction")}</p>
          </>
        )}
        <button
          onClick={() => signOut()}
          className="mt-6 text-sm text-stone-500 underline underline-offset-2 hover:text-stone-700"
        >
          {t("pendingPage.signOut")}
        </button>
      </div>
    </AuthCard>
  );
}
