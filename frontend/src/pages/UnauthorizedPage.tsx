import { Link } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";

export function UnauthorizedPage() {
  const { isAuthenticated } = useAuth();

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="max-w-sm space-y-4 px-4 text-center">
        <h1 className="text-2xl font-semibold">Access denied</h1>
        <p className="text-sm text-muted-foreground">
          You don't have permission to view this page.
        </p>
        <Link
          to={isAuthenticated ? "/home" : "/login"}
          className="inline-block text-sm underline underline-offset-2 text-muted-foreground hover:text-foreground"
        >
          {isAuthenticated ? "Back to home" : "Sign in"}
        </Link>
      </div>
    </div>
  );
}
