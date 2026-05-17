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
  FileDown,
  FolderOpen,
  Footprints,
  LayoutDashboard,
  Layers,
  Loader2,
  LogOut,
  Maximize2,
  Menu,
  Minimize2,
  Pencil,
  Printer,
  RotateCcw,
  Scan,
  Scroll,
  Settings,
  ShieldCheck,
  Wrench,
  X,
  Zap,
  ZoomIn,
  ZoomOut,
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
  edit: Pencil,
  mobileMenu: Menu,
  close: X,
  spinner: Loader2,
  print: Printer,
  saveAsPdf: FileDown,
  chevronDown: ChevronDown,
  chevronRight: ChevronRight,
  chevronDoubleRight: ChevronsRight,
  presentMode: Maximize2,
  exitPresentMode: Minimize2,
  zoomIn: ZoomIn,
  zoomOut: ZoomOut,
  zoomReset: RotateCcw,
  zoomFit: Scan,

  // ── Landing page features ─────────────────────────────────────────────────
  designLibrary: Layers,
  pickTracking: CheckSquare,
  toolManagement: Wrench,
} as const;
