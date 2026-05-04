import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth as useClerkAuth, useClerk } from "@clerk/clerk-react";
import { AuthCard } from "@/components/auth/AuthCard";

export function SignOutPage() {
  const { isSignedIn, isLoaded } = useClerkAuth();
  const { signOut } = useClerk();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isLoaded) return;
    if (isSignedIn) {
      signOut();
    } else {
      const timer = setTimeout(() => navigate("/", { replace: true }), 2000);
      return () => clearTimeout(timer);
    }
  }, [isLoaded, isSignedIn, signOut, navigate]);

  return (
    <AuthCard>
      <div className="text-center">
        {!isLoaded || isSignedIn ? (
          <>
            <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-stone-200 border-t-zinc-800" />
            <h1 className="text-lg font-semibold text-zinc-800">Signing you out</h1>
            <p className="mt-2 text-sm text-stone-600">Just a moment…</p>
          </>
        ) : (
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
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12h15m0 0l-6.75-6.75M19.5 12l-6.75 6.75" />
              </svg>
            </div>
            <h1 className="text-lg font-semibold text-zinc-800">You've been signed out</h1>
            <p className="mt-2 text-sm text-stone-600">Redirecting you to the home page…</p>
          </>
        )}
      </div>
    </AuthCard>
  );
}
