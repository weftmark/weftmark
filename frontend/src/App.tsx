import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ClerkProvider } from "@clerk/clerk-react";
import { AuthProvider } from "@/context/AuthContext";
import { ProtectedRoute } from "@/components/layout/ProtectedRoute";
import { EulaGate } from "@/components/EulaGate";
import { VersionGate } from "@/components/VersionGate";
import { LoginPage } from "@/pages/LoginPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { LandingPage } from "@/pages/LandingPage";
import { AboutPage } from "@/pages/AboutPage";
import { PrivacyPage } from "@/pages/PrivacyPage";
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
import { SignOutPage } from "@/pages/SignOutPage";
import { UnauthorizedPage } from "@/pages/UnauthorizedPage";
import { DevBanner } from "@/components/DevBanner";
import { ServiceHealthBanner } from "@/components/ServiceHealthBanner";
import { SystemGate } from "@/components/SystemGate";
import { clerkPublishableKey, clerkKeyMissing } from "@/lib/env";
import { useAuth } from "@/hooks/useAuth";

function RootRoute() {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <span className="text-sm text-muted-foreground">Loading…</span>
      </div>
    );
  }
  if (isAuthenticated) return <Navigate to="/home" replace />;
  return <LandingPage />;
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
});

export default function App() {
  if (clerkKeyMissing) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="w-full max-w-sm space-y-4 px-4 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">Configuration Error</h1>
          <p className="text-sm text-muted-foreground">
            CLERK_PUBLISHABLE_KEY is not set. Set it in the container environment and restart.
          </p>
        </div>
      </div>
    );
  }

  return (
    <ClerkProvider publishableKey={clerkPublishableKey} afterSignOutUrl="/sign-out">
      <VersionGate>
        <SystemGate>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <BrowserRouter>
              <DevBanner />
              <ServiceHealthBanner />
              <EulaGate>
                <Routes>
                  <Route path="/login" element={<LoginPage />} />
                  <Route path="/register" element={<RegisterPage />} />
                  <Route path="/sign-out" element={<SignOutPage />} />
                  <Route path="/unauthorized" element={<UnauthorizedPage />} />
                  <Route path="/about" element={<AboutPage />} />
                  <Route path="/privacy" element={<PrivacyPage />} />
                  <Route path="/" element={<RootRoute />} />
                  <Route
                    path="/home"
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
        </SystemGate>
      </VersionGate>
    </ClerkProvider>
  );
}
