import { Link, useLocation } from "react-router-dom";
import { useClerk } from "@clerk/clerk-react";
import {
  LayoutDashboard,
  FolderOpen,
  Activity,
  Wrench,
  Settings,
  ShieldCheck,
  LogOut,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { WeftmarkLogo } from "@/components/WeftmarkLogo";
import { useAuth } from "@/hooks/useAuth";

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  exact?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/home", icon: LayoutDashboard, exact: true },
  { label: "Projects", href: "/projects", icon: FolderOpen },
  { label: "Activities", href: "/activities", icon: Activity },
  { label: "Equipment", href: "/looms", icon: Wrench },
];

interface Props {
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ open, onClose }: Props) {
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
        ? "bg-amber-50 text-amber-800"
        : "text-stone-600 hover:bg-stone-100 hover:text-stone-900"
    }`;
  }

  function iconCls(href: string, exact?: boolean) {
    return `h-4 w-4 shrink-0 ${
      isActive(href, exact) ? "text-amber-600" : "text-stone-400"
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
        className={`fixed inset-y-0 left-0 z-30 flex w-60 flex-col bg-white border-r border-stone-200 transition-transform duration-200 ease-in-out lg:static lg:z-auto lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Logo */}
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-stone-200 px-4">
          <Link to="/home" className="flex items-center gap-2.5" onClick={onClose}>
            <WeftmarkLogo className="h-6 w-auto text-zinc-800" />
            <span className="text-sm font-semibold tracking-tight text-stone-900" style={{ fontFamily: '"Segoe UI", system-ui, sans-serif' }}>weftmark</span>
          </Link>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-stone-400 hover:text-stone-600 lg:hidden"
            aria-label="Close menu"
          >
            <X className="h-4 w-4" />
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
              >
                <Icon className={iconCls(href, exact)} strokeWidth={1.75} />
                {label}
              </Link>
            ))}
          </nav>
        )}

        {/* Spacer for superusers */}
        {user?.is_superuser && <div className="flex-1" />}

        {/* Bottom nav */}
        <div className="shrink-0 border-t border-stone-200 px-3 py-3 space-y-0.5">
          <Link to="/settings" onClick={onClose} className={navCls("/settings")}>
            <Settings className={iconCls("/settings")} strokeWidth={1.75} />
            Settings
          </Link>

          {user?.is_admin && (
            <Link to="/admin" onClick={onClose} className={navCls("/admin")}>
              <ShieldCheck className={iconCls("/admin")} strokeWidth={1.75} />
              Admin
            </Link>
          )}

          <button
            onClick={() => signOut()}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-stone-600 transition-colors hover:bg-stone-100 hover:text-stone-900"
          >
            <LogOut className="h-4 w-4 shrink-0 text-stone-400" strokeWidth={1.75} />
            Sign out
          </button>
        </div>

        {/* User identity */}
        {user && (
          <div className="shrink-0 border-t border-stone-200 bg-stone-50 px-4 py-3">
            <p className="truncate text-xs font-medium text-stone-900">{user.display_name}</p>
            <p className="truncate text-xs text-stone-400">{user.email}</p>
          </div>
        )}
      </aside>
    </>
  );
}
