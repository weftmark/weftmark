import { useState } from "react";
import { useParams } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { useQuery } from "@tanstack/react-query";
import { updateSettings, deleteAccount, getDataExport, getCurrentEula } from "@/api/users";
import { listProjects } from "@/api/projects";
import { Button } from "@/components/ui/button";
import { EulaContent } from "@/components/EulaContent";

type Section = "appearance" | "preferences" | "privacy" | "terms" | "account";

export function SettingsPage() {
  const { user, refetch } = useAuth();
  const { section } = useParams<{ section: string }>();
  const activeSection: Section = (section as Section) ?? "appearance";

  const { data: projects = [] } = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
  });
  const sharedProjectCount = projects.filter((p) => p.is_shared).length;

  const { data: currentEula } = useQuery({
    queryKey: ["eula", "current"],
    queryFn: getCurrentEula,
    staleTime: 5 * 60 * 1000,
  });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Form state mirrors user fields
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [theme, setTheme] = useState(user?.theme ?? "light");
  const [activityTheme, setActivityTheme] = useState(user?.activity_theme ?? "default");
  const [idleTimeout, setIdleTimeout] = useState(user?.idle_timeout_minutes ?? 30);
  const [measurementSystem, setMeasurementSystem] = useState(user?.measurement_system ?? "metric");
  const [dataConsent, setDataConsent] = useState(user?.ai_training_consent ?? false);

  // Privacy toggle warning state
  const [showConsentWarning, setShowConsentWarning] = useState(false);

  // EULA read state
  const [showEula, setShowEula] = useState(false);

  // Danger zone state
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteInput, setDeleteInput] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [exportInfo, setExportInfo] = useState<string | null>(null);

  if (!user) return null;

  async function save(patch: Parameters<typeof updateSettings>[0]) {
    setSaving(true);
    setSaveError(null);
    setSaveSuccess(false);
    try {
      await updateSettings(patch);
      refetch();
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  function handleConsentToggle(value: boolean) {
    if (!value && dataConsent) {
      // Turning off — warn about sharing impact
      setShowConsentWarning(true);
    } else {
      setDataConsent(value);
      save({ ai_training_consent: value });
    }
  }

  function confirmConsentOptOut() {
    setDataConsent(false);
    setShowConsentWarning(false);
    save({ ai_training_consent: false });
  }

  async function handleDeleteAccount() {
    if (deleteInput !== "DELETE MY ACCOUNT") return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteAccount("DELETE MY ACCOUNT");
      window.location.href = "/login";
    } catch (e: unknown) {
      setDeleteError(e instanceof Error ? e.message : "Failed to delete account");
      setDeleting(false);
    }
  }

  async function handleDataExport() {
    try {
      const result = await getDataExport();
      setExportInfo(result.message);
    } catch {
      setExportInfo("Could not fetch export status.");
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
        <div className="space-y-6">
            {(saveSuccess || saveError) && (
              <div
                className={`rounded-md px-4 py-2 text-sm ${
                  saveSuccess
                    ? "bg-green-500/10 text-green-700 dark:text-green-400"
                    : "bg-destructive/10 text-destructive"
                }`}
              >
                {saveSuccess ? "Saved" : saveError}
              </div>
            )}

            {/* ── Appearance ── */}
            {activeSection === "appearance" && (
              <Section title="Appearance">
                <Field label="Theme">
                  <div className="flex gap-2">
                    {(["light", "dark", "system"] as const).map((t) => (
                      <button
                        key={t}
                        onClick={() => {
                          setTheme(t);
                          save({ theme: t });
                        }}
                        className={`rounded-md border px-4 py-2 text-sm capitalize transition-colors ${
                          theme === t
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-border hover:bg-accent"
                        }`}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                </Field>

                <Field label="Activity tracker style">
                  <select
                    value={activityTheme}
                    onChange={(e) => {
                      setActivityTheme(e.target.value);
                      save({ activity_theme: e.target.value || null });
                    }}
                    className="rounded-md border border-border bg-background px-3 py-2 text-sm"
                  >
                    <option value="default">Default</option>
                    <option value="compact">Compact</option>
                    <option value="high_contrast">High contrast</option>
                  </select>
                  <p className="text-xs text-muted-foreground mt-1">
                    Controls the visual density of the pick-by-pick tracker.
                  </p>
                </Field>
              </Section>
            )}

            {/* ── Preferences ── */}
            {activeSection === "preferences" && (
              <Section title="Preferences">
                <Field label="Display name">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm"
                      maxLength={255}
                    />
                    <Button
                      size="sm"
                      onClick={() => save({ display_name: displayName })}
                      disabled={saving || displayName === user.display_name}
                    >
                      Save
                    </Button>
                  </div>
                </Field>

                <Field label="Measurement system">
                  <div className="flex gap-2">
                    {(["metric", "imperial"] as const).map((m) => (
                      <button
                        key={m}
                        onClick={() => {
                          setMeasurementSystem(m);
                          save({ measurement_system: m });
                        }}
                        className={`rounded-md border px-4 py-2 text-sm capitalize transition-colors ${
                          measurementSystem === m
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-border hover:bg-accent"
                        }`}
                      >
                        {m}
                      </button>
                    ))}
                  </div>
                </Field>

                <Field label="Session idle timeout">
                  <select
                    value={idleTimeout}
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      setIdleTimeout(v);
                      save({ idle_timeout_minutes: v });
                    }}
                    className="rounded-md border border-border bg-background px-3 py-2 text-sm"
                  >
                    <option value={15}>15 minutes</option>
                    <option value={30}>30 minutes</option>
                    <option value={60}>1 hour</option>
                    <option value={120}>2 hours</option>
                  </select>
                </Field>
              </Section>
            )}

            {/* ── Privacy & data ── */}
            {activeSection === "privacy" && (
              <Section title="Privacy & data">
                <Field label="Opt out of data use">
                  <p className="text-xs text-muted-foreground">
                    Per our Terms of Service, your data is used for platform improvements by default.
                    Toggle on to opt out.
                  </p>
                  <div className="flex items-center gap-3 mt-2">
                    <button
                      role="switch"
                      aria-checked={!dataConsent}
                      onClick={() => handleConsentToggle(!dataConsent)}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                        !dataConsent ? "bg-primary" : "bg-input"
                      }`}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                          !dataConsent ? "translate-x-6" : "translate-x-1"
                        }`}
                      />
                    </button>
                    <span className="text-sm">{!dataConsent ? "Opted out" : "Participating (default)"}</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    Your content, settings, and tags — including WIF files, photos, and activity
                    data — may be used for AI/ML model training and feature improvements as described
                    in the Terms of Service.
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    <strong>Note:</strong> Opting out also disables all public sharing links for your projects.
                  </p>
                </Field>

                {showConsentWarning && (
                  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
                    <div className="w-full max-w-md rounded-xl border bg-background shadow-xl space-y-4 p-6">
                      <h2 className="text-base font-semibold">Opt out of data use?</h2>

                      <p className="text-sm text-muted-foreground">
                        Opting out stops future use of your data for AI/ML model training and
                        feature improvements. Data already used in model training cannot be
                        retroactively removed.
                      </p>

                      <div className="rounded-md bg-amber-500/10 border border-amber-500/30 px-4 py-3 space-y-1.5">
                        <p className="text-sm font-medium text-amber-700 dark:text-amber-400">
                          The following will be disabled immediately:
                        </p>
                        <ul className="text-sm text-muted-foreground list-disc list-inside space-y-1">
                          <li>
                            Public sharing links for all your projects
                            {sharedProjectCount > 0 && (
                              <span className="font-medium text-foreground">
                                {" "}({sharedProjectCount} currently active)
                              </span>
                            )}
                          </li>
                          <li>Any future sharing features tied to your account</li>
                        </ul>
                        {sharedProjectCount > 0 && (
                          <p className="text-xs text-amber-700 dark:text-amber-400 pt-1">
                            Anyone with your current sharing links will immediately lose access.
                          </p>
                        )}
                      </div>

                      <p className="text-xs text-muted-foreground">
                        You can opt back in at any time from this page. Re-opting in restores
                        sharing access but does not re-enable individual project links — you will
                        need to re-share those manually.
                      </p>

                      <div className="flex gap-2 pt-1">
                        <Button variant="destructive" size="sm" onClick={confirmConsentOptOut}>
                          Opt out and disable sharing
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setShowConsentWarning(false)}
                        >
                          Cancel
                        </Button>
                      </div>
                    </div>
                  </div>
                )}

                <div className="rounded-md bg-muted px-4 py-3 text-xs text-muted-foreground space-y-1">
                  <p className="font-medium text-foreground">What we store about you</p>
                  <ul className="list-disc list-inside space-y-0.5">
                    <li>Email address and display name (from your sign-in provider)</li>
                    <li>WIF files, loom records, activities, photos, and yarn you create</li>
                    <li>Settings, tags, and metadata you assign to your content</li>
                    <li>Last active timestamp</li>
                  </ul>
                  <p className="pt-1">We never sell your data. See our Terms of Service for the full policy.</p>
                </div>
              </Section>
            )}

            {/* ── Terms ── */}
            {activeSection === "terms" && (
              <Section title="Terms of Service">
                <div className="space-y-3">
                  <div className="flex items-center justify-between rounded-lg border p-4">
                    <div>
                      <p className="text-sm font-medium">
                        WeftMark Terms of Service v{user.current_eula_version}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {user.eula_accepted_version === user.current_eula_version
                          ? "You have accepted the current version."
                          : "You have not yet accepted the current version."}
                      </p>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => setShowEula(!showEula)}>
                      {showEula ? "Hide" : "Read terms"}
                    </Button>
                  </div>

                  {showEula && currentEula && (
                    <div className="rounded-lg border p-4 max-h-[50vh] overflow-y-auto">
                      <EulaContent bodyHtml={currentEula.body_html} />
                    </div>
                  )}
                </div>
              </Section>
            )}

            {/* ── Account ── */}
            {activeSection === "account" && (
              <Section title="Account management">
                <Field label="Download my data">
                  <Button variant="outline" size="sm" onClick={handleDataExport}>
                    Request data archive
                  </Button>
                  {exportInfo && (
                    <p className="text-xs text-muted-foreground mt-2">{exportInfo}</p>
                  )}
                  <p className="text-xs text-muted-foreground mt-1">
                    Data export is planned for Milestone 2. Currently returns status only.
                  </p>
                </Field>

                <div className="rounded-lg border border-destructive/30 p-4 space-y-3">
                  <p className="text-sm font-medium text-destructive">Danger zone</p>
                  <p className="text-sm text-muted-foreground">
                    Permanently delete your account and all data: WIF files, photos, activity
                    records, looms, yarn, and projects. This cannot be undone.
                  </p>

                  {!showDeleteConfirm ? (
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => setShowDeleteConfirm(true)}
                    >
                      Delete my account
                    </Button>
                  ) : (
                    <div className="space-y-3">
                      <p className="text-sm">
                        Type <strong>DELETE MY ACCOUNT</strong> to confirm:
                      </p>
                      <input
                        type="text"
                        value={deleteInput}
                        onChange={(e) => setDeleteInput(e.target.value)}
                        placeholder="DELETE MY ACCOUNT"
                        className="w-full rounded-md border border-destructive/50 bg-background px-3 py-2 text-sm"
                      />
                      {deleteError && (
                        <p className="text-xs text-destructive">{deleteError}</p>
                      )}
                      <div className="flex gap-2">
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={handleDeleteAccount}
                          disabled={deleteInput !== "DELETE MY ACCOUNT" || deleting}
                        >
                          {deleting ? "Deleting…" : "Permanently delete my account"}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setShowDeleteConfirm(false);
                            setDeleteInput("");
                            setDeleteError(null);
                          }}
                          disabled={deleting}
                        >
                          Cancel
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              </Section>
            )}
        </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-5">
      <h2 className="text-base font-semibold border-b pb-2">{title}</h2>
      {children}
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">{label}</label>
      {children}
    </div>
  );
}

type ReactNode = import("react").ReactNode;
