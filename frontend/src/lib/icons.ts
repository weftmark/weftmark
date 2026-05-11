/**
 * Centralized icon registry — change a key here to update every usage site.
 * Import icons and the LucideIcon type from this module, not from lucide-react.
 */
import {
  Activity,
  CheckSquare,
  ChevronDown,
  ChevronRight,
  ChevronsRight,
  ChevronsUp,
  CircleCheck,
  CircleHelp,
  FolderOpen,
  Footprints,
  LayoutDashboard,
  Layers,
  LogOut,
  Maximize2,
  Menu,
  Minimize2,
  Scroll,
  Settings,
  ShieldCheck,
  Wrench,
  X,
  Zap,
} from "lucide-react";

export type { LucideIcon } from "lucide-react";

export const AppIcons = {
  // ── Weaving — project types ───────────────────────────────────────────────
  treadle: Footprints,
  lift: ChevronsUp,
  planning: CircleHelp,
  projectActive: Zap,
  projectCompleted: CircleCheck,

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
  chevronDown: ChevronDown,
  chevronRight: ChevronRight,
  chevronDoubleRight: ChevronsRight,
  presentMode: Maximize2,
  exitPresentMode: Minimize2,

  // ── Landing page features ─────────────────────────────────────────────────
  designLibrary: Layers,
  pickTracking: CheckSquare,
  toolManagement: Wrench,
} as const;
