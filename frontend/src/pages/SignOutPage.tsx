import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth as useClerkAuth, useClerk } from "@clerk/clerk-react";

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
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="space-y-2 text-center">
        <h1 className="text-xl font-semibold">WeftMark</h1>
        {!isLoaded || isSignedIn ? (
          <p className="text-sm text-muted-foreground">Signing you out…</p>
        ) : (
          <p className="text-sm text-muted-foreground">You have been signed out. Redirecting…</p>
        )}
      </div>
    </div>
  );
}
