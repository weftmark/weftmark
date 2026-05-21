import { useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LanguageSelector } from "@/components/LanguageSelector";
import { useAuth } from "@/hooks/useAuth";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { updateSettings, deleteAccount, requestDataExport, getDataExportStatus, getDataExportDownloadUrl, getCurrentEula } from "@/api/users";
import { downloadAuthed } from "@/api/client";
import { listDrafts } from "@/api/drafts";
import { listMyFeedback, SUBMISSION_TYPE_LABELS, type FeedbackRecord } from "@/api/feedback";
import { Button } from "@/components/ui/button";
import { EulaContent } from "@/components/EulaContent";
import { AppIcons } from "@/lib/icons";
import { TrackerStylePreview, TrackerLivePreview } from "@/components/TrackerStylePreview";

type Section = "appearance" | "preferences" | "privacy" | "terms" | "account" | "feedback-history";

export function SettingsPage() {
  const { t } = useTranslation();
  const { user, refetch } = useAuth();
  const { section } = useParams<{ section: string }>();
  const activeSection: Section = (section as Section) ?? "appearance";

  const { data: drafts = [] } = useQuery({
    queryKey: ["drafts"],
    queryFn: () => listDrafts(),
  });
  const sharedDraftCount = drafts.filter((d) => d.is_shared).length;

  const { data: currentEula } = useQuery({
    queryKey: ["eula", "current"],
    queryFn: getCurrentEula,
    staleTime: 5 * 60 * 1000,
  });

  const queryClient = useQueryClient();
  const { data: exportStatus } = useQuery({
    queryKey: ["export-status"],
    queryFn: getDataExportStatus,
    refetchInterval: (query) => (query.state.data?.status === "pending" ? 5000 : false),
    enabled: activeSection === "account",
  });
  const requestExportMutation = useMutation({
    mutationFn: requestDataExport,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["export-status"] }),
  });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Form state mirrors user fields
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [theme, setTheme] = useState(user?.theme ?? "light");
  const [activityTheme, setActivityTheme] = useState<"default" | "compact" | "high_contrast">(
    (user?.activity_theme as "default" | "compact" | "high_contrast") ?? "default"
  );
  const [trackerColorMode, setTrackerColorMode] = useState(user?.tracker_color_mode ?? "strip");
  const [trackerShowWeftColor, setTrackerShowWeftColor] = useState(user?.tracker_show_weft_color ?? true);
  const [trackerShowDrawdown, setTrackerShowDrawdown] = useState(user?.tracker_show_drawdown ?? true);
  const [trackerShowProgress, setTrackerShowProgress] = useState(user?.tracker_show_progress ?? true);
  const [trackerShowPickCards, setTrackerShowPickCards] = useState(user?.tracker_show_pick_cards ?? true);
  const [showVersionNumbers, setShowVersionNumbers] = useState(user?.show_version_numbers ?? true);
  const [hideUnusedShaftsTreadles, setHideUnusedShaftsTreadles] = useState(user?.hide_unused_shafts_treadles ?? false);
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

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
        {(saveSuccess || saveError) && (
          <div
            className={`fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-md px-4 py-2 text-sm shadow-lg ${
              saveSuccess
                ? "bg-green-500/10 text-green-700 dark:text-green-400"
                : "bg-destructive/10 text-destructive"
            }`}
          >
            {saveSuccess ? t("settings.saved") : saveError}
          </div>
        )}
        <div className="space-y-6">

            {/* ── Appearance ── */}
            {activeSection === "appearance" && (
              <>
              <Section title={t("settings.sections.appearance")}>
                <Field label={t("settings.appearance.theme")}>
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

                <Field label={t("settings.appearance.activityTrackerStyle")}>
                  <div className="flex flex-col gap-3 mt-1">
                    {(["default", "compact", "high_contrast"] as const).map((s) => {
                      const meta: Record<string, { label: string; desc: string }> = {
                        default: { label: t("settings.appearance.activityStyles.default.label"), desc: t("settings.appearance.activityStyles.default.desc") },
                        compact: { label: t("settings.appearance.activityStyles.compact.label"), desc: t("settings.appearance.activityStyles.compact.desc") },
                        high_contrast: { label: t("settings.appearance.activityStyles.high_contrast.label"), desc: t("settings.appearance.activityStyles.high_contrast.desc") },
                      };
                      const selected = activityTheme === s;
                      return (
                        <button
                          key={s}
                          onClick={() => { setActivityTheme(s); save({ activity_theme: s }); }}
                          className={`rounded-lg border-2 p-3 text-left transition-colors focus:outline-none focus:ring-2 focus:ring-ring ${
                            selected ? "border-primary bg-primary/5" : "border-border hover:border-primary/50"
                          }`}
                        >
                          <div className="mb-2">
                            <p className={`text-sm font-semibold ${selected ? "text-primary" : "text-foreground"}`}>
                              {meta[s].label}
                              {selected && <span className="ml-2 text-xs font-normal text-primary/70">{t("settings.appearance.active")}</span>}
                            </p>
                            <p className="text-xs text-muted-foreground mt-0.5">{meta[s].desc}</p>
                          </div>
                          <TrackerStylePreview style={s} />
                        </button>
                      );
                    })}
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    {t("settings.appearance.styleVariantNote")}
                  </p>
                </Field>

                <Field label={t("settings.appearance.trackerDefaults")}>
                  <p className="text-xs text-muted-foreground mb-3">
                    {t("settings.appearance.trackerDefaultsHelp")}
                  </p>

                  {/* Color mode */}
                  <div className="mb-4">
                    <p className="text-xs font-medium text-muted-foreground mb-1.5">{t("settings.appearance.colorMode")}</p>
                    <div className="inline-flex rounded-md border border-input overflow-hidden text-sm">
                      {(["theme", "strip", "filled"] as const).map((mode) => (
                        <button
                          key={mode}
                          onClick={() => { setTrackerColorMode(mode); save({ tracker_color_mode: mode }); }}
                          className={`px-3 py-1.5 capitalize transition-colors ${
                            trackerColorMode === mode
                              ? "bg-primary text-primary-foreground"
                              : "bg-background text-muted-foreground hover:bg-muted"
                          }`}
                        >
                          {mode}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Show/hide toggles */}
                  <div className="space-y-2.5">
                    {([
                      { label: t("settings.appearance.progressBar"), value: trackerShowProgress, setter: setTrackerShowProgress, key: "tracker_show_progress" as const },
                      { label: t("settings.appearance.drawdownPattern"), value: trackerShowDrawdown, setter: setTrackerShowDrawdown, key: "tracker_show_drawdown" as const },
                      { label: t("settings.appearance.weftColorBar"), value: trackerShowWeftColor, setter: setTrackerShowWeftColor, key: "tracker_show_weft_color" as const },
                      { label: t("settings.appearance.prevNextPickCards"), value: trackerShowPickCards, setter: setTrackerShowPickCards, key: "tracker_show_pick_cards" as const },
                    ] as { label: string; value: boolean; setter: (v: boolean) => void; key: "tracker_show_progress" | "tracker_show_drawdown" | "tracker_show_weft_color" | "tracker_show_pick_cards" }[]).map(({ label, value, setter, key }) => (
                      <div key={key} className="flex items-center justify-between">
                        <span className="text-sm">{label}</span>
                        <button
                          role="switch"
                          aria-checked={value}
                          onClick={() => { setter(!value); save({ [key]: !value }); }}
                          className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-ring ${value ? "bg-primary" : "bg-input"}`}
                        >
                          <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform ${value ? "translate-x-4" : "translate-x-1"}`} />
                        </button>
                      </div>
                    ))}
                  </div>

                  {/* Live preview */}
                  <div className="mt-5">
                    <TrackerLivePreview
                      style={activityTheme}
                      colorMode={trackerColorMode}
                      showProgress={trackerShowProgress}
                      showDrawdown={trackerShowDrawdown}
                      showWeftColor={trackerShowWeftColor}
                      showPickCards={trackerShowPickCards}
                      hideUnusedShafts={hideUnusedShaftsTreadles}
                    />
                  </div>
                </Field>

                <Field label={t("settings.appearance.hideUnusedShaftsTreadles")}>
                  <div className="flex items-center gap-3">
                    <button
                      role="switch"
                      aria-checked={hideUnusedShaftsTreadles}
                      onClick={() => {
                        const next = !hideUnusedShaftsTreadles;
                        setHideUnusedShaftsTreadles(next);
                        save({ hide_unused_shafts_treadles: next });
                      }}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                        hideUnusedShaftsTreadles ? "bg-primary" : "bg-input"
                      }`}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                          hideUnusedShaftsTreadles ? "translate-x-6" : "translate-x-1"
                        }`}
                      />
                    </button>
                    <span className="text-sm">{hideUnusedShaftsTreadles ? t("settings.appearance.hidden") : t("settings.appearance.shown")}</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    {t("settings.appearance.hideUnusedHelp")}
                  </p>
                </Field>
              </Section>

              <Section title={t("settings.sections.diagnostics")}>
                <Field label={t("settings.diagnostics.showVersionNumbers")}>
                  <div className="flex items-center gap-3">
                    <button
                      role="switch"
                      aria-checked={showVersionNumbers}
                      onClick={() => {
                        const next = !showVersionNumbers;
                        setShowVersionNumbers(next);
                        save({ show_version_numbers: next });
                      }}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                        showVersionNumbers ? "bg-primary" : "bg-input"
                      }`}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                          showVersionNumbers ? "translate-x-6" : "translate-x-1"
                        }`}
                      />
                    </button>
                    <span className="text-sm">{showVersionNumbers ? t("settings.diagnostics.visible") : t("settings.diagnostics.hidden")}</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    {t("settings.diagnostics.showVersionNumbersHelp")}
                  </p>
                </Field>
              </Section>
              </>
            )}

            {/* ── Preferences ── */}
            {activeSection === "preferences" && (
              <Section title={t("settings.sections.preferences")}>
                <Field label={t("settings.preferences.displayName")}>
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
                      {t("common.save")}
                    </Button>
                  </div>
                </Field>

                <Field label={t("settings.preferences.measurementSystem")}>
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

                <Field label={t("settings.preferences.language")}>
                  <LanguageSelector variant="app" />
                </Field>

                <Field label={t("settings.preferences.sessionIdleTimeout")}>
                  <select
                    value={idleTimeout}
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      setIdleTimeout(v);
                      save({ idle_timeout_minutes: v });
                    }}
                    className="rounded-md border border-border bg-background px-3 py-2 text-sm"
                  >
                    <option value={15}>{t("settings.preferences.timeout15min")}</option>
                    <option value={30}>{t("settings.preferences.timeout30min")}</option>
                    <option value={60}>{t("settings.preferences.timeout1hr")}</option>
                    <option value={120}>{t("settings.preferences.timeout2hr")}</option>
                  </select>
                </Field>
              </Section>
            )}

            {/* ── Privacy & data ── */}
            {activeSection === "privacy" && (
              <Section title={t("settings.sections.privacy")}>
                <Field label={t("settings.privacy.optOut")}>
                  <p className="text-xs text-muted-foreground">
                    {t("settings.privacy.optOutHelp")}
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
                    <span className="text-sm">{!dataConsent ? t("settings.privacy.optedOut") : t("settings.privacy.participating")}</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    {t("settings.privacy.dataUseNote")}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    <strong>Note:</strong> {t("settings.privacy.sharingNote")}
                  </p>
                </Field>

                {showConsentWarning && (
                  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
                    <div className="w-full max-w-md rounded-xl border bg-background shadow-xl space-y-4 p-6">
                      <h2 className="text-base font-semibold">{t("settings.privacy.optOutModal.title")}</h2>

                      <p className="text-sm text-muted-foreground">
                        {t("settings.privacy.optOutModal.body")}
                      </p>

                      <div className="rounded-md bg-amber-500/10 border border-amber-500/30 px-4 py-3 space-y-1.5">
                        <p className="text-sm font-medium text-amber-700 dark:text-amber-400">
                          {t("settings.privacy.optOutModal.warningTitle")}
                        </p>
                        <ul className="text-sm text-muted-foreground list-disc list-inside space-y-1">
                          <li>
                            {t("settings.privacy.optOutModal.sharingLinks")}
                            {sharedDraftCount > 0 && (
                              <span className="font-medium text-foreground">
                                {" "}{t("settings.privacy.optOutModal.currentlyActive", { count: sharedDraftCount })}
                              </span>
                            )}
                          </li>
                          <li>{t("settings.privacy.optOutModal.futureSharing")}</li>
                        </ul>
                        {sharedDraftCount > 0 && (
                          <p className="text-xs text-amber-700 dark:text-amber-400 pt-1">
                            {t("settings.privacy.optOutModal.loseAccess")}
                          </p>
                        )}
                      </div>

                      <p className="text-xs text-muted-foreground">
                        {t("settings.privacy.optOutModal.reOptInNote")}
                      </p>

                      <div className="flex gap-2 pt-1">
                        <Button variant="destructive" size="sm" onClick={confirmConsentOptOut}>
                          {t("settings.privacy.optOutModal.confirmButton")}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setShowConsentWarning(false)}
                        >
                          {t("settings.privacy.optOutModal.cancelButton")}
                        </Button>
                      </div>
                    </div>
                  </div>
                )}

                <div className="rounded-md bg-muted px-4 py-3 text-xs text-muted-foreground space-y-1">
                  <p className="font-medium text-foreground">{t("settings.privacy.whatWeStore")}</p>
                  <ul className="list-disc list-inside space-y-0.5">
                    <li>{t("settings.privacy.storeEmail")}</li>
                    <li>{t("settings.privacy.storeFiles")}</li>
                    <li>{t("settings.privacy.storeSettings")}</li>
                    <li>{t("settings.privacy.storeTimestamp")}</li>
                  </ul>
                  <p className="pt-1">{t("settings.privacy.noSell")}</p>
                </div>
              </Section>
            )}

            {/* ── Terms ── */}
            {activeSection === "terms" && (
              <Section title={t("settings.sections.terms")}>
                <div className="space-y-3">
                  <div className="flex items-center justify-between rounded-lg border p-4">
                    <div>
                      <p className="text-sm font-medium">
                        {t("settings.terms.tosTitle", { version: user.current_eula_version })}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {user.eula_accepted_version === user.current_eula_version
                          ? t("settings.terms.accepted")
                          : t("settings.terms.notAccepted")}
                      </p>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => setShowEula(!showEula)}>
                      {showEula ? t("settings.terms.hide") : t("settings.terms.readTerms")}
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

            {/* ── Feedback history ── */}
            {activeSection === "feedback-history" && <FeedbackHistorySection />}

            {/* ── Account ── */}
            {activeSection === "account" && (
              <Section title={t("settings.sections.account")}>
                <Field label={t("settings.account.downloadData")}>
                  {exportStatus?.status === "pending" ? (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <AppIcons.spinner className="h-4 w-4 animate-spin" />
                      {t("settings.account.archivePending")}
                    </div>
                  ) : exportStatus?.status === "complete" && exportStatus.request_id ? (
                    <div className="space-y-1">
                      <p className="text-sm text-muted-foreground">{t("settings.account.archiveReady")}</p>
                      {exportStatus.expires_at && (
                        <p className="text-xs text-muted-foreground">
                          {t("settings.account.archiveExpires", {
                            date: new Date(exportStatus.expires_at).toLocaleDateString(),
                          })}
                        </p>
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          downloadAuthed(
                            getDataExportDownloadUrl(exportStatus.request_id!),
                            "weftmark-data-export.zip"
                          ).catch(() => {})
                        }
                      >
                        {t("settings.account.downloadArchive")}
                      </Button>
                    </div>
                  ) : (
                    <>
                      {exportStatus?.status === "failed" && (
                        <p className="text-xs text-destructive mb-1">
                          {t("settings.account.archiveFailed")}
                        </p>
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => requestExportMutation.mutate()}
                        disabled={requestExportMutation.isPending}
                      >
                        {t("settings.account.requestArchive")}
                      </Button>
                    </>
                  )}
                  {exportStatus?.status === "pending" && (
                    <p className="text-xs text-muted-foreground mt-1">
                      {t("settings.account.archiveEmailNotice")}
                    </p>
                  )}
                  <p className="text-xs text-muted-foreground mt-1">
                    {t("settings.account.archiveNote")}
                  </p>
                </Field>

                <div className="rounded-lg border border-destructive/30 p-4 space-y-3">
                  <p className="text-sm font-medium text-destructive">{t("settings.account.dangerZone")}</p>
                  <p className="text-sm text-muted-foreground">
                    {t("settings.account.dangerDescription")}
                  </p>

                  {!showDeleteConfirm ? (
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => setShowDeleteConfirm(true)}
                    >
                      {t("settings.account.deleteAccount")}
                    </Button>
                  ) : (
                    <div className="space-y-3">
                      <p className="text-sm">
                        {t("settings.account.deleteConfirmInstruction")}
                      </p>
                      <input
                        type="text"
                        value={deleteInput}
                        onChange={(e) => setDeleteInput(e.target.value)}
                        placeholder={t("settings.account.deleteConfirmPlaceholder")}
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
                          {deleting ? t("settings.account.deleting") : t("settings.account.permanentDelete")}
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
                          {t("common.cancel")}
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

const DISPATCH_BADGE: Record<string, string> = {
  pending: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  sent: "bg-green-500/10 text-green-700 dark:text-green-400",
  skipped: "bg-muted text-muted-foreground",
  failed: "bg-destructive/10 text-destructive",
};

function FeedbackHistorySection() {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data: submissions = [], isLoading } = useQuery({
    queryKey: ["feedback", "mine"],
    queryFn: listMyFeedback,
  });

  return (
    <Section title={t("settings.sections.feedbackHistory")}>
      <p className="text-sm text-muted-foreground">
        {t("settings.feedbackHistory.description")}
      </p>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : submissions.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("settings.feedbackHistory.noSubmissions")}</p>
      ) : (
        <div className="divide-y divide-border rounded-lg border">
          {submissions.map((s: FeedbackRecord) => (
            <div key={s.id} className="px-4 py-3 space-y-1">
              <button
                className="w-full text-left space-y-1"
                onClick={() => setExpanded(expanded === s.id ? null : s.id)}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-xs font-medium shrink-0">
                      {SUBMISSION_TYPE_LABELS[s.submission_type as keyof typeof SUBMISSION_TYPE_LABELS] ?? s.submission_type}
                    </span>
                    {s.is_anonymous && (
                      <span className="text-xs text-muted-foreground shrink-0">{t("settings.feedbackHistory.anonymous")}</span>
                    )}
                    {s.subject && (
                      <span className="text-sm text-foreground truncate">{s.subject}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${DISPATCH_BADGE[s.dispatch_status] ?? ""}`}>
                      {s.dispatch_status}
                    </span>
                    <AppIcons.chevronDown
                      className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${expanded === s.id ? "rotate-180" : ""}`}
                    />
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">
                  {new Date(s.created_at).toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
                </p>
              </button>

              {expanded === s.id && (
                <div className="pt-2 space-y-2">
                  <p className="text-sm whitespace-pre-wrap text-foreground">{s.body}</p>
                  {s.github_discussion_url && (
                    <a
                      href={s.github_discussion_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
                    >
                      <AppIcons.externalLink className="h-3.5 w-3.5" />
                      {t("settings.feedbackHistory.viewDiscussion")}
                    </a>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Section>
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
