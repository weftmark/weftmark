import { useTranslation } from "react-i18next";
import { useImpersonation } from "@/context/ImpersonationContext";

export function ImpersonationBanner() {
  const { t } = useTranslation();
  const { isImpersonating, impersonatedUser, endImpersonation } = useImpersonation();

  if (!isImpersonating || !impersonatedUser) return null;

  return (
    <div className="flex items-center justify-between gap-3 border-b border-amber-300 bg-amber-50 px-4 py-2 dark:border-amber-700 dark:bg-amber-900/25 shrink-0">
      <p className="text-sm font-medium text-amber-800 dark:text-amber-300">
        ⚠ {t("impersonation.banner", { name: impersonatedUser.display_name || impersonatedUser.email })}
      </p>
      <button
        type="button"
        onClick={() => endImpersonation()}
        className="shrink-0 rounded px-2 py-1 text-xs font-medium text-amber-700 hover:bg-amber-200 dark:text-amber-300 dark:hover:bg-amber-800/40 transition-colors"
      >
        {t("impersonation.stopButton")}
      </button>
    </div>
  );
}
