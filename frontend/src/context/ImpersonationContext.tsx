import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { setImpersonationTarget } from "@/api/client";
import { startImpersonationSession, endImpersonationSession } from "@/api/impersonation";
import type { User } from "@/context/AuthContext";

interface ImpersonationState {
  isImpersonating: boolean;
  impersonatedUser: User | null;
  startImpersonation: (realUser: User, targetUser: User) => Promise<void>;
  endImpersonation: () => Promise<void>;
}

const ImpersonationContext = createContext<ImpersonationState | null>(null);

function applyTheme(theme: string) {
  if (theme === "system") {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    document.documentElement.classList.toggle("dark", mq.matches);
  } else {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }
}

export function ImpersonationProvider({ children }: { children: ReactNode }) {
  const [impersonatedUser, setImpersonatedUser] = useState<User | null>(null);
  const startedAtRef = useRef<Date | null>(null);
  const realThemeRef = useRef<string>("system");

  const startImpersonation = useCallback(async (realUser: User, targetUser: User) => {
    await startImpersonationSession(targetUser.id);
    realThemeRef.current = realUser.theme;
    setImpersonationTarget(targetUser.id);
    startedAtRef.current = new Date();
    setImpersonatedUser(targetUser);
    applyTheme(targetUser.theme);
  }, []);

  const endImpersonation = useCallback(async () => {
    if (!impersonatedUser) return;
    const durationSeconds = startedAtRef.current
      ? Math.round((Date.now() - startedAtRef.current.getTime()) / 1000)
      : 0;
    try {
      await endImpersonationSession(impersonatedUser.id, durationSeconds);
    } finally {
      setImpersonationTarget(null);
      startedAtRef.current = null;
      setImpersonatedUser(null);
      applyTheme(realThemeRef.current);
    }
  }, [impersonatedUser]);

  return (
    <ImpersonationContext.Provider
      value={{
        isImpersonating: impersonatedUser !== null,
        impersonatedUser,
        startImpersonation,
        endImpersonation,
      }}
    >
      {children}
    </ImpersonationContext.Provider>
  );
}

export function useImpersonation(): ImpersonationState {
  const ctx = useContext(ImpersonationContext);
  if (!ctx) throw new Error("useImpersonation must be used inside ImpersonationProvider");
  return ctx;
}
