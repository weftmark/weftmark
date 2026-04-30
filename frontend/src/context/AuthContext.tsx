import { createContext, startTransition, useContext, useEffect, useState, type ReactNode } from "react";
import { useAuth as useClerkAuth } from "@clerk/clerk-react";
import { api, configureApiClient } from "@/api/client";
import { getHealthReady } from "@/api/health";

export interface User {
  id: string;
  email: string;
  display_name: string;
  is_admin: boolean;
  is_superuser: boolean;
  theme: string;
  activity_theme: string | null;
  idle_timeout_minutes: number;
  measurement_system: string;
  ai_training_consent: boolean;
  eula_accepted_version: string | null;
  current_eula_version: string;
  storage_used_bytes: number;
  storage_quota_bytes: number;
}

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  webhookDegraded: boolean;
  refetch: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn, getToken } = useClerkAuth();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [webhookDegraded, setWebhookDegraded] = useState(false);

  // Wire Clerk's token getter synchronously during render so it's available
  // before any child component mounts and fires API calls.
  configureApiClient(getToken);

  const fetchUser = () => {
    setIsLoading(true);
    api
      .get<User>("/auth/me")
      .then((u) => { setUser(u); setWebhookDegraded(false); })
      .catch(() => {
        setUser(null);
        // When signed in to Clerk but no DB record, check if webhook is degraded
        // so we can show an informative banner rather than a generic error.
        if (isSignedIn) {
          getHealthReady()
            .then((h) => {
              const wh = h.services.find((s) => s.name === "Clerk Webhook");
              setWebhookDegraded(!!wh && !wh.ok);
            })
            .catch(() => {});
        }
      })
      .finally(() => setIsLoading(false));
  };

  // Only fetch once Clerk is loaded. If not signed in, skip the fetch entirely.
  useEffect(() => {
    if (!isLoaded) return;
    if (!isSignedIn) {
      startTransition(() => {
        setUser(null);
        setIsLoading(false);
        setWebhookDegraded(false);
      });
      return;
    }
    fetchUser(); // eslint-disable-line react-hooks/set-state-in-effect
  }, [isLoaded, isSignedIn]);

  // Apply theme class to document root
  useEffect(() => {
    const theme = user?.theme ?? "light";
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [user?.theme]);

  return (
    <AuthContext.Provider
      value={{ user, isLoading, isAuthenticated: user !== null, webhookDegraded, refetch: fetchUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuthContext(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuthContext must be used inside AuthProvider");
  return ctx;
}
