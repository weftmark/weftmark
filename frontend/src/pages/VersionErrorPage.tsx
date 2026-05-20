import { useTranslation } from "react-i18next";

interface Props {
  frontendVersion: string;
  backendVersion: string;
  workerVersion?: string;
}

export function VersionErrorPage({ frontendVersion, backendVersion, workerVersion }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <div className="w-full max-w-sm space-y-6 px-4 text-center">
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight">{t("versionErrorPage.title")}</h1>
          <p className="text-sm text-muted-foreground">
            {t("versionErrorPage.desc")}
          </p>
        </div>
        <div className="rounded-md bg-muted px-4 py-3 text-left font-mono text-xs text-muted-foreground space-y-1">
          <div>{t("versionErrorPage.frontend")} {frontendVersion}</div>
          <div>{t("versionErrorPage.backend")}&nbsp; {backendVersion || t("versionErrorPage.unreachable")}</div>
          {workerVersion && <div>{t("versionErrorPage.worker")}&nbsp;&nbsp; {workerVersion}</div>}
        </div>
      </div>
    </div>
  );
}
