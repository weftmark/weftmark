import { Link, useLocation } from "react-router-dom";
import { useClerk } from "@clerk/clerk-react";
import { AppIcons, type LucideIcon } from "@/lib/icons";
import { WeftmarkLogo } from "@/components/WeftmarkLogo";
import { useAuth } from "@/hooks/useAuth";

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  exact?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/home", icon: AppIcons.dashboard, exact: true },
  { label: "Equipment", href: "/looms", icon: AppIcons.equipment },
  { label: "Drafts", href: "/drafts", icon: AppIcons.drafts },
  { label: "Projects", href: "/projects", icon: AppIcons.projects },
];

const SETTINGS_SECTIONS = [
  { id: "appearance", label: "Appearance" },
  { id: "preferences", label: "Preferences" },
  { id: "privacy", label: "Privacy & data" },
  { id: "terms", label: "Terms" },
  { id: "account", label: "Account" },
];

interface Props {
  open: boolean;
  onClose: () => void;
  desktopCollapsed?: boolean;
  onDesktopExpand?: () => void;
}

export function Sidebar({ open, onClose, desktopCollapsed = false, onDesktopExpand }: Props) {
  const location = useLocation();
  const { user } = useAuth();
  const { signOut } = useClerk();

  function isActive(href: string, exact = false) {
    if (exact) return location.pathname === href;
    return location.pathname === href || location.pathname.startsWith(href + "/");
  }

  function navCls(href: string, exact?: boolean) {
    const active = isActive(href, exact);
    return `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
      active
        ? "bg-accent text-accent-foreground"
        : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
    } ${desktopCollapsed ? "lg:justify-center lg:px-2" : ""}`;
  }

  function iconCls(href: string, exact?: boolean) {
    return `h-4 w-4 shrink-0 ${
      isActive(href, exact) ? "text-accent-foreground" : "text-muted-foreground"
    }`;
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
        </div>

        {/* Primary nav — hidden for superusers (they only use /admin) */}
        {!user?.is_superuser && (
          <nav className="flex-1 overflow-y-auto px-3 py-3 space-y-0.5">
            {NAV_ITEMS.map(({ label, href, icon: Icon, exact }) => (
              <Link
                key={href}
                to={href}
                onClick={onClose}
                className={navCls(href, exact)}
                title={desktopCollapsed ? label : undefined}
              >
                <Icon className={iconCls(href, exact)} strokeWidth={1.75} />
                <span className={desktopCollapsed ? "lg:hidden" : ""}>{label}</span>
              </Link>
            ))}
          </nav>
        )}

        {/* Spacer for superusers */}
        {user?.is_superuser && <div className="flex-1" />}

        {/* Bottom nav */}
        <div className={`shrink-0 border-t border-border px-3 py-3 space-y-0.5 ${desktopCollapsed ? "lg:px-2" : ""}`}>
          <Link
            to="/settings/appearance"
            onClick={onClose}
            className={navCls("/settings")}
            title={desktopCollapsed ? "Settings" : undefined}
          >
            <AppIcons.settings className={iconCls("/settings")} strokeWidth={1.75} />
            <span className={desktopCollapsed ? "lg:hidden" : ""}>Settings</span>
          </Link>

          {isActive("/settings") && !desktopCollapsed && (
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
            <Link
              to="/admin"
              onClick={onClose}
              className={navCls("/admin")}
              title={desktopCollapsed ? "Admin" : undefined}
            >
              <AppIcons.admin className={iconCls("/admin")} strokeWidth={1.75} />
              <span className={desktopCollapsed ? "lg:hidden" : ""}>Admin</span>
            </Link>
          )}

          <button
            onClick={() => signOut()}
            className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-subdued transition-colors hover:bg-muted hover:text-foreground ${desktopCollapsed ? "lg:justify-center lg:px-2" : ""}`}
            title={desktopCollapsed ? "Sign out" : undefined}
          >
            <AppIcons.logout className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.75} />
            <span className={desktopCollapsed ? "lg:hidden" : ""}>Sign out</span>
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
    </>
  );
}
