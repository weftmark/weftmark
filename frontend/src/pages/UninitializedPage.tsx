import { useTranslation } from "react-i18next";

export function UninitializedPage() {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="w-full max-w-sm space-y-6 px-4 text-center">
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight">{t("uninitializedPage.title")}</h1>
          <p className="text-sm text-muted-foreground">
            {t("uninitializedPage.desc")}
          </p>
        </div>
        <div className="rounded-md bg-muted px-4 py-3 text-left font-mono text-xs text-muted-foreground">
          docker compose exec backend python -m app.cli seed
        </div>
      </div>
    </div>
  );
}
