import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";

export function LoginPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const inviteToken = searchParams.get("token");
  const error = searchParams.get("error");

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      navigate("/", { replace: true });
    }
  }, [isAuthenticated, isLoading, navigate]);

  const handleLogin = () => {
    const url = inviteToken ? `/auth/login?invite_token=${inviteToken}` : "/auth/login";
    window.location.href = url;
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="w-full max-w-sm space-y-6 px-4">
        <div className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">WeftMark</h1>
          {inviteToken ? (
            <p className="text-sm text-muted-foreground">
              You've been invited. Sign in to accept your invitation.
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">Sign in to continue</p>
          )}
        </div>

        {error === "invite_required" && (
          <p className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
            An invitation is required to create an account.
          </p>
        )}

        <Button className="w-full" onClick={handleLogin} disabled={isLoading}>
          Sign in with Authentik
        </Button>
      </div>
    </div>
  );
}
