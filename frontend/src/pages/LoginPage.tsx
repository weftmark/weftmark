import { useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { SignIn, useAuth as useClerkAuth, useClerk, useUser } from "@clerk/clerk-react";
import { useAuth } from "@/hooks/useAuth";
import { AuthCard } from "@/components/auth/AuthCard";

const CLERK_APPEARANCE = {
  variables: {
    colorPrimary: "#27272a",
    colorBackground: "#ffffff",
    colorInputBackground: "#fafaf9",
    colorText: "#1c1917",
    colorTextSecondary: "#57534e",
    borderRadius: "0.5rem",
  },
  elements: {
    headerTitle: "hidden",
    headerSubtitle: "hidden",
  },
};

export function LoginPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const { isSignedIn, isLoaded: clerkLoaded } = useClerkAuth();
  const { user: clerkUser } = useUser();
  const { signOut } = useClerk();
  const clerkStatus = clerkUser?.publicMetadata?.status as string | undefined;
  const navigate = useNavigate();

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      navigate("/home", { replace: true });
    }
  }, [isAuthenticated, isLoading, navigate]);

  useEffect(() => {
    if (clerkLoaded && isSignedIn && !isLoading && !isAuthenticated && clerkStatus === "pending_signup") {
      navigate("/pending", { replace: true });
    }
  }, [clerkLoaded, isSignedIn, isLoading, isAuthenticated, clerkStatus, navigate]);

  // Clerk-authenticated but WeftMark hasn't approved the account
  if (clerkLoaded && isSignedIn && !isLoading && !isAuthenticated && clerkStatus !== "pending_signup") {
    const isDenied = clerkStatus === "denied" || clerkStatus === "banned";
    return (
      <AuthCard>
        <div className="text-center">
          {isDenied ? (
            <div className="mx-auto mb-4 flex h-10 w-10 items-center justify-center rounded-full bg-stone-100">
              <svg className="h-5 w-5 text-stone-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
              </svg>
            </div>
          ) : (
            <div className="mx-auto mb-4 flex h-10 w-10 items-center justify-center rounded-full bg-amber-50">
              <svg className="h-5 w-5 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6l4 2m6-2a10 10 0 11-20 0 10 10 0 0120 0z" />
              </svg>
            </div>
          )}
          <h1 className="text-lg font-semibold text-zinc-800">
            {isDenied ? "Account not approved" : "Approval pending"}
          </h1>
          <p className="mt-2 text-sm text-stone-600">
            {isDenied
              ? "weftmark is currently closed to new sign-ups, but your interest has been noted. We'll be in touch if that changes."
              : "Your sign-up request has been received. You'll get an email when an admin approves your account."}
          </p>
          <button
            onClick={() => signOut()}
            className="mt-6 text-sm text-stone-500 underline underline-offset-2 hover:text-stone-700"
          >
            Sign out
          </button>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      naked
      footer={
        <>
          New to weftmark?{" "}
          <Link to="/register" className="text-amber-700 underline underline-offset-2 hover:text-amber-800">
            Request access
          </Link>
        </>
      }
    >
      <div className="mb-5 text-center">
        <h1 className="text-lg font-semibold text-zinc-800">Sign in</h1>
        <p className="mt-1 text-sm text-stone-600">Welcome back</p>
      </div>
      <SignIn routing="hash" appearance={CLERK_APPEARANCE} />
    </AuthCard>
  );
}
