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
  EllipsisVertical,
  ExternalLink,
  FileDown,
  FolderOpen,
  Footprints,
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
  Treadle: Footprints,
  Lift: ChevronsUp,
  Planning: CircleHelp,
  ProjectActive: Zap,
  ProjectCompleted: CircleCheck,

  // ── Navigation ────────────────────────────────────────────────────────────
  Dashboard: LayoutDashboard,
  Drafts: FolderOpen,
  Draft: Scroll,
  Projects: Activity,
  Equipment: Wrench,
  Collections: BookOpen,
  Yarn: Spool,
  Settings: Settings,
  Admin: ShieldCheck,
  Superuser: Terminal,
  Logout: LogOut,
  Feedback: MessageSquare,
  Onboarding: ListChecks,
  Support: Heart,

  // ── UI chrome ─────────────────────────────────────────────────────────────
  Edit: Pencil,
  MobileMenu: Menu,
  Close: X,
  Spinner: Loader2,
  Print: Printer,
  SaveAsPdf: FileDown,
  ChevronDown: ChevronDown,
  ChevronRight: ChevronRight,
  ChevronDoubleLeft: ChevronsLeft,
  ChevronDoubleRight: ChevronsRight,
  PresentMode: Maximize2,
  ExitPresentMode: Minimize2,
  ZoomIn: ZoomIn,
  ZoomOut: ZoomOut,
  ZoomReset: RotateCcw,
  ZoomFit: Scan,

  // ── Sharing ───────────────────────────────────────────────────────────────
  Share: Share2,
  CopyLink: Copy,
  ExternalLink: ExternalLink,

  // ── Project status actions ────────────────────────────────────────────────
  StatusActions: EllipsisVertical,

  // ── Landing page features ─────────────────────────────────────────────────
  DesignLibrary: Layers,
  PickTracking: CheckSquare,
  ToolManagement: Wrench,

  // ── Generic ───────────────────────────────────────────────────────────────
  Check: Check,
} as const;
