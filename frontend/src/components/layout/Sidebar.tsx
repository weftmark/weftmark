import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useClerk } from "@clerk/clerk-react";
import { useTranslation } from "react-i18next";
import { AppIcons, type LucideIcon } from "@/lib/icons";
import { WeftmarkLogo } from "@/components/WeftmarkLogo";
import { useAuth } from "@/hooks/useAuth";
import { useImpersonation } from "@/context/ImpersonationContext";
import { FeedbackModal } from "@/components/FeedbackModal";
import { OnboardingChecklist } from "@/components/layout/OnboardingChecklist";
import type { User } from "@/context/AuthContext";

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  exact?: boolean;
}

interface Props {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly desktopCollapsed?: boolean;
  readonly onDesktopExpand?: () => void;
  readonly onDesktopCollapse?: () => void;
}

interface NavGroupSectionProps {
  readonly icon: LucideIcon;
  readonly label: string;
  readonly expanded: boolean;
  readonly onToggle: () => void;
  readonly desktopCollapsed: boolean;
  readonly onClose: () => void;
  readonly sections: { id: string; label: string }[];
  readonly basePath: string;
}

type NavGroup = "settings" | "admin" | "superuser";

const SettingsIcon = AppIcons.Settings;
const AdminIcon = AppIcons.Admin;
const SuperuserIcon = AppIcons.Superuser;
const ExpandIcon = AppIcons.ChevronDoubleRight;
const CollapseIcon = AppIcons.ChevronDoubleLeft;

function isActive(pathname: string, href: string, exact = false): boolean {
  if (exact) return pathname === href;
  return pathname === href || pathname.startsWith(href + "/");
}

function navCls(active: boolean, desktopCollapsed: boolean): string {
  return `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
    active
      ? "bg-accent text-accent-foreground"
      : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
  } ${desktopCollapsed ? "lg:justify-center lg:px-2" : ""}`;
}

function iconCls(active: boolean): string {
  return `h-4 w-4 shrink-0 ${active ? "text-accent-foreground" : "text-muted-foreground"}`;
}

