import type { ReactNode } from "react";
import { WeftmarkLogo } from "@/components/WeftmarkLogo";

interface Props {
  children: ReactNode;
  footer?: ReactNode;
  /** Skip the white card wrapper — Clerk pages use this so Clerk renders its own card naturally. */
  naked?: boolean;
}

export function AuthCard({ children, footer, naked = false }: Props) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-stone-50 px-4 py-12">
      <svg
        className="pointer-events-none fixed inset-0 z-50 h-full w-full opacity-[0.045]"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <filter id="grain-auth">
          <feTurbulence type="fractalNoise" baseFrequency="0.72" numOctaves="4" stitchTiles="stitch" />
        </filter>
        <rect width="100%" height="100%" filter="url(#grain-auth)" />
      </svg>

      <div className="mb-6 flex items-center gap-2.5">
        <WeftmarkLogo className="h-7 w-auto text-zinc-800" />
        <span
          className="text-base font-semibold tracking-tight text-zinc-800"
          style={{ fontFamily: '"Segoe UI", system-ui, sans-serif' }}
        >
          weftmark
        </span>
      </div>

      {naked ? (
        <div className="w-full max-w-sm">{children}</div>
      ) : (
        <div className="w-full max-w-sm rounded-2xl border border-stone-200 bg-white px-8 pb-8 pt-7 shadow-sm">
          {children}
        </div>
      )}

      {footer && <div className="mt-5 text-center text-xs text-stone-500">{footer}</div>}
    </div>
  );
}
