import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
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
          Already have an account?{" "}
          <Link to="/login" className="text-amber-700 underline underline-offset-2 hover:text-amber-800">
            Sign in
          </Link>
        </>
      }
    >
      <div className="mb-5 text-center">
        {ssoStep ? (
          <>
            <h1 className="text-lg font-semibold text-zinc-800">One more step</h1>
            <p className="mt-1 text-sm text-stone-600">
              Your account was connected. Choose a display name to finish creating your weftmark account.
            </p>
          </>
        ) : (
          <>
            <h1 className="text-lg font-semibold text-zinc-800">Create your account</h1>
            <p className="mt-1 text-sm text-stone-600">Sign up with email or connect an existing account</p>
          </>
        )}
      </div>
      <SignUp routing="hash" appearance={CLERK_APPEARANCE} />
    </AuthCard>
  );
}
