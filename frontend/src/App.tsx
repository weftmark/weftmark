import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ClerkProvider } from "@clerk/clerk-react";
import { AuthProvider } from "@/context/AuthContext";
import { ProtectedRoute } from "@/components/layout/ProtectedRoute";
import { AppLayout } from "@/components/layout/AppLayout";
import type { ReactNode } from "react";
import { EulaGate } from "@/components/EulaGate";
import { VersionGate } from "@/components/VersionGate";
import { LoginPage } from "@/pages/LoginPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { LandingPage } from "@/pages/LandingPage";
import { AboutPage } from "@/pages/AboutPage";
import { PrivacyPage } from "@/pages/PrivacyPage";
import { TermsPage } from "@/pages/TermsPage";
import { CostsPage } from "@/pages/CostsPage";
import { DraftsPage } from "@/pages/DraftsPage";
import { DraftDetailPage } from "@/pages/DraftDetailPage";
import { LoomsPage } from "@/pages/LoomsPage";
import { LoomDetailPage } from "@/pages/LoomDetailPage";
import { YarnPage } from "@/pages/YarnPage";
import { YarnDetailPage } from "@/pages/YarnDetailPage";
import { ProjectsPage } from "@/pages/ProjectsPage";
import { ProjectDetailPage } from "@/pages/ProjectDetailPage";
import { ProjectLandingPage } from "@/pages/ProjectLandingPage";
import { WarpingPlanPage } from "@/pages/WarpingPlanPage";
import { SharedProjectPage } from "@/pages/SharedProjectPage";
import { CollectionsPage } from "@/pages/CollectionsPage";
import { CollectionDetailPage } from "@/pages/CollectionDetailPage";
import { LoomCatalogPage } from "@/pages/LoomCatalogPage";
import { AdminPage } from "@/pages/AdminPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { SignOutPage } from "@/pages/SignOutPage";
import { UnauthorizedPage } from "@/pages/UnauthorizedPage";
import { PendingPage } from "@/pages/PendingPage";
import { DevBanner } from "@/components/DevBanner";
import { ServiceHealthBanner } from "@/components/ServiceHealthBanner";
import { SystemGate } from "@/components/SystemGate";
import { clerkPublishableKey, clerkKeyMissing } from "@/lib/env";
import { useAuth } from "@/hooks/useAuth";

function AuthRoute({ children, requireAdmin = false }: { children: ReactNode; requireAdmin?: boolean }) {
  return (
    <ProtectedRoute requireAdmin={requireAdmin}>
      <AppLayout>{children}</AppLayout>
    </ProtectedRoute>
  );
}

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
    <ClerkProvider publishableKey={clerkPublishableKey} afterSignInUrl="/home" afterSignUpUrl="/pending" afterSignOutUrl="/sign-out">
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
                  <Route path="/pending" element={<PendingPage />} />
                  <Route path="/register" element={<RegisterPage />} />
                  <Route path="/sign-out" element={<SignOutPage />} />
                  <Route path="/unauthorized" element={<UnauthorizedPage />} />
                  <Route path="/about" element={<AboutPage />} />
                  <Route path="/privacy" element={<PrivacyPage />} />
                  <Route path="/terms" element={<TermsPage />} />
                  <Route path="/costs" element={<CostsPage />} />
                  <Route path="/catalog/looms" element={<LoomCatalogPage />} />
                  <Route path="/" element={<RootRoute />} />
                  <Route path="/home" element={<AuthRoute><DashboardPage /></AuthRoute>} />
                  <Route path="/drafts" element={<AuthRoute><DraftsPage /></AuthRoute>} />
                  <Route path="/drafts/:id" element={<AuthRoute><DraftDetailPage /></AuthRoute>} />
                  <Route path="/looms" element={<AuthRoute><LoomsPage /></AuthRoute>} />
                  <Route path="/looms/:id" element={<AuthRoute><LoomDetailPage /></AuthRoute>} />
                  <Route path="/collections" element={<AuthRoute><CollectionsPage /></AuthRoute>} />
                  <Route path="/collections/:id" element={<AuthRoute><CollectionDetailPage /></AuthRoute>} />
                  <Route path="/yarn" element={<AuthRoute><YarnPage /></AuthRoute>} />
                  <Route path="/yarn/:id" element={<AuthRoute><YarnDetailPage /></AuthRoute>} />
                  <Route path="/projects" element={<AuthRoute><ProjectsPage /></AuthRoute>} />
                  <Route path="/projects/:id" element={<AuthRoute><ProjectLandingPage /></AuthRoute>} />
                  <Route path="/projects/:id/track" element={<AuthRoute><ProjectDetailPage /></AuthRoute>} />
                  <Route path="/projects/:id/warping-plan" element={<AuthRoute><WarpingPlanPage /></AuthRoute>} />
                  <Route path="/p/:slug" element={<SharedProjectPage />} />
                  <Route path="/admin" element={<Navigate to="/admin/users" replace />} />
                  <Route path="/admin/:section" element={<AuthRoute requireAdmin><AdminPage /></AuthRoute>} />
                  <Route path="/settings" element={<Navigate to="/settings/appearance" replace />} />
                  <Route path="/settings/:section" element={<AuthRoute><SettingsPage /></AuthRoute>} />
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
