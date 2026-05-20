import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { WeftmarkLogo } from "@/components/WeftmarkLogo";
import { PublicFooter } from "@/components/PublicFooter";
import { EulaContent } from "@/components/EulaContent";
import { getCurrentEula } from "@/api/users";

export function TermsPage() {
  const { t } = useTranslation();
  const { data: eula, isLoading, isError } = useQuery({
    queryKey: ["eula", "current"],
    queryFn: getCurrentEula,
    staleTime: 5 * 60 * 1000,
  });

  return (
    <div className="flex min-h-screen flex-col bg-stone-50 text-stone-900">
      <header className="border-b border-stone-200 bg-stone-50 px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center gap-3">
          <Link to="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
            <WeftmarkLogo className="h-8 w-auto text-amber-800" />
            <span className="text-lg font-semibold tracking-tight" style={{ fontFamily: '"Segoe UI", system-ui, sans-serif' }}>weftmark</span>
          </Link>
        </div>
      </header>

      <main className="flex-1 px-6 py-16">
        <div className="mx-auto max-w-2xl space-y-8">
          <div>
            <h1 className="text-3xl font-bold tracking-tight mb-2">{t("termsPage.title")}</h1>
            {eula && (
              <p className="text-sm text-stone-400">
                {t("termsPage.versionEffective", {
                  version: eula.version,
                  date: new Date(eula.effective_date).toLocaleDateString("en-GB", {
                    day: "numeric",
                    month: "long",
                    year: "numeric",
                  }),
                })}
              </p>
            )}
          </div>

          {isLoading && (
            <p className="text-sm text-stone-400">{t("termsPage.loading")}</p>
          )}

          {isError && (
            <p className="text-sm text-red-600">
              {t("termsPage.error")}{" "}
              <a href="mailto:admin@weftmark.com" className="underline">
                admin@weftmark.com
              </a>
              .
            </p>
          )}

          {eula && (
            <div className="prose prose-stone prose-sm max-w-none">
              <EulaContent bodyHtml={eula.body_html} />
            </div>
          )}
        </div>
      </main>

      <PublicFooter />
    </div>
  );
}
