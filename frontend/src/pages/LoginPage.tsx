import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { SignIn, useAuth as useClerkAuth, useClerk, useUser } from "@clerk/clerk-react";
import { useAuth } from "@/hooks/useAuth";

export function LoginPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const { isSignedIn, isLoaded: clerkLoaded } = useClerkAuth();
  const { user: clerkUser } = useUser();
  const { signOut } = useClerk();
  const clerkStatus = clerkUser?.publicMetadata?.status as string | undefined;
  const navigate = useNavigate();

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      navigate("/", { replace: true });
    }
  }, [isAuthenticated, isLoading, navigate]);

  // Clerk-authenticated but no DB record — show a holding page instead of looping.
  if (clerkLoaded && isSignedIn && !isLoading && !isAuthenticated) {
    const isDenied = clerkStatus === "denied";
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="w-full max-w-sm space-y-4 px-4 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">WeftMark</h1>
          {isDenied ? (
            <p className="text-sm text-muted-foreground">
              WeftMark is currently closed to new sign-ups, but your interest has been noted. We'll be in touch if that changes.
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              WeftMark is currently invite only. Admins have been notified of your sign-up request.
            </p>
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

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="w-full max-w-sm space-y-6 px-4">
        <div className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">WeftMark</h1>
          <p className="text-sm text-muted-foreground">Sign in to continue</p>
        </div>
        <SignIn
          routing="hash"
          signUpUrl="/register"
          fallbackRedirectUrl="/"
          appearance={{
            elements: {
              rootBox: "w-full",
              card: "shadow-none border rounded-lg p-6 bg-card",
              headerTitle: "hidden",
              headerSubtitle: "hidden",
            },
          }}
        />
      </div>
    </div>
  );
}
