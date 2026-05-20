import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { SignUp } from "@clerk/clerk-react";
import { AuthCard } from "@/components/auth/AuthCard";

const CLERK_APPEARANCE = {
  variables: {
    colorPrimary: "#27272a",
    colorBackground: "#ffffff",
    colorInputBackground: "#fafaf9",
    colorText: "#1c1917",
    colorTextSecondary: "#57534e",
    borderRadius: "0.5rem",
  },
  elements: {
    headerTitle: "hidden",
    headerSubtitle: "hidden",
  },
};

function isSSOStep() {
  if (typeof window === "undefined") return false;
  const h = window.location.hash;
  return h.includes("sso") || h.includes("continue") || h.includes("oauth");
}

export function RegisterPage() {
  const [ssoStep, setSSOStep] = useState(isSSOStep);
  const { t } = useTranslation();

  useEffect(() => {
    const onHash = () => setSSOStep(isSSOStep());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  return (
    <AuthCard
      naked
      footer={
        <>
          {t("registerPage.alreadyHaveAccount")}{" "}
          <Link to="/login" className="text-amber-700 underline underline-offset-2 hover:text-amber-800">
            {t("registerPage.signIn")}
          </Link>
        </>
      }
    >
      <div className="mb-5 text-center">
        {ssoStep ? (
          <>
            <h1 className="text-lg font-semibold text-zinc-800">{t("registerPage.oneMoreStep")}</h1>
            <p className="mt-1 text-sm text-stone-600">{t("registerPage.accountConnected")}</p>
          </>
        ) : (
          <>
            <h1 className="text-lg font-semibold text-zinc-800">{t("registerPage.createAccount")}</h1>
            <p className="mt-1 text-sm text-stone-600">{t("registerPage.signUpPrompt")}</p>
          </>
        )}
      </div>
      <SignUp routing="hash" appearance={CLERK_APPEARANCE} />
    </AuthCard>
  );
}
