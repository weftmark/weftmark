import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "@/api/client";

interface User {
  id: string;
  email: string;
  display_name: string;
  is_admin: boolean;
  theme: string;
  idle_timeout_minutes: number;
}

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  refetch: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchUser = () => {
    setIsLoading(true);
    api
      .get<User>("/auth/me")
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setIsLoading(false));
  };

  useEffect(() => {
    fetchUser(); // eslint-disable-line react-hooks/set-state-in-effect
  }, []);

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
