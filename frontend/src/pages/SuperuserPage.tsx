import React, { useState, useEffect, useRef } from "react";
import * as Sentry from "@sentry/react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import {
  getAdminEula,
  createEulaVersion,
  getReconcileReport,
  backfillClerkUser,
  startS3AuditScan,
  getS3AuditTask,
  cleanupS3Orphans,
  startCveScan,
  getCveScanTask,
  getWorkerStatus,
  startDebugSleep,
  getTaskHistory,
  revokeTask,
  runPurgeSoftDeleted,
  getSoftDeleteQueue,
  getDeletionQueue,
  listScheduledTasks,
  patchScheduledTask,
  listExports,
  deleteExport,
  listCredentials,
  createCredential,
  patchCredential,
  deleteCredential,
  getConfig,
  saveConfig,
  testConfigService,
  type ScheduledTask,
  type TaskHistoryItem,
  type ReconcileReport,
  type S3AuditResult,
  type CveScanResult,
  type CveFinding,
  type WorkerStatus,
  type WorkerInfo,
  type DeletionQueueUser,
  type AdminExportRecord,
  type CredentialExpiry,
  type CredentialResource,
  type ConfigTestResult,
} from "@/api/admin";
import { EulaContent } from "@/components/EulaContent";
import { CveBanner } from "@/components/admin/CveBanner";
import { CopyEmail } from "@/components/admin/CopyEmail";
import { formatBytes } from "@/lib/image-utils";

declare const __FRONTEND_DEPS__: Record<string, string>;

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const parts: string[] = [];
  if (d > 0) parts.push(`${d} day${d !== 1 ? "s" : ""}`);
  if (h > 0) parts.push(`${h} hour${h !== 1 ? "s" : ""}`);
  parts.push(`${m} minute${m !== 1 ? "s" : ""}`);
  return parts.join(", ");
}

type SuperuserSection = "eula" | "storage" | "cve" | "workers" | "deletion" | "reconcile" | "maintenance" | "schedule" | "exports" | "credentials" | "sandbox";

// ---------------------------------------------------------------------------
// EULA tab
// ---------------------------------------------------------------------------

type LintIssue = { level: "error" | "warning"; message: string };
type LintResult = { ok: boolean; issues: LintIssue[] };

function lintHtml(html: string): LintResult {
  const issues: LintIssue[] = [];
  if (!html.trim()) return { ok: false, issues: [{ level: "error", message: "HTML is empty" }] };

  const doc = new DOMParser().parseFromString(html, "text/html");

  // Parser error nodes (browsers inject these for severely malformed markup)
  if (doc.querySelector("parseerror")) {
    issues.push({ level: "error", message: "HTML parse error — check for malformed tags" });
  }

  // Disallowed elements
  for (const tag of ["script", "iframe", "object", "embed", "form"]) {
    if (doc.body.querySelector(tag)) {
      issues.push({ level: "error", message: `Disallowed element: <${tag}>` });
    }
  }

  // Inline event handlers
  for (const el of doc.body.querySelectorAll("*")) {
    for (const attr of el.attributes) {
      if (attr.name.startsWith("on")) {
        issues.push({ level: "error", message: `Inline event handler: ${attr.name} on <${el.tagName.toLowerCase()}>` });
        break;
      }
    }
  }

  // javascript: hrefs
  for (const a of doc.body.querySelectorAll("a[href]")) {
    if ((a.getAttribute("href") ?? "").toLowerCase().startsWith("javascript:")) {
      issues.push({ level: "error", message: "javascript: URL in <a> href" });
    }
  }

  // Inline <style> blocks (warning only)
  if (doc.body.querySelector("style")) {
    issues.push({ level: "warning", message: "<style> tag found — may affect page layout" });
  }

  return { ok: issues.every((i) => i.level !== "error"), issues };
}

