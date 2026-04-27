import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ClerkProvider, useAuth as useClerkAuth } from "@clerk/clerk-react";
import { AuthProvider } from "@/context/AuthContext";
import { ProtectedRoute } from "@/components/layout/ProtectedRoute";
import { EulaGate } from "@/components/EulaGate";
import { VersionGate } from "@/components/VersionGate";
import { LoginPage } from "@/pages/LoginPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { ProjectsPage } from "@/pages/ProjectsPage";
import { ProjectDetailPage } from "@/pages/ProjectDetailPage";
import { LoomsPage } from "@/pages/LoomsPage";
import { LoomDetailPage } from "@/pages/LoomDetailPage";
import { YarnPage } from "@/pages/YarnPage";
import { YarnDetailPage } from "@/pages/YarnDetailPage";
import { ActivitiesPage } from "@/pages/ActivitiesPage";
import { ActivityDetailPage } from "@/pages/ActivityDetailPage";
import { AdminPage } from "@/pages/AdminPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { configureApiClient } from "@/api/client";

const CLERK_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string;

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
});

/** Wires Clerk's getToken into the API client so all requests carry a Bearer token. */
function ClerkTokenConfigurer() {
  const { getToken } = useClerkAuth();
  useEffect(() => {
    configureApiClient(getToken);
  }, [getToken]);
  return null;
}

export default function App() {
  return (
    <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY} afterSignOutUrl="/login">
      <VersionGate>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <BrowserRouter>
              <ClerkTokenConfigurer />
              <EulaGate>
                <Routes>
                  <Route path="/login" element={<LoginPage />} />
                  <Route path="/register" element={<LoginPage />} />
                  <Route
                    path="/"
                    element={
                      <ProtectedRoute>
                        <DashboardPage />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/projects"
                    element={
                      <ProtectedRoute>
                        <ProjectsPage />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/projects/:id"
                    element={
                      <ProtectedRoute>
                        <ProjectDetailPage />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/looms"
                    element={
                      <ProtectedRoute>
                        <LoomsPage />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/looms/:id"
                    element={
                      <ProtectedRoute>
                        <LoomDetailPage />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/yarn"
                    element={
                      <ProtectedRoute>
                        <YarnPage />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/yarn/:id"
                    element={
                      <ProtectedRoute>
                        <YarnDetailPage />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/activities"
                    element={
                      <ProtectedRoute>
                        <ActivitiesPage />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/activities/:id"
                    element={
                      <ProtectedRoute>
                        <ActivityDetailPage />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/admin"
                    element={
                      <ProtectedRoute requireAdmin>
                        <AdminPage />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/settings"
                    element={
                      <ProtectedRoute>
                        <SettingsPage />
                      </ProtectedRoute>
                    }
                  />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </EulaGate>
            </BrowserRouter>
          </AuthProvider>
        </QueryClientProvider>
      </VersionGate>
    </ClerkProvider>
  );
}