function NavGroupSection({
  icon: Icon,
  label,
  expanded,
  onToggle,
  desktopCollapsed,
  onClose,
  sections,
  basePath,
}: NavGroupSectionProps) {
  const location = useLocation();
  return (
    <>
      <button
        type="button"
        onClick={onToggle}
        className={`w-full ${navCls(expanded, desktopCollapsed)}`}
        title={desktopCollapsed ? label : undefined}
      >
        <Icon className={iconCls(expanded)} strokeWidth={1.75} />
        <span className={desktopCollapsed ? "lg:hidden" : ""}>{label}</span>
      </button>
      {expanded && !desktopCollapsed && (
        <div className="ml-3 border-l border-border pl-2 space-y-0.5">
          {sections.map(({ id, label: sectionLabel }) => {
            const href = `${basePath}/${id}`;
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
                {sectionLabel}
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}

interface SidebarHeaderProps {
  readonly desktopCollapsed: boolean;
  readonly onClose: () => void;
  readonly onDesktopExpand?: () => void;
  readonly onDesktopCollapse?: () => void;
}

function SidebarHeader({ desktopCollapsed, onClose, onDesktopExpand, onDesktopCollapse }: SidebarHeaderProps) {
  return (
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
        type="button"
        onClick={onClose}
        className="rounded-md p-1 text-muted-foreground hover:text-subdued lg:hidden"
        aria-label="Close menu"
      >
        <AppIcons.Close className="h-4 w-4" />
      </button>
      {/* Desktop sidebar toggle — only on detail pages where rail/expand applies */}
      {(desktopCollapsed || onDesktopCollapse) && (
        <button
          type="button"
          onClick={desktopCollapsed ? onDesktopExpand : onDesktopCollapse}
          className={`hidden lg:flex rounded-md text-muted-foreground hover:bg-muted hover:text-foreground ${desktopCollapsed ? "p-1" : "p-1.5"}`}
          aria-label={desktopCollapsed ? "Expand navigation" : "Collapse navigation"}
          title={desktopCollapsed ? "Expand navigation" : "Collapse navigation"}
        >
          {desktopCollapsed
            ? <ExpandIcon className="h-3.5 w-3.5" />
            : <CollapseIcon className="h-5 w-5" />}
        </button>
      )}
    </div>
  );
}

interface SidebarMainNavProps {
  readonly isSuperuser: boolean;
  readonly desktopCollapsed: boolean;
  readonly onClose: () => void;
}

function SidebarMainNav({ isSuperuser, desktopCollapsed, onClose }: SidebarMainNavProps) {
  const { t } = useTranslation();
  const location = useLocation();

  // Superusers only use /admin — no primary nav, just a flex spacer above the bottom nav
  // (not shown during impersonation, since effectiveUser reflects the impersonated user there).
  if (isSuperuser) return <div className="flex-1" />;

  const NAV_ITEMS: NavItem[] = [
    { label: t("nav.dashboard"), href: "/home", icon: AppIcons.Dashboard, exact: true },
    { label: t("nav.projects"), href: "/projects", icon: AppIcons.Projects },
    { label: t("nav.drafts"), href: "/drafts", icon: AppIcons.Drafts },
    { label: t("nav.collections"), href: "/collections", icon: AppIcons.Collections },
    { label: t("nav.equipment"), href: "/looms", icon: AppIcons.Equipment },
    { label: t("nav.yarn"), href: "/yarn", icon: AppIcons.Yarn },
  ];

  return (
    <>
      <div className="shrink-0 pt-2">
        <OnboardingChecklist collapsed={desktopCollapsed} />
      </div>
      <nav className="flex-1 overflow-y-auto px-3 py-3 space-y-0.5">
        {NAV_ITEMS.map(({ label, href, icon: Icon, exact }) => (
          <Link
            key={href}
            to={href}
            onClick={onClose}
            className={navCls(isActive(location.pathname, href, exact), desktopCollapsed)}
            title={desktopCollapsed ? label : undefined}
          >
            <Icon className={iconCls(isActive(location.pathname, href, exact))} strokeWidth={1.75} />
            <span className={desktopCollapsed ? "lg:hidden" : ""}>{label}</span>
          </Link>
        ))}
      </nav>
    </>
  );
}

interface SidebarBottomNavProps {
  readonly user: User | null;
  readonly desktopCollapsed: boolean;
  readonly onClose: () => void;
  readonly onFeedbackClick: () => void;
}

function SidebarBottomNav({ user, desktopCollapsed, onClose, onFeedbackClick }: SidebarBottomNavProps) {
  const { t } = useTranslation();
  const { signOut } = useClerk();
  const [expandedGroup, setExpandedGroup] = useState<NavGroup | null>(null);

  function toggleGroup(group: NavGroup) {
    setExpandedGroup((prev) => (prev === group ? null : group));
  }

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
    { id: "users", label: t("superuserSections.users") },
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
    { id: "neon", label: t("superuserSections.neon") },
    { id: "sandbox", label: t("superuserSections.sandbox") },
  ];

  return (
    <div className={`shrink-0 border-t border-border px-3 py-3 space-y-0.5 ${desktopCollapsed ? "lg:px-2" : ""}`}>
      <NavGroupSection
        icon={SettingsIcon}
        label={t("nav.settings")}
        expanded={expandedGroup === "settings"}
        onToggle={() => toggleGroup("settings")}
        desktopCollapsed={desktopCollapsed}
        onClose={onClose}
        sections={SETTINGS_SECTIONS}
        basePath="/settings"
      />

      {user?.is_admin && (
        <NavGroupSection
          icon={AdminIcon}
          label={t("nav.admin")}
          expanded={expandedGroup === "admin"}
          onToggle={() => toggleGroup("admin")}
          desktopCollapsed={desktopCollapsed}
          onClose={onClose}
          sections={ADMIN_SECTIONS}
          basePath="/admin"
        />
      )}

      {user?.is_superuser && (
        <NavGroupSection
          icon={SuperuserIcon}
          label={t("nav.superuser")}
          expanded={expandedGroup === "superuser"}
          onToggle={() => toggleGroup("superuser")}
          desktopCollapsed={desktopCollapsed}
          onClose={onClose}
          sections={SUPERUSER_SECTIONS}
          basePath="/superuser"
        />
      )}

      <button
        type="button"
        onClick={onFeedbackClick}
        className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground ${desktopCollapsed ? "lg:justify-center lg:px-2" : ""}`}
        title={desktopCollapsed ? t("nav.sendFeedback") : undefined}
      >
        <AppIcons.Feedback className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} />
        <span className={desktopCollapsed ? "lg:hidden" : ""}>{t("nav.sendFeedback")}</span>
      </button>

      <Link
        to="/costs"
        onClick={onClose}
        className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground ${desktopCollapsed ? "lg:justify-center lg:px-2" : ""}`}
        title={desktopCollapsed ? t("nav.supportWeftmark") : undefined}
      >
        <AppIcons.Support className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} />
        <span className={desktopCollapsed ? "lg:hidden" : ""}>{t("nav.supportWeftmark")}</span>
      </Link>

      <button
        type="button"
        onClick={() => signOut()}
        className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-subdued transition-colors hover:bg-muted hover:text-foreground ${desktopCollapsed ? "lg:justify-center lg:px-2" : ""}`}
        title={desktopCollapsed ? t("nav.signOut") : undefined}
      >
        <AppIcons.Logout className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} />
        <span className={desktopCollapsed ? "lg:hidden" : ""}>{t("nav.signOut")}</span>
      </button>
    </div>
  );
}

interface SidebarUserFooterProps {
  readonly user: User | null;
  readonly isImpersonating: boolean;
  readonly impersonatedUser: User | null;
  readonly endImpersonation: () => void;
  readonly desktopCollapsed: boolean;
}

function SidebarUserFooter({ user, isImpersonating, impersonatedUser, endImpersonation, desktopCollapsed }: SidebarUserFooterProps) {
  const { t } = useTranslation();
  return (
    <>
      {/* Impersonated user identity — shown above real user when impersonating */}
      {isImpersonating && impersonatedUser && (
        <div className={`shrink-0 border-t border-amber-500/40 bg-amber-500/10 px-4 py-3 ${desktopCollapsed ? "lg:hidden" : ""}`}>
          <div className="flex items-center gap-2">
            <p className="min-w-0 flex-1 truncate text-xs font-medium text-foreground">{impersonatedUser.display_name}</p>
            <button
              type="button"
              onClick={endImpersonation}
              className="shrink-0 rounded px-1.5 py-0.5 text-xs font-medium text-amber-700 ring-1 ring-amber-500/50 hover:bg-amber-500/20 dark:text-amber-400 transition-colors"
            >
              {t("impersonation.stop")}
            </button>
          </div>
          <p className="truncate text-xs text-muted-foreground">{impersonatedUser.email}</p>
        </div>
      )}

      {/* User identity — hidden on desktop in rail mode */}
      {user && (
        <div className={`shrink-0 border-t border-border bg-muted px-4 py-3 ${desktopCollapsed ? "lg:hidden" : ""}`}>
          <p className="truncate text-xs font-medium text-foreground">{user.display_name}</p>
          <p className="truncate text-xs text-muted-foreground">{user.email}</p>
        </div>
      )}
    </>
  );
}

export function Sidebar({ open, onClose, desktopCollapsed = false, onDesktopExpand, onDesktopCollapse }: Props) {
  const { user } = useAuth();
  const { isImpersonating, impersonatedUser, endImpersonation } = useImpersonation();
  // For nav visibility: use the impersonated user when active, so the primary
  // nav shows and reflects the impersonated user's role. Admin/superuser
  // console guards below still use the real `user`.
  const effectiveUser = isImpersonating ? impersonatedUser : user;
  const [feedbackOpen, setFeedbackOpen] = useState(false);

  return (
    <>
      {/* Mobile backdrop */}
      {open && (
        <div
          role="button"
          tabIndex={0}
          aria-label="Close"
          className="fixed inset-0 z-20 bg-black/40 lg:hidden"
          onClick={onClose}
          onKeyDown={(e) => { if (e.key === "Escape" || e.key === "Enter" || e.key === " ") onClose(); }}
        />
      )}

      {/* Sidebar panel */}
      <aside
        className={`fixed inset-y-0 left-0 z-30 flex flex-col bg-card border-r border-border transition-all duration-200 ease-in-out lg:static lg:z-auto lg:translate-x-0 ${
          open ? "translate-x-0 w-60" : "-translate-x-full w-60"
        } ${desktopCollapsed ? "lg:w-14" : "lg:w-60"}`}
      >
        <SidebarHeader
          desktopCollapsed={desktopCollapsed}
          onClose={onClose}
          onDesktopExpand={onDesktopExpand}
          onDesktopCollapse={onDesktopCollapse}
        />

        <SidebarMainNav
          isSuperuser={!!effectiveUser?.is_superuser}
          desktopCollapsed={desktopCollapsed}
          onClose={onClose}
        />

        <SidebarBottomNav
          user={user}
          desktopCollapsed={desktopCollapsed}
          onClose={onClose}
          onFeedbackClick={() => setFeedbackOpen(true)}
        />

        <SidebarUserFooter
          user={user}
          isImpersonating={isImpersonating}
          impersonatedUser={impersonatedUser}
          endImpersonation={endImpersonation}
          desktopCollapsed={desktopCollapsed}
        />
      </aside>

      {feedbackOpen && <FeedbackModal onClose={() => setFeedbackOpen(false)} />}
    </>
  );
}
