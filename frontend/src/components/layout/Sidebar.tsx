import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useClerk } from "@clerk/clerk-react";
import { useTranslation } from "react-i18next";
import { AppIcons, type LucideIcon } from "@/lib/icons";
import { WeftmarkLogo } from "@/components/WeftmarkLogo";
import { useAuth } from "@/hooks/useAuth";
import { FeedbackModal } from "@/components/FeedbackModal";
import { OnboardingChecklist } from "@/components/layout/OnboardingChecklist";

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  exact?: boolean;
}

interface Props {
  open: boolean;
  onClose: () => void;
  desktopCollapsed?: boolean;
  onDesktopExpand?: () => void;
  onDesktopCollapse?: () => void;
}

type NavGroup = "settings" | "admin" | "superuser";

const SettingsIcon = AppIcons.settings;
const AdminIcon = AppIcons.admin;
const SuperuserIcon = AppIcons.superuser;

export function Sidebar({ open, onClose, desktopCollapsed = false, onDesktopExpand, onDesktopCollapse }: Props) {
  const location = useLocation();
  const { user } = useAuth();
  const { signOut } = useClerk();
  const { t } = useTranslation();
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [expandedGroup, setExpandedGroup] = useState<NavGroup | null>(null);

  function toggleGroup(group: NavGroup) {
    setExpandedGroup((prev) => (prev === group ? null : group));
  }

  const NAV_ITEMS: NavItem[] = [
    { label: t("nav.dashboard"), href: "/home", icon: AppIcons.dashboard, exact: true },
    { label: t("nav.projects"), href: "/projects", icon: AppIcons.projects },
    { label: t("nav.drafts"), href: "/drafts", icon: AppIcons.drafts },
    { label: t("nav.collections"), href: "/collections", icon: AppIcons.collections },
    { label: t("nav.equipment"), href: "/looms", icon: AppIcons.equipment },
    { label: t("nav.yarn"), href: "/yarn", icon: AppIcons.yarn },
  ];

  const SETTINGS_SECTIONS = [
    { id: "appearance", label: t("settingsSections.appearance") },
    { id: "preferences", label: t("settingsSections.preferences") },
    { id: "connections", label: t("settingsSections.connections") },
    { id: "privacy", label: t("settingsSections.privacy") },
    { id: "terms", label: t("settingsSections.terms") },
    { id: "account", label: t("settingsSections.account") },
    { id: "feedback-history", label: t("settingsSections.feedbackHistory") },
  ];

  const ADMIN_SECTIONS = [
    { id: "users", label: t("adminSections.users") },
    { id: "invites", label: t("adminSections.invites") },
    { id: "stats", label: t("adminSections.stats") },
    { id: "health", label: t("adminSections.health") },
    { id: "services", label: t("adminSections.services") },
    { id: "deps", label: t("adminSections.deps") },
    { id: "audit", label: t("adminSections.audit") },
    { id: "feedback", label: t("adminSections.feedback") },
    { id: "slugs", label: t("adminSections.slugs") },
    { id: "looms", label: t("adminSections.looms") },
  ];

  const SUPERUSER_SECTIONS = [
    { id: "eula", label: t("superuserSections.eula") },
    { id: "storage", label: t("superuserSections.storage") },
    { id: "cve", label: t("superuserSections.cve") },
    { id: "workers", label: t("superuserSections.workers") },
    { id: "deletion", label: t("superuserSections.deletion") },
    { id: "reconcile", label: t("superuserSections.reconcile") },
    { id: "maintenance", label: t("superuserSections.maintenance") },
    { id: "schedule", label: t("superuserSections.schedule") },
    { id: "exports", label: t("superuserSections.exports") },
    { id: "credentials", label: t("superuserSections.credentials") },
    { id: "sandbox", label: t("superuserSections.sandbox") },
  ];

  function isActive(href: string, exact = false) {
    if (exact) return location.pathname === href;
    return location.pathname === href || location.pathname.startsWith(href + "/");
  }

  function navCls(active: boolean) {
    return `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
      active
        ? "bg-accent text-accent-foreground"
        : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
    } ${desktopCollapsed ? "lg:justify-center lg:px-2" : ""}`;
  }

  function iconCls(active: boolean) {
    return `h-4 w-4 shrink-0 ${active ? "text-accent-foreground" : "text-muted-foreground"}`;
  }

  return (
    <>
      {/* Mobile backdrop */}
      {open && (
        <div
          className="fixed inset-0 z-20 bg-black/40 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar panel */}
      <aside
        className={`fixed inset-y-0 left-0 z-30 flex flex-col bg-card border-r border-border transition-all duration-200 ease-in-out lg:static lg:z-auto lg:translate-x-0 ${
          open ? "translate-x-0 w-60" : "-translate-x-full w-60"
        } ${desktopCollapsed ? "lg:w-14" : "lg:w-60"}`}
      >
        {/* Logo */}
        <div className={`shrink-0 border-b border-border flex h-16 items-center justify-between px-4 ${
          desktopCollapsed ? "lg:flex-col lg:items-center lg:justify-center lg:h-auto lg:px-2 lg:py-3 lg:gap-2" : ""
        }`}>
          <Link
            to="/home"
            className={`flex items-center gap-2.5 ${desktopCollapsed ? "lg:w-full lg:justify-center" : ""}`}
            onClick={onClose}
            title={desktopCollapsed ? "Dashboard" : undefined}
          >
            <WeftmarkLogo className={`h-6 text-primary ${desktopCollapsed ? "lg:h-auto lg:w-full" : "w-auto"}`} />
            <span className={`text-sm font-semibold tracking-tight text-foreground ${desktopCollapsed ? "lg:hidden" : ""}`} style={{ fontFamily: '"Segoe UI", system-ui, sans-serif' }}>weftmark</span>
          </Link>
          {/* Mobile close button */}
          <button
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:text-subdued lg:hidden"
            aria-label="Close menu"
          >
            <AppIcons.close className="h-4 w-4" />
          </button>
          {/* Desktop expand button — stacks below logo when collapsed */}
          <button
            onClick={onDesktopExpand}
            className={`rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground ${desktopCollapsed ? "hidden lg:flex" : "hidden"}`}
            aria-label="Expand navigation"
            title="Expand navigation"
          >
            <AppIcons.chevronDoubleRight className="h-3.5 w-3.5" />
          </button>
          {/* Desktop collapse button — visible only when sidebar is expanded */}
          <button
            onClick={onDesktopCollapse}
            className={`rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground ${desktopCollapsed ? "hidden" : "hidden lg:flex"}`}
            aria-label="Collapse navigation"
            title="Collapse navigation"
          >
            <AppIcons.chevronDoubleLeft className="h-5 w-5" />
          </button>
        </div>

        {/* Onboarding checklist — above primary nav, hidden for superusers */}
        {!user?.is_superuser && (
          <div className="shrink-0 pt-2">
            <OnboardingChecklist collapsed={desktopCollapsed} />
          </div>
        )}

        {/* Primary nav — hidden for superusers (they only use /admin) */}
        {!user?.is_superuser && (
          <nav className="flex-1 overflow-y-auto px-3 py-3 space-y-0.5">
            {NAV_ITEMS.map(({ label, href, icon: Icon, exact }) => (
              <Link
                key={href}
                to={href}
                onClick={onClose}
                className={navCls(isActive(href, exact))}
                title={desktopCollapsed ? label : undefined}
              >
                <Icon className={iconCls(isActive(href, exact))} strokeWidth={1.75} />
                <span className={desktopCollapsed ? "lg:hidden" : ""}>{label}</span>
              </Link>
            ))}
          </nav>
        )}

        {/* Spacer for superusers */}
        {user?.is_superuser && <div className="flex-1" />}

        {/* Bottom nav */}
        <div className={`shrink-0 border-t border-border px-3 py-3 space-y-0.5 ${desktopCollapsed ? "lg:px-2" : ""}`}>
          <button
            onClick={() => toggleGroup("settings")}
            className={`w-full ${navCls(expandedGroup === "settings")}`}
            title={desktopCollapsed ? t("nav.settings") : undefined}
          >
            <SettingsIcon className={iconCls(expandedGroup === "settings")} strokeWidth={1.75} />
            <span className={desktopCollapsed ? "lg:hidden" : ""}>{t("nav.settings")}</span>
          </button>

          {expandedGroup === "settings" && !desktopCollapsed && (
            <div className="ml-3 border-l border-border pl-2 space-y-0.5">
              {SETTINGS_SECTIONS.map(({ id, label }) => {
                const href = `/settings/${id}`;
                const active = location.pathname === href;
                return (
                  <Link
                    key={id}
                    to={href}
                    onClick={onClose}
                    className={`block rounded-md px-2 py-1.5 text-xs transition-colors ${
                      active
                        ? "bg-accent/20 text-accent font-medium"
                        : "text-muted-foreground hover:bg-accent/10 hover:text-foreground"
                    }`}
                  >
                    {label}
                  </Link>
                );
              })}
            </div>
          )}

          {user?.is_admin && (
            <button
              onClick={() => toggleGroup("admin")}
              className={`w-full ${navCls(expandedGroup === "admin")}`}
              title={desktopCollapsed ? t("nav.admin") : undefined}
            >
              <AdminIcon className={iconCls(expandedGroup === "admin")} strokeWidth={1.75} />
              <span className={desktopCollapsed ? "lg:hidden" : ""}>{t("nav.admin")}</span>
            </button>
          )}

          {user?.is_admin && expandedGroup === "admin" && !desktopCollapsed && (
            <div className="ml-3 border-l border-border pl-2 space-y-0.5">
              {ADMIN_SECTIONS.map(({ id, label }) => {
                const href = `/admin/${id}`;
                const active = location.pathname === href;
                return (
                  <Link
                    key={id}
                    to={href}
                    onClick={onClose}
                    className={`block rounded-md px-2 py-1.5 text-xs transition-colors ${
                      active
                        ? "bg-accent/20 text-accent font-medium"
                        : "text-muted-foreground hover:bg-accent/10 hover:text-foreground"
                    }`}
                  >
                    {label}
                  </Link>
                );
              })}
            </div>
          )}

          {user?.is_superuser && (
            <button
              onClick={() => toggleGroup("superuser")}
              className={`w-full ${navCls(expandedGroup === "superuser")}`}
              title={desktopCollapsed ? t("nav.superuser") : undefined}
            >
              <SuperuserIcon className={iconCls(expandedGroup === "superuser")} strokeWidth={1.75} />
              <span className={desktopCollapsed ? "lg:hidden" : ""}>{t("nav.superuser")}</span>
            </button>
          )}

          {user?.is_superuser && expandedGroup === "superuser" && !desktopCollapsed && (
            <div className="ml-3 border-l border-border pl-2 space-y-0.5">
              {SUPERUSER_SECTIONS.map(({ id, label }) => {
                const href = `/superuser/${id}`;
                const active = location.pathname === href;
                return (
                  <Link
                    key={id}
                    to={href}
                    onClick={onClose}
                    className={`block rounded-md px-2 py-1.5 text-xs transition-colors ${
                      active
                        ? "bg-accent/20 text-accent font-medium"
                        : "text-muted-foreground hover:bg-accent/10 hover:text-foreground"
                    }`}
                  >
                    {label}
                  </Link>
                );
              })}
            </div>
          )}

          <button
            onClick={() => setFeedbackOpen(true)}
            className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground ${desktopCollapsed ? "lg:justify-center lg:px-2" : ""}`}
            title={desktopCollapsed ? t("nav.sendFeedback") : undefined}
          >
            <AppIcons.feedback className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} />
            <span className={desktopCollapsed ? "lg:hidden" : ""}>{t("nav.sendFeedback")}</span>
          </button>

          <Link
            to="/costs"
            onClick={onClose}
            className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground ${desktopCollapsed ? "lg:justify-center lg:px-2" : ""}`}
            title={desktopCollapsed ? t("nav.supportWeftmark") : undefined}
          >
            <AppIcons.support className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} />
            <span className={desktopCollapsed ? "lg:hidden" : ""}>{t("nav.supportWeftmark")}</span>
          </Link>

          <button
            onClick={() => signOut()}
            className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-subdued transition-colors hover:bg-muted hover:text-foreground ${desktopCollapsed ? "lg:justify-center lg:px-2" : ""}`}
            title={desktopCollapsed ? t("nav.signOut") : undefined}
          >
            <AppIcons.logout className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} />
            <span className={desktopCollapsed ? "lg:hidden" : ""}>{t("nav.signOut")}</span>
          </button>
        </div>

        {/* User identity — hidden on desktop in rail mode */}
        {user && (
          <div className={`shrink-0 border-t border-border bg-muted px-4 py-3 ${desktopCollapsed ? "lg:hidden" : ""}`}>
            <p className="truncate text-xs font-medium text-foreground">{user.display_name}</p>
            <p className="truncate text-xs text-muted-foreground">{user.email}</p>
          </div>
        )}
      </aside>

      {feedbackOpen && <FeedbackModal onClose={() => setFeedbackOpen(false)} />}
    </>
  );
}
