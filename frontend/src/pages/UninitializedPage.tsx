export function UninitializedPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="w-full max-w-sm space-y-6 px-4 text-center">
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight">System Not Initialized</h1>
          <p className="text-sm text-muted-foreground">
            No administrator account has been configured. Run the seed command on the server to initialize the system.
          </p>
        </div>
        <div className="rounded-md bg-muted px-4 py-3 text-left font-mono text-xs text-muted-foreground">
          docker compose exec backend python -m app.cli seed
        </div>
      </div>
    </div>
  );
}
