interface Props {
  frontendVersion: string;
  backendVersion: string;
}

export function VersionErrorPage({ frontendVersion, backendVersion }: Props) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="w-full max-w-sm space-y-6 px-4 text-center">
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight">Server Version Mismatch</h1>
          <p className="text-sm text-muted-foreground">
            The server is currently being updated. Please try again in a moment, or contact your
            administrator if this problem persists.
          </p>
        </div>
        <div className="rounded-md bg-muted px-4 py-3 text-left font-mono text-xs text-muted-foreground space-y-1">
          <div>Frontend: {frontendVersion}</div>
          <div>Backend:&nbsp; {backendVersion || "unreachable"}</div>
        </div>
      </div>
    </div>
  );
}
