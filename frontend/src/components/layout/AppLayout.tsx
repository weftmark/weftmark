import { useState } from "react";
import { Menu } from "lucide-react";
import { Sidebar } from "@/components/layout/Sidebar";
import { VersionBadge } from "@/components/layout/VersionFooter";
import type { ReactNode } from "react";

interface Props {
  children: ReactNode;
}

export function AppLayout({ children }: Props) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-stone-50">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile top bar — hidden on lg+ where sidebar is always visible */}
        <div className="flex h-14 shrink-0 items-center border-b border-stone-200 bg-white px-4 lg:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="rounded-md p-1.5 text-stone-500 hover:bg-stone-100 hover:text-stone-900"
            aria-label="Open navigation"
          >
            <Menu className="h-5 w-5" />
          </button>
        </div>

        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>

      <VersionBadge />
    </div>
  );
}
