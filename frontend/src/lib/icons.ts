/**
 * Centralized icon registry — change a key here to update every usage site.
 * Import icons and the LucideIcon type from this module, not from lucide-react.
 */
import {
  Activity,
  CheckSquare,
  ChevronRight,
  ChevronsUp,
  CircleCheck,
  CircleHelp,
  FolderOpen,
  Footprints,
  LayoutDashboard,
  Layers,
  LogOut,
  Menu,
  Scroll,
  Settings,
  ShieldCheck,
  Wrench,
  X,
  Zap,
} from "lucide-react";

export type { LucideIcon } from "lucide-react";

export const AppIcons = {
  // ── Weaving — activity types ──────────────────────────────────────────────
  treadle: Footprints,
  lift: ChevronsUp,
  planning: CircleHelp,
  activityActive: Zap,
  activityCompleted: CircleCheck,

  // ── Navigation ────────────────────────────────────────────────────────────
  dashboard: LayoutDashboard,
  drafts: FolderOpen,
  draft: Scroll,
  projects: Activity,
  equipment: Wrench,
  settings: Settings,
  admin: ShieldCheck,
  logout: LogOut,

  // ── UI chrome ─────────────────────────────────────────────────────────────
  mobileMenu: Menu,
  close: X,
  chevronRight: ChevronRight,

  // ── Landing page features ─────────────────────────────────────────────────
  designLibrary: Layers,
  pickTracking: CheckSquare,
  toolManagement: Wrench,
} as const;
