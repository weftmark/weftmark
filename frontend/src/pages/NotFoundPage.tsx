import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "@/hooks/useAuth";
import { AuthCard } from "@/components/auth/AuthCard";

export function NotFoundPage() {
  const { isAuthenticated } = useAuth();
  const { t } = useTranslation();

  return (
    <AuthCard>
      <div className="text-center">
        <p className="text-5xl font-bold tracking-tight text-zinc-800">404</p>
        <h1 className="mt-3 text-lg font-semibold text-zinc-800">{t("notFoundPage.title")}</h1>
        <p className="mt-2 text-sm text-stone-600">{t("notFoundPage.description")}</p>
        <Link
          to={isAuthenticated ? "/home" : "/"}
          className="mt-6 inline-block text-sm text-amber-700 underline underline-offset-2 hover:text-amber-800"
        >
          {t("notFoundPage.backToHome")}
        </Link>
      </div>
    </AuthCard>
  );
}
