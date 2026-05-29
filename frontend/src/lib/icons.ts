/**
 * Centralized icon registry — change a key here to update every usage site.
 * Import icons and the LucideIcon type from this module, not from lucide-react.
 */
import {
  Activity,
  BookOpen,
  Check,
  CheckSquare,
  ChevronDown,
  ListChecks,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  ChevronsUp,
  CircleCheck,
  CircleHelp,
  Copy,
  ExternalLink,
  FileDown,
  FolderOpen,
  Footprints,
  GripVertical,
  Heart,
  LayoutDashboard,
  Layers,
  Loader2,
  LogOut,
  Maximize2,
  Menu,
  MessageSquare,
  Minimize2,
  Pencil,
  Printer,
  RotateCcw,
  Scan,
  Scroll,
  Settings,
  Share2,
  Spool,
  ShieldCheck,
  Terminal,
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
  collections: BookOpen,
  yarn: Spool,
  settings: Settings,
  admin: ShieldCheck,
  superuser: Terminal,
  logout: LogOut,
  feedback: MessageSquare,
  onboarding: ListChecks,
  support: Heart,

  // ── UI chrome ─────────────────────────────────────────────────────────────
  grip: GripVertical,
  edit: Pencil,
  mobileMenu: Menu,
  close: X,
  spinner: Loader2,
  print: Printer,
  saveAsPdf: FileDown,
  chevronDown: ChevronDown,
  chevronRight: ChevronRight,
  chevronDoubleLeft: ChevronsLeft,
  chevronDoubleRight: ChevronsRight,
  presentMode: Maximize2,
  exitPresentMode: Minimize2,
  zoomIn: ZoomIn,
  zoomOut: ZoomOut,
  zoomReset: RotateCcw,
  zoomFit: Scan,

  // ── Sharing ───────────────────────────────────────────────────────────────
  share: Share2,
  copyLink: Copy,
  externalLink: ExternalLink,

  // ── Landing page features ─────────────────────────────────────────────────
  designLibrary: Layers,
  pickTracking: CheckSquare,
  toolManagement: Wrench,

  // ── Generic ───────────────────────────────────────────────────────────────
  check: Check,
} as const;
