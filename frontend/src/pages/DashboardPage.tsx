import { useAuth } from "@/hooks/useAuth";
import { api } from "@/api/client";
import { useNavigate, Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

export function DashboardPage() {
  const { user, refetch } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await api.post("/auth/logout");
    refetch();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b px-6 py-4 flex items-center justify-between">
        <span className="font-semibold">Weaving Site</span>
        <div className="flex items-center gap-4">
          <span className="text-sm text-muted-foreground">{user?.email}</span>
          <Button variant="outline" size="sm" onClick={handleLogout}>
            Sign out
          </Button>
        </div>
      </header>

      <main className="flex-1 p-6 max-w-4xl mx-auto w-full">
        <h2 className="text-xl font-semibold">Dashboard</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Welcome, {user?.display_name}.
        </p>
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <Link
            to="/projects"
            className="rounded-lg border p-5 hover:border-ring transition-colors"
          >
            <h3 className="font-medium">Projects</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Upload and manage your WIF design files.
            </p>
          </Link>
          <Link
            to="/looms"
            className="rounded-lg border p-5 hover:border-ring transition-colors"
          >
            <h3 className="font-medium">Equipment</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Manage your looms and configuration history.
            </p>
          </Link>
          <Link
            to="/yarn"
            className="rounded-lg border p-5 hover:border-ring transition-colors"
          >
            <h3 className="font-medium">Yarn</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Track your stash — yarn products and individual skeins.
            </p>
          </Link>
        </div>
      </main>
    </div>
  );
}
