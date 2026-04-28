import { createContext, startTransition, useContext, useEffect, useState, type ReactNode } from "react";
import { useAuth as useClerkAuth } from "@clerk/clerk-react";
import { api, configureApiClient } from "@/api/client";

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
}

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  refetch: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn, getToken } = useClerkAuth();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Wire Clerk's token getter into the API client as soon as it's available.
  useEffect(() => {
    configureApiClient(getToken);
  }, [getToken]);

  const fetchUser = () => {
    setIsLoading(true);
    api
      .get<User>("/auth/me")
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setIsLoading(false));
  };

  // Only fetch once Clerk is loaded. If not signed in, skip the fetch entirely.
  useEffect(() => {
    if (!isLoaded) return;
    if (!isSignedIn) {
      startTransition(() => {
        setUser(null);
        setIsLoading(false);
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
      value={{ user, isLoading, isAuthenticated: user !== null, refetch: fetchUser }}
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