function EulaTab() {
  const qc = useQueryClient();
  const { data: current, isLoading } = useQuery({
    queryKey: ["admin", "eula"],
    queryFn: getAdminEula,
  });

  const currentVersion = current?.version ?? null;
  const nextVersion = React.useMemo(() => {
    if (!currentVersion) return "";
    const [major, minor] = currentVersion.split(".").map(Number);
    return `${major}.${(minor ?? 0) + 1}`;
  }, [currentVersion]);
  const [versionOverride, setVersionOverride] = useState<string | null>(null);
  const version = versionOverride ?? nextVersion;
  const setVersion = setVersionOverride;
  const [bodyHtml, setBodyHtml] = useState("");
  const [effectiveDate, setEffectiveDate] = useState(
    () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16)
  );
  const [showCurrent, setShowCurrent] = useState(false);
  const [lintResult, setLintResult] = useState<LintResult | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState(false);

  const versionValid = /^\d+\.\d+$/.test(version.trim());

  function handleBodyHtmlChange(val: string) {
    setBodyHtml(val);
    setLintResult(null); // reset lint when content changes
  }

  const { mutate: publish, isPending } = useMutation({
    mutationFn: () => createEulaVersion(
      version.trim(),
      bodyHtml.trim(),
      effectiveDate ? new Date(effectiveDate).toISOString() : undefined,
    ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "eula"] });
      qc.invalidateQueries({ queryKey: ["eula", "current"] });
      setFormSuccess(true);
      setVersionOverride(null);
      setBodyHtml("");
      setEffectiveDate(new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16));
      setLintResult(null);
      setFormError(null);
      setTimeout(() => setFormSuccess(false), 3000);
    },
    onError: (e: unknown) => {
      setFormError(e instanceof Error ? e.message : "Failed to publish EULA version");
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setFormSuccess(false);
    if (!version.trim()) { setFormError("Version is required"); return; }
    if (!versionValid) { setFormError("Version must be in x.y format (e.g. 0.4)"); return; }
    if (!bodyHtml.trim()) { setFormError("Body HTML is required"); return; }
    if (!lintResult?.ok) { setFormError("HTML must pass lint before publishing"); return; }
    publish();
  }

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <div className="space-y-6">
      <div className="space-y-1 pb-2 border-b">
        <h1 className="text-lg font-semibold">Terms of Service</h1>
        <p className="text-sm text-muted-foreground">View the current published EULA version and publish a new version that will require all users to re-accept on next login.</p>
      </div>
      {/* Current version */}
      <div className="space-y-2">
        <h2 className="text-sm font-medium">Current version: {current?.version}</h2>
        <p className="text-xs text-muted-foreground">
          Effective {current ? new Date(current.effective_date).toLocaleDateString() : "—"}
          {" · "}Published {current ? new Date(current.created_at).toLocaleString() : "—"}
        </p>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" type="button" onClick={() => setShowCurrent((v) => !v)}>
            {showCurrent ? "Hide" : "View"} current EULA
          </Button>
        </div>
        {showCurrent && current && (
          <div className="rounded-lg border p-4 max-h-[40vh] overflow-y-auto">
            <EulaContent bodyHtml={current.body_html} />
          </div>
        )}
      </div>

      <hr />

      {/* Publish new version */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <h2 className="text-sm font-medium">Publish new version</h2>
        <p className="text-xs text-muted-foreground">
          Publishing a new version will require all users to re-accept on next login.
        </p>

        <div className="space-y-1">
          <label className="text-xs font-medium">Version string</label>
          <input
            className={`w-full rounded border bg-background px-3 py-1.5 text-sm ${version && !versionValid ? "border-destructive" : ""}`}
            placeholder="e.g. 0.4"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
          />
          {version && !versionValid && (
            <p className="text-xs text-destructive">Must be x.y format (e.g. 0.4)</p>
          )}
        </div>

        <div className="space-y-1">
          <label className="text-xs font-medium">Effective date</label>
          <input
            type="datetime-local"
            className="w-full rounded border bg-background px-3 py-1.5 text-sm"
            value={effectiveDate}
            onChange={(e) => setEffectiveDate(e.target.value)}
          />
        </div>

        <div className="space-y-1">
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium">Body HTML</label>
            {current && (
              <Button variant="outline" size="sm" type="button" onClick={() => {
                const html = current.body_html.replace(/Version \d+\.\d+/, `Version ${version}`);
                setBodyHtml(html);
                setLintResult(null);
              }}>
                Copy to editor
              </Button>
            )}
          </div>
          <textarea
            className="w-full rounded border bg-background px-3 py-1.5 text-sm font-mono min-h-[240px]"
            placeholder="<p>Paste full EULA HTML here…</p>"
            value={bodyHtml}
            onChange={(e) => handleBodyHtmlChange(e.target.value)}
          />
        </div>

        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!bodyHtml.trim()}
          onClick={() => setLintResult(lintHtml(bodyHtml))}
        >
          Lint &amp; preview
        </Button>

        {/* Lint results */}
        {lintResult && (
          <div className={`rounded-lg border p-3 space-y-1 ${lintResult.ok ? "border-green-500/40 bg-green-500/5" : "border-destructive/40 bg-destructive/5"}`}>
            {lintResult.issues.length === 0 ? (
              <p className="text-xs text-green-600 font-medium">✓ No issues found</p>
            ) : (
              lintResult.issues.map((issue, i) => (
                <p key={i} className={`text-xs ${issue.level === "error" ? "text-destructive" : "text-yellow-600"}`}>
                  {issue.level === "error" ? "✗" : "⚠"} {issue.message}
                </p>
              ))
            )}
            {lintResult.ok && (
              <p className="text-xs text-green-600 font-medium">✓ Lint passed — HTML is safe to publish</p>
            )}
          </div>
        )}

        {/* New EULA preview */}
        {lintResult?.ok && bodyHtml.trim() && (
          <div className="space-y-1">
            <p className="text-xs font-medium">Preview</p>
            <div className="rounded-lg border p-4 max-h-[40vh] overflow-y-auto">
              <EulaContent bodyHtml={bodyHtml} />
            </div>
          </div>
        )}

        {formError && (
          <p className="text-sm text-destructive">{formError}</p>
        )}
        {formSuccess && (
          <p className="text-sm text-green-600">EULA version published.</p>
        )}

        {lintResult?.ok && (
          <Button type="submit" disabled={isPending}>
            {isPending ? "Publishing…" : "Publish new version"}
          </Button>
        )}
      </form>
    </div>
  );
}
function StorageAuditTab() {
  const [scanStatus, setScanStatus] = useState<"idle" | "running" | "complete" | "failed">("idle");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [result, setResult] = useState<S3AuditResult | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [cleaning, setCleaning] = useState(false);
  const [cleanupCount, setCleanupCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!taskId || scanStatus !== "running") return;
    pollRef.current = setInterval(async () => {
      try {
        const data = await getS3AuditTask(taskId);
        if (data.status === "complete" && data.result) {
          setResult(data.result);
          setScanStatus("complete");
          clearInterval(pollRef.current!);
        } else if (data.status === "failed") {
          setError(data.error ?? "Scan failed");
          setScanStatus("failed");
          clearInterval(pollRef.current!);
        }
      } catch {
        setError("Failed to poll scan status");
        setScanStatus("failed");
        clearInterval(pollRef.current!);
      }
    }, 2000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [taskId, scanStatus]);

  async function startScan() {
    setScanStatus("running");
    setResult(null);
    setSelected(new Set());
    setCleanupCount(null);
    setError(null);
    try {
      const { task_id } = await startS3AuditScan();
      setTaskId(task_id);
    } catch {
      setScanStatus("failed");
      setError("Failed to start scan");
    }
  }

  function toggleSelect(key: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) { next.delete(key); } else { next.add(key); }
      return next;
    });
  }

  function toggleAll() {
    if (!result) return;
    setSelected((prev) =>
      prev.size === result.orphaned_files.length
        ? new Set()
        : new Set(result.orphaned_files.map((f) => f.key))
    );
  }

  async function handleCleanup() {
    if (!selected.size || !result) return;
    const noun = selected.size === 1 ? "file" : "files";
    if (!window.confirm(`Permanently delete ${selected.size} ${noun} from S3? This cannot be undone.`)) return;
    setCleaning(true);
    setError(null);
    try {
      const { deleted } = await cleanupS3Orphans(Array.from(selected));
      setCleanupCount(deleted);
      setResult({
        ...result,
        orphaned_files: result.orphaned_files.filter((f) => !selected.has(f.key)),
        orphaned_count: result.orphaned_count - deleted,
      });
      setSelected(new Set());
    } catch {
      setError("Cleanup failed — check logs");
    } finally {
      setCleaning(false);
    }
  }

  const allSelected = !!result && selected.size === result.orphaned_files.length && result.orphaned_files.length > 0;

  return (
    <div className="space-y-4">
      <div className="space-y-1 pb-2 border-b">
        <h1 className="text-lg font-semibold">Storage Audit</h1>
        <p className="text-sm text-muted-foreground">Scan R2/S3 for orphaned files that are no longer referenced by any database record and permanently delete them.</p>
      </div>
      <div className="flex items-center gap-3">
        <Button onClick={startScan} disabled={scanStatus === "running"} size="sm">
          {scanStatus === "running" ? "Scanning…" : "Scan S3 for Orphaned Files"}
        </Button>
        {scanStatus === "running" && (
          <span className="text-xs text-muted-foreground animate-pulse">Running in background…</span>
        )}
        {selected.size > 0 && (
          <>
            <span className="text-xs text-destructive">
              {selected.size} file{selected.size !== 1 ? "s" : ""} selected — permanent delete, cannot be undone.
            </span>
            <Button variant="destructive" size="sm" onClick={handleCleanup} disabled={cleaning}>
              {cleaning ? "Deleting…" : "Delete Selected"}
            </Button>
          </>
        )}
        {cleanupCount !== null && (
          <span className="text-sm text-green-600 dark:text-green-400">
            Deleted {cleanupCount} file{cleanupCount !== 1 ? "s" : ""} from S3.
          </span>
        )}
        {error && <span className="text-sm text-destructive">{error}</span>}
      </div>

      {result && (
        <div className="space-y-3">
          {result.not_applicable ? (
            <p className="text-sm text-muted-foreground">
              Storage backend is not S3 — audit not applicable in this environment.
            </p>
          ) : (
            <>
              <div className="flex gap-6 text-sm">
                <span><span className="font-medium">{result.total_s3_keys}</span> S3 keys</span>
                <span><span className="font-medium">{result.total_db_paths}</span> DB-referenced paths</span>
                <span><span className="font-medium text-amber-600 dark:text-amber-400">{result.orphaned_count}</span> orphaned</span>
              </div>

              {result.orphaned_files.length === 0 ? (
                <p className="text-sm text-muted-foreground">No orphaned files found.</p>
              ) : (
                <div className="rounded-md border overflow-auto max-h-96">
                  <table className="w-full text-xs">
                    <thead className="bg-muted sticky top-0">
                      <tr>
                        <th className="p-2 text-left w-8">
                          <input
                            type="checkbox"
                            checked={allSelected}
                            onChange={toggleAll}
                            className="cursor-pointer"
                          />
                        </th>
                        <th className="p-2 text-left font-medium">Key</th>
                        <th className="p-2 text-right font-medium">Size</th>
                        <th className="p-2 text-right font-medium">Last Modified</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.orphaned_files.map((f) => (
                        <tr key={f.key} className="border-t hover:bg-muted/50">
                          <td className="p-2">
                            <input
                              type="checkbox"
                              checked={selected.has(f.key)}
                              onChange={() => toggleSelect(f.key)}
                              className="cursor-pointer"
                            />
                          </td>
                          <td className="p-2 font-mono break-all">{f.key}</td>
                          <td className="p-2 text-right whitespace-nowrap">{formatBytes(f.size)}</td>
                          <td className="p-2 text-right whitespace-nowrap text-muted-foreground">
                            {new Date(f.last_modified).toLocaleDateString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function CveFindingsTable({ title, findings }: { title: string; findings: CveFinding[] }) {
  if (findings.length === 0) return null;
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{title}</h3>
      <div className="rounded-md border overflow-auto max-h-96">
        <table className="w-full text-xs">
          <thead className="bg-muted sticky top-0">
            <tr>
              <th className="p-2 text-left font-medium">Package</th>
              <th className="p-2 text-left font-medium">Version</th>
              <th className="p-2 text-left font-medium">CVE ID</th>
              <th className="p-2 text-left font-medium">Fix</th>
              <th className="p-2 text-left font-medium">Summary</th>
            </tr>
          </thead>
          <tbody>
            {findings.flatMap((pkg) =>
              pkg.vulns.map((v, i) => (
                <tr key={`${pkg.name}-${v.id}-${i}`} className="border-t hover:bg-muted/50">
                  <td className="p-2 font-mono">{i === 0 ? pkg.name : ""}</td>
                  <td className="p-2 font-mono tabular-nums">{i === 0 ? pkg.version : ""}</td>
                  <td className="p-2 font-mono text-destructive">{v.id}</td>
                  <td className="p-2 font-mono">{v.fix_versions.length > 0 ? v.fix_versions.join(", ") : "—"}</td>
                  <td className="p-2 text-muted-foreground max-w-xs truncate" title={v.description}>
                    {v.description || "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CveScanTab() {
  const qc = useQueryClient();
  const [scanStatus, setScanStatus] = useState<"idle" | "running" | "complete" | "failed">("idle");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [result, setResult] = useState<CveScanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!taskId || scanStatus !== "running") return;
    pollRef.current = setInterval(async () => {
      try {
        const data = await getCveScanTask(taskId);
        if (data.status === "complete" && data.result) {
          setResult(data.result);
          setScanStatus("complete");
          qc.invalidateQueries({ queryKey: ["admin", "cve-summary"] });
          clearInterval(pollRef.current!);
        } else if (data.status === "failed") {
          setError(data.error ?? "Scan failed");
          setScanStatus("failed");
          clearInterval(pollRef.current!);
        }
      } catch {
        setError("Failed to poll scan status");
        setScanStatus("failed");
        clearInterval(pollRef.current!);
      }
    }, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [taskId, scanStatus, qc]);

  async function startScan() {
    setScanStatus("running");
    setResult(null);
    setError(null);
    try {
      const { task_id } = await startCveScan(__FRONTEND_DEPS__);
      setTaskId(task_id);
    } catch {
      setScanStatus("failed");
      setError("Failed to start scan");
    }
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1 pb-2 border-b">
        <h1 className="text-lg font-semibold">CVE Scanner</h1>
        <p className="text-sm text-muted-foreground">Run pip-audit and OSV.dev scans against Python and npm dependencies. Results populate the warning banner shown on all admin pages.</p>
      </div>
      <div className="space-y-1">
        <p className="text-xs text-muted-foreground">
          Scans Python dependencies via pip-audit and npm packages via OSV.dev.
          Results are stored and shown in the warning banner on all admin pages.
        </p>
      </div>
      <div className="flex items-center gap-3">
        <Button onClick={startScan} disabled={scanStatus === "running"} size="sm">
          {scanStatus === "running" ? "Scanning…" : "Run CVE Scan"}
        </Button>
        {scanStatus === "running" && (
          <span className="text-xs text-muted-foreground animate-pulse">Running in background…</span>
        )}
        {error && <span className="text-sm text-destructive">{error}</span>}
      </div>

      {result && (
        <div className="space-y-4">
          <div className="flex gap-6 text-sm">
            <span>
              <span className={`font-medium ${result.total_findings > 0 ? "text-destructive" : "text-green-600 dark:text-green-400"}`}>
                {result.total_findings}
              </span>
              {" "}total {result.total_findings === 1 ? "vulnerability" : "vulnerabilities"}
            </span>
            <span className="text-xs text-muted-foreground self-center">
              scanned {new Date(result.scanned_at).toLocaleString()}
            </span>
          </div>
          {result.total_findings === 0 && (
            <p className="text-sm text-green-600 dark:text-green-400">No vulnerabilities found.</p>
          )}
          <CveFindingsTable title="Backend (Python)" findings={result.backend_findings} />
          <CveFindingsTable title="Frontend (npm)" findings={result.frontend_findings} />
        </div>
      )}
    </div>
  );
}

function WorkerCard({ worker, apiVersion }: { worker: WorkerInfo; apiVersion: string }) {
  const isOnline = worker.status === "online";
  const hasActive = worker.active_tasks.length > 0;
  const hasReserved = worker.reserved_tasks.length > 0;
  const versionMismatch = isOnline && worker.version != null && worker.version !== apiVersion;

  return (
    <div className={`border rounded-lg overflow-hidden ${versionMismatch ? "border-amber-500/50" : ""}`}>
      <div className={`flex items-center gap-3 px-4 py-3 ${versionMismatch ? "bg-amber-500/10" : "bg-muted/20"}`}>
        <span className={`w-2 h-2 rounded-full shrink-0 ${isOnline ? "bg-green-500" : "bg-red-500"}`} />
        <span className="text-sm font-mono font-medium flex-1 truncate">{worker.name}</span>
        {isOnline && worker.version && (
          <span className={`text-xs px-2 py-0.5 rounded border font-mono ${
            versionMismatch
              ? "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300"
              : "border-border text-muted-foreground"
          }`} title={versionMismatch ? `Expected ${apiVersion}` : undefined}>
            {worker.version}{versionMismatch ? " ⚠" : ""}
          </span>
        )}
        {isOnline && worker.concurrency !== null && (
          <span className={`text-xs px-2 py-0.5 rounded border tabular-nums ${
            worker.active_tasks.length >= worker.concurrency
              ? "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300"
              : worker.active_tasks.length > 0
              ? "border-blue-500/30 text-blue-600 dark:text-blue-400"
              : "border-border text-muted-foreground"
          }`}>
            {worker.active_tasks.length}/{worker.concurrency} slots
          </span>
        )}
        <span className={`text-xs px-2 py-0.5 rounded border ${isOnline ? "border-green-500/30 text-green-600 dark:text-green-400" : "border-destructive/30 text-destructive"}`}>
          {worker.status}
        </span>
      </div>
      {isOnline && (
        <div className="divide-y">
          <div className="grid grid-cols-4 divide-x px-4 py-2.5 text-sm">
            <div className="flex flex-col gap-0.5 pr-4">
              <span className="text-xs text-muted-foreground">Concurrency</span>
              <span className="font-medium tabular-nums">{worker.concurrency ?? "—"}</span>
            </div>
            <div className="flex flex-col gap-0.5 px-4">
              <span className="text-xs text-muted-foreground">Completed</span>
              <span className="font-medium tabular-nums">{worker.completed_tasks?.toLocaleString() ?? "—"}</span>
            </div>
            <div className="flex flex-col gap-0.5 px-4">
              <span className="text-xs text-muted-foreground">Uptime</span>
              <span className="font-medium tabular-nums">{worker.uptime != null ? formatUptime(worker.uptime) : "—"}</span>
            </div>
            <div className="flex flex-col gap-0.5 pl-4">
              <span className="text-xs text-muted-foreground">Memory</span>
              <span className="font-medium tabular-nums">{worker.memory_mb != null ? `${worker.memory_mb} MB` : "—"}</span>
            </div>
          </div>
          {hasActive && (
            <div className="px-4 py-2.5 space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Active ({worker.active_tasks.length})
              </p>
              {worker.active_tasks.map((t) => (
                <div key={t.id} className="text-xs space-y-0.5">
                  <p className="font-mono text-foreground">{t.name}</p>
                  <p className="text-muted-foreground truncate">{t.args_repr}</p>
                  {t.time_start && (
                    <p className="text-muted-foreground">
                      started {new Date(t.time_start * 1000).toLocaleTimeString()}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
          {hasReserved && (
            <div className="px-4 py-2.5 space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Reserved ({worker.reserved_tasks.length})
              </p>
              {worker.reserved_tasks.map((t) => (
                <div key={t.id} className="text-xs">
                  <p className="font-mono text-foreground">{t.name}</p>
                  <p className="text-muted-foreground truncate">{t.args_repr}</p>
                </div>
              ))}
            </div>
          )}
          {!hasActive && !hasReserved && (
            <p className="px-4 py-2.5 text-xs text-muted-foreground">No active or reserved tasks.</p>
          )}
        </div>
      )}
    </div>
  );
}

function WorkersTab() {
  const [data, setData] = useState<WorkerStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sleeping, setSleeping] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const fetch = () =>
      getWorkerStatus()
        .then((d) => { setData(d); setError(null); })
        .catch(() => setError("Failed to fetch worker status"));
    fetch();
    intervalRef.current = setInterval(fetch, 3_000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, []);

  function triggerSleep() {
    setSleeping(true);
    startDebugSleep(45)
      .then(() => setSleeping(false))
      .catch(() => setSleeping(false));
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1 pb-2 border-b">
        <h1 className="text-lg font-semibold">Worker Status</h1>
        <p className="text-sm text-muted-foreground">Live view of Celery worker health, queue depths, active and reserved tasks, and recent task history.</p>
      </div>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <span className="text-xs text-muted-foreground">
            {data
              ? `Updated ${new Date(data.checked_at).toLocaleTimeString()} · auto-refreshes every 3s`
              : "Loading…"}
          </span>
        </div>
        <Button size="sm" variant="outline" disabled={sleeping} onClick={triggerSleep}>
          {sleeping ? "Dispatching…" : "Run test task"}
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {data && (
        <>
          {data.queues.length > 0 && (
            <div>
              <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Queues</h3>
              <div className="border rounded-lg divide-y overflow-hidden">
                {data.queues.map((q) => (
                  <div key={q.name} className="flex items-center justify-between px-4 py-2.5 bg-background">
                    <span className="text-sm font-mono">{q.name}</span>
                    <span className={`text-sm font-medium tabular-nums ${q.depth > 0 ? "text-amber-600 dark:text-amber-400" : ""}`}>
                      {q.depth} pending
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div>
            <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
              Workers ({data.workers.length})
            </h3>
            <div className="space-y-3">
              {data.workers.map((w) => (
                <WorkerCard key={w.name} worker={w} apiVersion={data.api_version} />
              ))}
            </div>
          </div>
        </>
      )}

      <TaskHistoryTable />
    </div>
  );
}

const STATE_CLS: Record<string, string> = {
  queued: "text-muted-foreground",
  running: "text-blue-600 dark:text-blue-400",
  success: "text-green-600 dark:text-green-400",
  failed: "text-destructive",
  revoked: "text-amber-600 dark:text-amber-400",
};

function fmtSec(s: number | null): string {
  if (s === null) return "—";
  if (s < 1) return `${Math.round(s * 1000)}ms`;
  return `${s.toFixed(1)}s`;
}

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function shortName(name: string): string {
  const parts = name.split(".");
  return parts.length >= 2 ? parts.slice(-2).join(".") : name;
}

function TaskHistoryRow({ item, onRevoke }: { item: TaskHistoryItem; onRevoke: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const cancellable = item.state === "queued" || item.state === "running";
  return (
    <>
      <tr
        className={`border-t hover:bg-muted/30 text-xs ${item.error ? "cursor-pointer" : ""}`}
        onClick={() => item.error && setExpanded((v) => !v)}
      >
        <td className="px-3 py-2 font-mono text-muted-foreground whitespace-nowrap">{fmtTime(item.queued_at)}</td>
        <td className="px-3 py-2 font-mono" title={item.name}>{shortName(item.name)}</td>
        <td className="px-3 py-2 text-muted-foreground">{item.caller}</td>
        <td className={`px-3 py-2 font-medium ${STATE_CLS[item.state] ?? ""}`}>{item.state}</td>
        <td className="px-3 py-2 tabular-nums text-right">{fmtSec(item.wait_seconds)}</td>
        <td className="px-3 py-2 tabular-nums text-right">{fmtSec(item.run_seconds)}</td>
        <td className="px-3 py-2 tabular-nums text-right whitespace-nowrap">{fmtTime(item.completed_at)}</td>
        <td className="px-3 py-2 text-muted-foreground">{item.error ? (expanded ? "▲" : "▼ error") : "—"}</td>
        <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
          {cancellable && (
            <button
              className="text-xs text-destructive hover:underline"
              onClick={() => onRevoke(item.task_id)}
            >
              Cancel
            </button>
          )}
        </td>
      </tr>
      {expanded && item.error && (
        <tr className="border-t bg-destructive/5">
          <td colSpan={9} className="px-3 py-2">
            <pre className="text-xs font-mono text-destructive whitespace-pre-wrap">{item.error}</pre>
          </td>
        </tr>
      )}
    </>
  );
}

function TaskHistoryTable() {
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 25;
  const queryClient = useQueryClient();

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["admin", "task-history", page],
    queryFn: () => getTaskHistory(page, PAGE_SIZE),
    refetchInterval: 5_000,
  });

  const revokeMutation = useMutation({
    mutationFn: revokeTask,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["admin", "task-history"] }),
  });

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Task History {data ? `(${data.total})` : ""}
        </h3>
        <button
          className="text-xs text-muted-foreground hover:text-foreground"
          onClick={() => refetch()}
        >
          Refresh
        </button>
      </div>

      {isLoading && <p className="text-xs text-muted-foreground">Loading…</p>}

      {data && data.items.length === 0 && (
        <p className="text-xs text-muted-foreground">No task history yet. Dispatch a task to see it here.</p>
      )}

      {data && data.items.length > 0 && (
        <>
          <div className="rounded-md border overflow-auto max-h-[480px]">
            <table className="w-full text-xs min-w-[640px]">
              <thead className="bg-muted sticky top-0">
                <tr>
                  <th className="px-3 py-2 text-left font-medium whitespace-nowrap">Queued at</th>
                  <th className="px-3 py-2 text-left font-medium">Task</th>
                  <th className="px-3 py-2 text-left font-medium">Caller</th>
                  <th className="px-3 py-2 text-left font-medium">State</th>
                  <th className="px-3 py-2 text-right font-medium whitespace-nowrap">Wait</th>
                  <th className="px-3 py-2 text-right font-medium whitespace-nowrap">Run</th>
                  <th className="px-3 py-2 text-right font-medium whitespace-nowrap">Completed at</th>
                  <th className="px-3 py-2 text-left font-medium">Error</th>
                  <th className="px-3 py-2 text-left font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <TaskHistoryRow key={item.task_id} item={item} onRevoke={(id) => revokeMutation.mutate(id)} />
                ))}
              </tbody>
            </table>
          </div>

          {data.pages > 1 && (
            <div className="flex items-center justify-between text-xs text-muted-foreground pt-1">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                className="px-2 py-1 border rounded disabled:opacity-40 hover:bg-muted/40"
              >
                ← Prev
              </button>
              <span>Page {data.page} of {data.pages}</span>
              <button
                disabled={page >= data.pages}
                onClick={() => setPage((p) => p + 1)}
                className="px-2 py-1 border rounded disabled:opacity-40 hover:bg-muted/40"
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

const DELETION_STATE_STYLE: Record<string, string> = {
  pending: "border-border text-muted-foreground",
  in_progress: "border-blue-500/40 bg-blue-500/10 text-blue-700 dark:text-blue-300",
  stalled: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  complete: "border-green-500/40 bg-green-500/10 text-green-700 dark:text-green-300",
};

function DeletionStateBadge({ state }: { state: string }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded border font-medium ${DELETION_STATE_STYLE[state] ?? "border-border text-muted-foreground"}`}>
      {state}
    </span>
  );
}

function DeletionTab() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "deletion-queue"],
    queryFn: getDeletionQueue,
    refetchInterval: 10_000,
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error) return <p className="text-sm text-destructive">Failed to load deletion queue.</p>;

  const users = data ?? [];

  return (
    <div className="space-y-4">
      <div className="space-y-1 pb-2 border-b">
        <h1 className="text-lg font-semibold">Deletion Queue</h1>
        <p className="text-sm text-muted-foreground">Users currently in the deletion pipeline and soft-deleted content items awaiting hard purge.</p>
      </div>

      {users.length === 0 ? (
        <p className="text-sm text-muted-foreground">No users in the deletion queue.</p>
      ) : (
        <div className="rounded-md border overflow-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Display name</th>
                <th className="px-3 py-2 text-left font-medium">Email</th>
                <th className="px-3 py-2 text-left font-medium">State</th>
                <th className="px-3 py-2 text-left font-medium whitespace-nowrap">Initiated</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u: DeletionQueueUser) => (
                <tr key={u.id} className={`border-t ${u.deletion_state === "stalled" ? "bg-amber-500/5" : ""}`}>
                  <td className="px-3 py-2 font-medium">{u.display_name}</td>
                  <td className="px-3 py-2 text-muted-foreground font-mono text-xs">{u.email}</td>
                  <td className="px-3 py-2">
                    <DeletionStateBadge state={u.deletion_state} />
                    {u.deletion_state === "stalled" && (
                      <span className="ml-1 text-xs text-amber-600 dark:text-amber-400">⚠ check logs</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-muted-foreground text-xs whitespace-nowrap">
                    {u.deletion_initiated_at
                      ? new Date(u.deletion_initiated_at).toLocaleString()
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function MaintenanceTab() {
  const queryClient = useQueryClient();
  const [purging, setPurging] = useState(false);

  const { data: queue, isLoading: queueLoading } = useQuery({
    queryKey: ["admin", "soft-delete-queue"],
    queryFn: getSoftDeleteQueue,
  });

  const nothingEligible = queue != null && queue.ready_to_purge.total === 0;

  function triggerPurge() {
    setPurging(true);
    runPurgeSoftDeleted()
      .then(() => {
        setPurging(false);
        queryClient.invalidateQueries({ queryKey: ["admin", "task-history"] });
        queryClient.invalidateQueries({ queryKey: ["admin", "soft-delete-queue"] });
      })
      .catch(() => setPurging(false));
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1 pb-2 border-b">
        <h1 className="text-lg font-semibold">Maintenance</h1>
        <p className="text-sm text-muted-foreground">Manual maintenance operations including hard-purging soft-deleted records that have passed the retention window.</p>
      </div>
      {/* Soft-delete queue summary */}
      <div className="rounded-lg border p-5 space-y-3">
        <div>
          <p className="text-sm font-medium">Soft-Delete Queue</p>
          {queue && (
            <p className="text-xs text-muted-foreground mt-1">
              Items deleted before{" "}
              <span className="font-mono">{new Date(queue.cutoff).toLocaleDateString()}</span>
              {" "}are eligible for purge (retention: {queue.retention_days} days).
            </p>
          )}
        </div>

        {queueLoading && <p className="text-xs text-muted-foreground">Loading…</p>}

        {queue && (
          nothingEligible && queue.in_retention_window.total === 0 ? (
            <p className="text-xs text-muted-foreground">No soft-deleted records found.</p>
          ) : (
            <div className="rounded-md border overflow-auto">
              <table className="w-full text-xs">
                <thead className="bg-muted">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Type</th>
                    <th className="px-3 py-2 text-right font-medium text-destructive">Ready to purge</th>
                    <th className="px-3 py-2 text-right font-medium">In retention window</th>
                  </tr>
                </thead>
                <tbody>
                  {(["drafts", "projects", "yarn", "looms"] as const).map((key) => (
                    <tr key={key} className="border-t">
                      <td className="px-3 py-2 capitalize">{key}</td>
                      <td className={`px-3 py-2 text-right tabular-nums font-medium ${queue.ready_to_purge[key] > 0 ? "text-destructive" : "text-muted-foreground"}`}>
                        {queue.ready_to_purge[key]}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                        {queue.in_retention_window[key]}
                      </td>
                    </tr>
                  ))}
                  <tr className="border-t bg-muted/40 font-medium">
                    <td className="px-3 py-2">Total</td>
                    <td className={`px-3 py-2 text-right tabular-nums ${queue.ready_to_purge.total > 0 ? "text-destructive" : "text-muted-foreground"}`}>
                      {queue.ready_to_purge.total}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                      {queue.in_retention_window.total}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          )
        )}
      </div>

      {/* Purge action */}
      <div className="rounded-lg border p-5 space-y-3">
        <div>
          <p className="text-sm font-medium">Purge Soft-Deleted Records</p>
          <p className="text-xs text-muted-foreground mt-1">
            Hard-deletes drafts, looms, projects, and yarn that have been soft-deleted for longer than the
            configured retention period (<code className="font-mono">SOFT_DELETE_RETENTION_DAYS</code>, default 365 days).
            Associated storage files are removed at the same time. User deletion is handled separately by the
            deletion cascade task.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            size="sm"
            variant="destructive"
            disabled={purging || nothingEligible}
            onClick={triggerPurge}
            title={nothingEligible ? "Nothing is eligible for purge yet" : undefined}
          >
            {purging ? "Queuing…" : "Run Purge Now"}
          </Button>
          {nothingEligible ? (
            <p className="text-xs text-muted-foreground">Nothing eligible for purge yet.</p>
          ) : (
            <p className="text-xs text-muted-foreground">Results appear in the Workers → Task History table.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function ReconcileTab() {
  const queryClient = useQueryClient();
  const [ran, setRan] = useState(false);
  const [report, setReport] = useState<ReconcileReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [backfilling, setBackfilling] = useState<string | null>(null);
  const [backfillResults, setBackfillResults] = useState<Record<string, string>>({});

  async function runReconcile() {
    setLoading(true);
    setError(null);
    try {
      const data = await getReconcileReport();
      setReport(data);
      setRan(true);
    } catch {
      setError("Failed to run reconciliation. Check that the Clerk API key is configured.");
    } finally {
      setLoading(false);
    }
  }

  async function handleBackfill(clerkUserId: string, role: "user" | "admin") {
    setBackfilling(clerkUserId);
    try {
      const result = await backfillClerkUser(clerkUserId, role);
      setBackfillResults((prev) => ({ ...prev, [clerkUserId]: result.status }));
      setReport((prev) =>
        prev
          ? { ...prev, clerk_only: prev.clerk_only.filter((u) => u.clerk_user_id !== clerkUserId) }
          : prev
      );
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    } catch {
      setBackfillResults((prev) => ({ ...prev, [clerkUserId]: "error" }));
    } finally {
      setBackfilling(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1 pb-2 border-b">
        <h1 className="text-lg font-semibold">Clerk Reconciliation</h1>
        <p className="text-sm text-muted-foreground">Cross-reference Clerk accounts against the database to find and backfill users created directly in the Clerk dashboard.</p>
      </div>

      <Button onClick={runReconcile} disabled={loading} size="sm">
        {loading ? "Running…" : ran ? "Re-run reconciliation" : "Run reconciliation"}
      </Button>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {report && (
        <div className="space-y-6">
          {/* In Clerk, not in DB */}
          <div className="space-y-2">
            <h3 className="text-sm font-medium">
              In Clerk, not in DB
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                ({report.clerk_only.length} {report.clerk_only.length === 1 ? "user" : "users"})
              </span>
            </h3>
            {report.clerk_only.length === 0 ? (
              <p className="text-xs text-muted-foreground">No unmatched Clerk accounts.</p>
            ) : (
              <div className="rounded-lg border divide-y text-sm">
                {report.clerk_only.map((u) => (
                  <div key={u.clerk_user_id} className="flex items-center justify-between px-3 py-2 gap-4">
                    <div className="min-w-0">
                      <p className="font-medium truncate">{u.display_name}</p>
                      <p className="text-xs text-muted-foreground overflow-hidden"><CopyEmail email={u.email} /></p>
                      <p className="text-xs text-muted-foreground font-mono">{u.clerk_user_id}</p>
                    </div>
                    <div className="flex gap-2 shrink-0">
                      {backfillResults[u.clerk_user_id] ? (
                        <span className="text-xs text-green-600 font-medium capitalize">
                          {backfillResults[u.clerk_user_id]}
                        </span>
                      ) : (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={backfilling === u.clerk_user_id}
                            onClick={() => handleBackfill(u.clerk_user_id, "user")}
                          >
                            Backfill as user
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={backfilling === u.clerk_user_id}
                            onClick={() => handleBackfill(u.clerk_user_id, "admin")}
                          >
                            Backfill as admin
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* In DB, not in Clerk */}
          <div className="space-y-2">
            <h3 className="text-sm font-medium">
              In DB, not in Clerk
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                ({report.db_only.length} {report.db_only.length === 1 ? "user" : "users"})
              </span>
            </h3>
            {report.db_only.length === 0 ? (
              <p className="text-xs text-muted-foreground">No orphaned DB records.</p>
            ) : (
              <div className="rounded-lg border divide-y text-sm">
                {report.db_only.map((u) => (
                  <div key={u.user_id} className="flex items-center justify-between px-3 py-2 gap-4">
                    <div className="min-w-0">
                      <p className="font-medium truncate">{u.display_name}</p>
                      <p className="text-xs text-muted-foreground overflow-hidden"><CopyEmail email={u.email} /></p>
                    </div>
                    {u.clerk_errored && (
                      <span className="text-xs bg-destructive/10 text-destructive px-2 py-0.5 rounded shrink-0">
                        clerk errored
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Scheduled Tasks tab
// ---------------------------------------------------------------------------

const CRON_PRESETS = [
  { label: "Hourly", value: "0 * * * *" },
  { label: "Daily (2 AM UTC)", value: "0 2 * * *" },
  { label: "Weekly (Sun 2 AM)", value: "0 2 * * 0" },
  { label: "Monthly (1st 2 AM)", value: "0 2 1 * *" },
  { label: "Custom", value: "custom" },
];

function ScheduledTaskCard({ task, onSaved }: { task: ScheduledTask; onSaved: () => void }) {
  const [enabled, setEnabled] = useState(task.enabled);
  const [preset, setPreset] = useState<string>(() => {
    const match = CRON_PRESETS.find((p) => p.value === task.cron && p.value !== "custom");
    return match ? match.value : "custom";
  });
  const [customCron, setCustomCron] = useState(task.cron);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const effectiveCron = preset === "custom" ? customCron : preset;
  const isDirty = enabled !== task.enabled || effectiveCron !== task.cron;

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await patchScheduledTask(task.name, { enabled, cron: effectiveCron });
      onSaved();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to save";
      setError(msg.includes("422") ? "Invalid cron expression" : msg);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="border rounded-lg p-3 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium text-sm">{task.display_name}</p>
          <p className="text-xs text-muted-foreground mt-0.5">{task.description}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <label className="flex items-center gap-2 cursor-pointer">
            <span className="text-xs text-muted-foreground">{enabled ? "Enabled" : "Disabled"}</span>
            <button
              role="switch"
              aria-checked={enabled}
              onClick={() => setEnabled((v) => !v)}
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                enabled ? "bg-primary" : "bg-muted"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                  enabled ? "translate-x-4" : "translate-x-0.5"
                }`}
              />
            </button>
          </label>
          {error && <p className="text-xs text-destructive">{error}</p>}
          <Button size="sm" disabled={!isDirty || saving} onClick={save}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-muted-foreground">Schedule:</span>
          <select
            value={preset}
            onChange={(e) => {
              setPreset(e.target.value);
              if (e.target.value !== "custom") setCustomCron(e.target.value);
            }}
            className="text-xs border rounded px-2 py-1 bg-background"
          >
            {CRON_PRESETS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
          {preset === "custom" && (
            <input
              type="text"
              value={customCron}
              onChange={(e) => setCustomCron(e.target.value)}
              placeholder="0 2 * * *"
              className="text-xs border rounded px-2 py-1 bg-background font-mono w-36"
            />
          )}
        </div>

        <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted-foreground">
          {task.next_runs.length > 0 && (
            <span>
              Next: {task.next_runs.slice(0, 3).map((r) => new Date(r).toLocaleString()).join(" · ")}
            </span>
          )}
          {task.last_fired_at && (
            <span>
              Last fired: {new Date(task.last_fired_at).toLocaleString()}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function ScheduledTasksTab() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "scheduled-tasks"],
    queryFn: listScheduledTasks,
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error) return <p className="text-sm text-destructive">Failed to load scheduled tasks.</p>;

  return (
    <div className="space-y-6">
      <div className="space-y-1 pb-2 border-b">
        <h1 className="text-lg font-semibold">Scheduled Tasks</h1>
        <p className="text-sm text-muted-foreground">Configure recurring background tasks. Schedules are stored in Postgres and survive restarts; the scheduler tick runs every 60 seconds via Celery Beat.</p>
      </div>
      {data && data.length === 0 && (
        <p className="text-sm text-muted-foreground">No scheduled tasks configured.</p>
      )}
      {data?.map((task) => (
        <ScheduledTaskCard
          key={task.name}
          task={task}
          onSaved={() => qc.invalidateQueries({ queryKey: ["admin", "scheduled-tasks"] })}
        />
      ))}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Data Exports tab
// ---------------------------------------------------------------------------

function ExportStatusBadge({ status }: { status: AdminExportRecord["status"] }) {
  const cls =
    status === "complete"
      ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
      : status === "failed"
        ? "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300"
        : "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300";
  return (
    <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${cls}`}>{status}</span>
  );
}

function ExportRow({ record, onDeleted }: { record: AdminExportRecord; onDeleted: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const mutation = useMutation({
    mutationFn: () => deleteExport(record.id),
    onSuccess: onDeleted,
  });

  const sizeMb =
    record.archive_size_bytes != null
      ? `${(record.archive_size_bytes / 1_048_576).toFixed(2)} MB`
      : "—";

  const fmt = (iso: string | null) =>
    iso ? new Date(iso).toLocaleString() : "—";

  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-medium truncate">
            {record.user_display_name || <span className="text-muted-foreground italic">no name</span>}
          </p>
          <p className="text-sm text-muted-foreground truncate">{record.user_email}</p>
        </div>
        <ExportStatusBadge status={record.status} />
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
        <span className="text-muted-foreground">Requested</span>
        <span>{fmt(record.requested_at)}</span>
        <span className="text-muted-foreground">Generated</span>
        <span>{fmt(record.completed_at)}</span>
        <span className="text-muted-foreground">Expires</span>
        <span>{fmt(record.expires_at)}</span>
        <span className="text-muted-foreground">Size</span>
        <span>{sizeMb}</span>
      </div>

      {record.status === "failed" && record.error && (
        <p className="text-xs text-destructive font-mono bg-destructive/10 rounded px-2 py-1 break-all">
          {record.error}
        </p>
      )}

      <div className="flex justify-end">
        {confirming ? (
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Delete this record and archive?</span>
            <Button
              size="sm"
              variant="destructive"
              disabled={mutation.isPending}
              onClick={() => mutation.mutate()}
            >
              {mutation.isPending ? "Deleting…" : "Confirm"}
            </Button>
            <Button size="sm" variant="outline" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <Button size="sm" variant="outline" onClick={() => setConfirming(true)}>
            Delete
          </Button>
        )}
      </div>
    </div>
  );
}

function ExportsTab() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "exports"],
    queryFn: listExports,
  });

  return (
    <div className="space-y-6">
      <div className="space-y-1 pb-2 border-b">
        <h1 className="text-lg font-semibold">Data Exports</h1>
        <p className="text-sm text-muted-foreground">
          All user data export requests. Archives are stored in R2 and expire after 7 days. Delete a record to
          immediately remove both the DB row and the archive object.
        </p>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground py-8 text-center">Loading…</p>}
      {error && <p className="text-sm text-destructive">Failed to load exports.</p>}

      {!isLoading && data && data.length === 0 && (
        <p className="text-sm text-muted-foreground py-8 text-center">No export requests found.</p>
      )}

      {data && data.length > 0 && (
        <div className="space-y-3">
          {data.map((record) => (
            <ExportRow
              key={record.id}
              record={record}
              onDeleted={() => qc.invalidateQueries({ queryKey: ["admin", "exports"] })}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Credentials tab
// ---------------------------------------------------------------------------

const RESOURCE_LABELS: Record<CredentialResource, string> = {
  smtp: "SMTP",
  s3: "S3 / R2",
  clerk: "Clerk",
  postgres: "PostgreSQL",
  app: "App Secret",
};

const RESOURCE_OPTIONS: CredentialResource[] = ["smtp", "s3", "clerk", "postgres", "app"];

function credentialStatus(daysRemaining: number | null): { label: string; cls: string } {
  if (daysRemaining === null) return { label: "No expiry", cls: "bg-muted text-muted-foreground" };
  if (daysRemaining < 0) return { label: "Expired", cls: "bg-destructive/10 text-destructive" };
  if (daysRemaining <= 7) return { label: "Critical", cls: "bg-destructive/10 text-destructive" };
  if (daysRemaining <= 30) return { label: "Warning", cls: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300" };
  return { label: "OK", cls: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300" };
}

const GROUP_CONFIG: Record<string, { label: string; fields: string[]; testService: string | null }> = {
  smtp: {
    label: "SMTP / Email",
    fields: ["smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from_email", "smtp_from_name"],
    testService: "smtp",
  },
  s3: {
    label: "S3 / Object Storage",
    fields: ["s3_endpoint_url", "s3_access_key_id", "s3_secret_access_key", "s3_bucket_name", "s3_region"],
    testService: "s3",
  },
  ravelry_read: {
    label: "Ravelry — Read key",
    fields: ["ravelry_read_access_username", "ravelry_read_access_key"],
    testService: "ravelry_read",
  },
  ravelry_oauth: {
    label: "Ravelry — OAuth app",
    fields: ["ravelry_oauth_client_id", "ravelry_oauth_client_secret", "ravelry_oauth_redirect_uri"],
    testService: null,
  },
  github: {
    label: "GitHub Feedback",
    fields: ["github_feedback_token", "github_feedback_repo"],
    testService: "github",
  },
  cloudflare: {
    label: "Cloudflare Zero Trust",
    fields: ["cf_zero_trust_enabled", "cf_access_client_id", "cf_access_client_secret"],
    testService: null,
  },
  webhook: {
    label: "Clerk Webhook",
    fields: ["webhook_base_url", "clerk_webhook_secret"],
    testService: null,
  },
  geoip: {
    label: "GeoIP (MaxMind)",
    fields: ["maxmind_license_key"],
    testService: null,
  },
  otel: {
    label: "OpenTelemetry",
    fields: ["otel_exporter_otlp_endpoint"],
    testService: null,
  },
};

const CONFIG_SECRET_FIELDS = new Set([
  "smtp_password",
  "s3_secret_access_key",
  "cf_access_client_secret",
  "ravelry_read_access_key",
  "ravelry_oauth_client_secret",
  "github_feedback_token",
  "clerk_webhook_secret",
  "maxmind_license_key",
]);

// These secrets show prefix + •••••••• when set and reveal as plain text when editing.
// All other secrets use a standard password field (value always blank).
const PREFIX_MASKED_FIELDS = new Set(["clerk_webhook_secret", "maxmind_license_key"]);

const BOOLEAN_FIELDS = new Set(["cf_zero_trust_enabled"]);

const CONFIG_FIELD_LABELS: Record<string, string> = {
  smtp_host: "SMTP Host",
  smtp_port: "SMTP Port",
  smtp_user: "SMTP User",
  smtp_password: "SMTP Password",
  smtp_from_email: "From Email",
  smtp_from_name: "From Name",
  s3_endpoint_url: "Endpoint URL",
  s3_access_key_id: "Access Key ID",
  s3_secret_access_key: "Secret Access Key",
  s3_bucket_name: "Bucket Name",
  s3_region: "Region",
  ravelry_read_access_username: "Username",
  ravelry_read_access_key: "API Key",
  ravelry_oauth_client_id: "OAuth Client ID",
  ravelry_oauth_client_secret: "OAuth Client Secret",
  ravelry_oauth_redirect_uri: "Redirect URI",
  github_feedback_token: "Personal Access Token",
  github_feedback_repo: "Repository",
  cf_zero_trust_enabled: "Zero Trust Enabled",
  cf_access_client_id: "Access Client ID",
  cf_access_client_secret: "Access Client Secret",
  clerk_webhook_secret: "Signing Secret",
  webhook_base_url: "Base URL",
  maxmind_license_key: "License Key",
  otel_exporter_otlp_endpoint: "OTLP Endpoint",
};

function ConfigSection() {
  const qc = useQueryClient();
  const { data: configState, isLoading } = useQuery({
    queryKey: ["admin", "config"],
    queryFn: getConfig,
    staleTime: 30_000,
  });

  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [testResults, setTestResults] = useState<Record<string, ConfigTestResult | null>>({});
  const [testingGroup, setTestingGroup] = useState<string | null>(null);
  const [savingGroup, setSavingGroup] = useState<string | null>(null);
  const [saveErrors, setSaveErrors] = useState<Record<string, string>>({});
  const [editingFields, setEditingFields] = useState<Set<string>>(new Set());

  const fieldMap = Object.fromEntries((configState?.fields ?? []).map((f) => [f.field, f]));

  function clearGroupDrafts(groupKey: string) {
    const fields = GROUP_CONFIG[groupKey].fields;
    setDrafts((prev) => {
      const next = { ...prev };
      fields.forEach((f) => delete next[f]);
      return next;
    });
    setEditingFields((prev) => {
      const next = new Set(prev);
      fields.forEach((f) => next.delete(f));
      return next;
    });
    setTestResults((prev) => ({ ...prev, [groupKey]: null }));
    setSaveErrors((prev) => ({ ...prev, [groupKey]: "" }));
  }

  async function handleSave(groupKey: string) {
    const fields = GROUP_CONFIG[groupKey].fields;
    const values: Record<string, string | null> = {};
    for (const field of fields) {
      if (field in drafts) values[field] = drafts[field] || null;
    }
    if (Object.keys(values).length === 0) return;
    setSavingGroup(groupKey);
    setSaveErrors((prev) => ({ ...prev, [groupKey]: "" }));
    try {
      const result = await saveConfig(values);
      qc.setQueryData(["admin", "config"], result);
      clearGroupDrafts(groupKey);
    } catch (e) {
      setSaveErrors((prev) => ({ ...prev, [groupKey]: e instanceof Error ? e.message : "Save failed" }));
    } finally {
      setSavingGroup(null);
    }
  }

  async function handleTest(groupKey: string) {
    setTestingGroup(groupKey);
    setTestResults((prev) => ({ ...prev, [groupKey]: null }));
    const svc = GROUP_CONFIG[groupKey].testService!;
    const testValues: Record<string, string | null> = {};
    for (const field of GROUP_CONFIG[groupKey].fields) {
      if (field in drafts) {
        testValues[field] = drafts[field] || null;
      } else {
        const f = fieldMap[field];
        testValues[field] = (f && !CONFIG_SECRET_FIELDS.has(field)) ? (f.value ?? null) : null;
      }
    }
    try {
      const result = await testConfigService(svc, testValues);
      setTestResults((prev) => ({ ...prev, [groupKey]: result }));
    } catch (e) {
      setTestResults((prev) => ({
        ...prev,
        [groupKey]: { ok: false, message: e instanceof Error ? e.message : "Test failed" },
      }));
    } finally {
      setTestingGroup(null);
    }
  }

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading configuration…</p>;
  if (!configState) return null;

  const unpopulatedGroups = Object.entries(GROUP_CONFIG)
    .map(([, { label, fields }]) => ({
      label,
      missing: fields.filter((f) => {
        const s = fieldMap[f];
        return s && (CONFIG_SECRET_FIELDS.has(f) ? !s.secret_set : !s.value);
      }),
    }))
    .filter((g) => g.missing.length > 0);

  return (
    <div className="space-y-6 pt-6">
      <div className="space-y-1 pb-2 border-b">
        <h2 className="text-base font-semibold">Integration Settings</h2>
        <p className="text-xs text-muted-foreground">
          Optional service credentials stored encrypted on disk. Fields with an ENV badge are sourced from environment variables and take priority at runtime.
          Saved changes require a process restart to take effect.
        </p>
      </div>

      {unpopulatedGroups.length > 0 && (
        <div className="rounded-md border border-border bg-muted/40 px-4 py-3 space-y-1.5">
          <p className="text-xs font-medium">Optional services not fully configured:</p>
          {unpopulatedGroups.map(({ label, missing }) => (
            <p key={label} className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">{label}</span>
              {" — "}
              {missing.map((f) => CONFIG_FIELD_LABELS[f] ?? f).join(", ")}
            </p>
          ))}
        </div>
      )}

      {Object.entries(GROUP_CONFIG).map(([groupKey, { label, fields, testService }]) => {
        const isDirty = fields.some((f) => f in drafts);
        const saveError = saveErrors[groupKey];
        const testResult = testResults[groupKey];

        return (
          <div key={groupKey} className="border rounded-lg overflow-hidden">
            <div className="px-4 py-2.5 bg-muted/30 border-b">
              <h3 className="text-sm font-medium">{label}</h3>
            </div>
            <div className="p-4 space-y-3">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {fields.map((field) => {
                  const state = fieldMap[field];
                  const isBoolean = BOOLEAN_FIELDS.has(field);
                  const isSecret = CONFIG_SECRET_FIELDS.has(field);
                  const fromEnv = state?.source === "env";
                  const hasDraft = field in drafts;
                  const isSet = isSecret ? (state?.secret_set ?? false) : !!(state?.value);
                  const isFullWidth = fields.length === 1
                    || field === "smtp_from_email"
                    || field === "ravelry_oauth_redirect_uri"
                    || field === "webhook_base_url"
                    || field === "otel_exporter_otlp_endpoint";

                  if (isBoolean) {
                    const isOn = hasDraft
                      ? drafts[field] === "true"
                      : (state?.value === "True" || state?.value === "true");
                    return (
                      <div key={field} className={`flex items-center justify-between gap-3 py-1 ${isFullWidth ? "sm:col-span-2" : ""}`}>
                        <div className="flex items-center gap-1.5">
                          <label className="text-xs font-medium">{CONFIG_FIELD_LABELS[field] ?? field}</label>
                          {fromEnv && (
                            <span className="text-[10px] border rounded px-1 text-blue-600 dark:text-blue-400 border-blue-300 dark:border-blue-700 leading-4">ENV</span>
                          )}
                        </div>
                        <button
                          type="button"
                          role="switch"
                          aria-checked={isOn}
                          onClick={() => setDrafts((prev) => ({ ...prev, [field]: isOn ? "false" : "true" }))}
                          className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${isOn ? "bg-accent" : "bg-input"}`}
                        >
                          <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform ${isOn ? "translate-x-4" : "translate-x-0.5"}`} />
                        </button>
                      </div>
                    );
                  }

                  const isPrefixMasked = PREFIX_MASKED_FIELDS.has(field);
                  const isEditing = editingFields.has(field);
                  const showMasked = isPrefixMasked && isSet && !hasDraft && !isEditing;

                  return (
                    <div key={field} className={isFullWidth ? "sm:col-span-2" : ""}>
                      <div className="flex items-center gap-1.5 mb-1">
                        <label className="text-xs font-medium">{CONFIG_FIELD_LABELS[field] ?? field}</label>
                        {fromEnv && (
                          <span className="text-[10px] border rounded px-1 text-blue-600 dark:text-blue-400 border-blue-300 dark:border-blue-700 leading-4">
                            ENV
                          </span>
                        )}
                        {isSecret && isSet && !hasDraft && (
                          <span className="text-[10px] text-green-600 dark:text-green-400">set</span>
                        )}
                      </div>
                      {showMasked ? (
                        <div
                          className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm font-mono text-muted-foreground cursor-text select-none"
                          onClick={() => setEditingFields((prev) => new Set([...prev, field]))}
                          title="Click to change"
                        >
                          {state?.secret_prefix ? state.secret_prefix + "••••••••" : "••••••••"}
                        </div>
                      ) : (
                        <input
                          type={isPrefixMasked ? "text" : isSecret ? "password" : "text"}
                          className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring font-mono"
                          value={isSecret ? (hasDraft ? drafts[field] : "") : (hasDraft ? drafts[field] : (state?.value ?? ""))}
                          placeholder={isSecret && isSet ? "Enter new value to replace" : ""}
                          onChange={(e) => setDrafts((prev) => ({ ...prev, [field]: e.target.value }))}
                          autoComplete="off"
                          autoFocus={isPrefixMasked && isEditing && !hasDraft}
                        />
                      )}
                      {fromEnv && hasDraft && (
                        <p className="text-[11px] text-amber-600 dark:text-amber-400 mt-0.5">
                          ENV var active — file value won't take effect until removed from .env
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>

              {saveError && <p className="text-xs text-destructive">{saveError}</p>}
              {testResult && (
                <p className={`text-xs ${testResult.ok ? "text-green-600 dark:text-green-400" : "text-destructive"}`}>
                  {testResult.ok ? "✓" : "✗"} {testResult.message}
                </p>
              )}

              <div className="flex items-center gap-2 pt-1 border-t">
                {testService && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 px-2 text-xs"
                    disabled={testingGroup === groupKey}
                    onClick={() => handleTest(groupKey)}
                  >
                    {testingGroup === groupKey ? "Testing…" : "Test"}
                  </Button>
                )}
                <div className="flex-1" />
                {isDirty && (
                  <button
                    className="text-xs text-muted-foreground hover:text-foreground"
                    onClick={() => clearGroupDrafts(groupKey)}
                  >
                    Discard
                  </button>
                )}
                <Button
                  size="sm"
                  className="h-7 px-3 text-xs"
                  disabled={!isDirty || savingGroup === groupKey}
                  onClick={() => handleSave(groupKey)}
                >
                  {savingGroup === groupKey ? "Saving…" : "Save"}
                </Button>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CredentialsTab() {
  const queryClient = useQueryClient();

  const { data: credentials = [], isLoading } = useQuery({
    queryKey: ["admin", "credentials"],
    queryFn: listCredentials,
  });

  const [editing, setEditing] = useState<CredentialExpiry | null>(null);
  const [adding, setAdding] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<CredentialExpiry | null>(null);
  const [formName, setFormName] = useState("");
  const [formResource, setFormResource] = useState<CredentialResource>("smtp");
  const [formExpiry, setFormExpiry] = useState("");
  const [formNotes, setFormNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function openAdd() {
    setFormName(""); setFormResource("smtp"); setFormExpiry(""); setFormNotes("");
    setError(null); setAdding(true);
  }

  function openEdit(c: CredentialExpiry) {
    setFormName(c.name);
    setFormResource(c.resource);
    setFormExpiry(c.expires_on ?? "");
    setFormNotes(c.notes ?? "");
    setError(null);
    setEditing(c);
  }

  function closeForm() { setAdding(false); setEditing(null); setError(null); }

  async function handleSave() {
    if (!formName.trim()) { setError("Name is required"); return; }
    setSaving(true); setError(null);
    try {
      const body = {
        name: formName.trim(),
        resource: formResource,
        expires_on: formExpiry || null,
        notes: formNotes.trim() || null,
      };
      if (adding) {
        await createCredential(body);
      } else if (editing) {
        await patchCredential(editing.id, body);
      }
      queryClient.invalidateQueries({ queryKey: ["admin", "credentials"] });
      closeForm();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteCredential(deleteTarget.id);
      queryClient.invalidateQueries({ queryKey: ["admin", "credentials"] });
      setDeleteTarget(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete");
    } finally {
      setDeleting(false);
    }
  }

  const sorted = [...credentials].sort((a, b) => {
    if (a.days_remaining === null && b.days_remaining === null) return 0;
    if (a.days_remaining === null) return 1;
    if (b.days_remaining === null) return -1;
    return a.days_remaining - b.days_remaining;
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="space-y-1 pb-2 border-b flex-1 mr-4">
          <h1 className="text-lg font-semibold">Credentials</h1>
          <p className="text-sm text-muted-foreground">Track expiration dates for secrets and third-party service credentials.</p>
        </div>
        <Button size="sm" onClick={openAdd}>Add credential</Button>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : sorted.length === 0 ? (
        <p className="text-sm text-muted-foreground">No credentials tracked yet.</p>
      ) : (
        <div className="rounded-md border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">Name</th>
                <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">Service</th>
                <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">Expires</th>
                <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">Status</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {sorted.map((c) => {
                const { label, cls } = credentialStatus(c.days_remaining);
                return (
                  <tr key={c.id} className="hover:bg-muted/50">
                    <td className="px-3 py-2.5 font-medium">{c.name}</td>
                    <td className="px-3 py-2.5 text-muted-foreground">{RESOURCE_LABELS[c.resource]}</td>
                    <td className="px-3 py-2.5 text-muted-foreground">
                      {c.expires_on
                        ? <>
                            {new Date(c.expires_on).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}
                            {c.days_remaining !== null && (
                              <span className="ml-1.5 text-xs text-muted-foreground">
                                ({c.days_remaining < 0 ? `${Math.abs(c.days_remaining)}d ago` : `${c.days_remaining}d`})
                              </span>
                            )}
                          </>
                        : <span className="text-muted-foreground">Never</span>}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${cls}`}>{label}</span>
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <button className="text-xs text-muted-foreground hover:text-foreground mr-3" onClick={() => openEdit(c)}>Edit</button>
                      <button className="text-xs text-destructive hover:text-destructive/80" onClick={() => setDeleteTarget(c)}>Delete</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <ConfigSection />

      {(adding || editing) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-lg border bg-background shadow-lg p-6 space-y-4">
            <h3 className="font-semibold">{adding ? "Add credential" : "Edit credential"}</h3>
            <div>
              <label className="mb-1 block text-sm font-medium">Name <span className="text-destructive">*</span></label>
              <input className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring" value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="Clerk Secret Key" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Service</label>
              <select className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring" value={formResource} onChange={(e) => setFormResource(e.target.value as CredentialResource)}>
                {RESOURCE_OPTIONS.map((r) => <option key={r} value={r}>{RESOURCE_LABELS[r]}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Expiration date <span className="text-muted-foreground font-normal">(optional)</span></label>
              <input type="date" className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring" value={formExpiry} onChange={(e) => setFormExpiry(e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Notes <span className="text-muted-foreground font-normal">(optional)</span></label>
              <textarea className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring" rows={2} value={formNotes} onChange={(e) => setFormNotes(e.target.value)} placeholder="Rotation instructions, link to vault, etc." />
            </div>
            {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
            <div className="flex justify-end gap-2 pt-1">
              <Button type="button" variant="outline" onClick={closeForm} disabled={saving}>Cancel</Button>
              <Button onClick={handleSave} disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
            </div>
          </div>
        </div>
      )}

      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-lg border bg-background shadow-lg p-6 space-y-4">
            <h3 className="font-semibold">Delete credential?</h3>
            <p className="text-sm text-muted-foreground">This will permanently remove <strong>{deleteTarget.name}</strong> from the tracking list.</p>
            {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setDeleteTarget(null)} disabled={deleting}>Cancel</Button>
              <Button variant="destructive" onClick={handleDelete} disabled={deleting}>{deleting ? "Deleting…" : "Delete"}</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function SandboxTab() {
  const [lastError, setLastError] = React.useState<string | null>(null);

  function throwTestError() {
    try {
      throw new Error("Sentry test error — triggered from Superuser Sandbox");
    } catch (err) {
      Sentry.captureException(err);
      setLastError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Sandbox</h2>
        <p className="text-sm text-muted-foreground mt-1">Internal diagnostics and integration tests. Not visible to regular users.</p>
      </div>

      <div className="rounded-md border border-border p-4 space-y-3">
        <h3 className="text-sm font-medium">Sentry error tracking</h3>
        <p className="text-xs text-muted-foreground">Captures a test exception and sends it to Sentry. Use this to verify the DSN is wired correctly.</p>
        <div className="flex items-center gap-3">
          <Button variant="destructive" size="sm" onClick={throwTestError}>
            Send test error to Sentry
          </Button>
          {lastError && (
            <span className="text-xs text-muted-foreground">Sent: <code className="font-mono">{lastError}</code></span>
          )}
        </div>
      </div>
    </div>
  );
}

export function SuperuserPage() {
  const { section = "eula" } = useParams<{ section: string }>();
  const activeSection = section as SuperuserSection;

  const { data: configState } = useQuery({
    queryKey: ["admin", "config"],
    queryFn: getConfig,
    staleTime: 30_000,
  });

  return (
    <div className="p-6 max-w-4xl mx-auto w-full space-y-6">
      <CveBanner />

      {configState?.restart_pending && (
        <div className="rounded-md border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-900/20 px-4 py-3 flex items-start gap-3">
          <span className="text-amber-600 dark:text-amber-400 shrink-0 mt-0.5">⚠</span>
          <div>
            <p className="text-sm font-medium text-amber-800 dark:text-amber-300">Restart required</p>
            <p className="text-xs text-amber-700 dark:text-amber-400 mt-0.5">
              Integration settings were updated. Saved values will take effect after the next process restart.
            </p>
          </div>
        </div>
      )}

      {activeSection === "eula" && <EulaTab />}
      {activeSection === "storage" && <StorageAuditTab />}
      {activeSection === "cve" && <CveScanTab />}
      {activeSection === "workers" && <WorkersTab />}
      {activeSection === "deletion" && <DeletionTab />}
      {activeSection === "reconcile" && <ReconcileTab />}
      {activeSection === "maintenance" && <MaintenanceTab />}
      {activeSection === "schedule" && <ScheduledTasksTab />}
      {activeSection === "exports" && <ExportsTab />}
      {activeSection === "credentials" && <CredentialsTab />}
      {activeSection === "sandbox" && <SandboxTab />}
    </div>
  );
}
