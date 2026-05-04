import { Link } from "react-router-dom";
import { AppIcons } from "@/lib/icons";
import { WeftmarkLogo } from "@/components/WeftmarkLogo";
import { PublicFooter } from "@/components/PublicFooter";

const FEATURES = [
  {
    title: "Track your weaves",
    body: "Upload your WIF draft and step through every pick. weftmark keeps your place so you can put down the shuttle and pick it right back up.",
    Icon: AppIcons.designLibrary,
  },
  {
    title: "Record every pick",
    body: "Advance, reverse, or jump to any row. Mark an activity complete when the last pick is woven in.",
    Icon: AppIcons.pickTracking,
  },
  {
    title: "Manage your tools",
    body: "Keep a record of your looms and yarn. Assign a loom to a draft and track what's on the beam.",
    Icon: AppIcons.toolManagement,
  },
];

export function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col bg-stone-50 text-stone-900">
      {/* Grain texture overlay */}
      <svg
        className="pointer-events-none fixed inset-0 z-50 h-full w-full opacity-[0.045]"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <filter id="grain">
          <feTurbulence type="fractalNoise" baseFrequency="0.72" numOctaves="4" stitchTiles="stitch" />
        </filter>
        <rect width="100%" height="100%" filter="url(#grain)" />
      </svg>

      <header className="sticky top-0 z-10 bg-stone-50/95 px-6 py-4 backdrop-blur shadow-sm shadow-stone-900/5">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <div className="flex items-center gap-2.5">
            <WeftmarkLogo className="h-7 w-auto text-zinc-800" />
            <span className="text-base font-semibold tracking-tight" style={{ fontFamily: '"Segoe UI", system-ui, sans-serif' }}>weftmark</span>
          </div>
          <Link
            to="/login"
            className="text-sm font-medium text-stone-600 transition-colors hover:text-stone-900"
          >
            Sign in
          </Link>
        </div>
      </header>

      <main className="flex-1">
        {/* Hero */}
        <section
          className="relative bg-gradient-to-br from-stone-100 via-stone-50 to-white px-6 pt-16 pb-32 lg:pt-24 lg:pb-40"
          style={{ clipPath: "polygon(0 0, 100% 0, 100% 88%, 0 100%)" }}
        >
          <div className="mx-auto max-w-6xl">
            <div className="grid items-center gap-12 lg:grid-cols-[1fr_1.4fr]">
              <div className="order-2 lg:order-1">
                <span className="mb-5 inline-block rounded-full bg-amber-100 px-3.5 py-1 text-xs font-medium tracking-wide text-amber-700">
                  Weaving companion for handweavers
                </span>
                <h1 className="mb-5 text-4xl font-bold tracking-tight text-stone-900 sm:text-5xl lg:text-6xl">
                  Your weaving,
                  <br />
                  <span className="text-amber-600">row by row.</span>
                </h1>
                <p className="mb-8 max-w-lg text-lg leading-relaxed text-stone-600">
                  Upload your WIF draft, follow along pick by pick, and keep a complete record of every
                  draft from first warp to last pick.
                </p>
                <div className="flex flex-col gap-3 sm:flex-row">
                  <Link
                    to="/login"
                    className="rounded-lg bg-zinc-800 px-6 py-3 text-center text-sm font-semibold text-white shadow-md shadow-zinc-900/30 transition-colors hover:bg-zinc-900"
                  >
                    Sign In
                  </Link>
                  <Link
                    to="/register"
                    className="rounded-lg border border-stone-300 bg-white/60 px-6 py-3 text-center text-sm font-semibold text-stone-700 transition-colors hover:bg-white"
                  >
                    Create Account
                  </Link>
                </div>
              </div>

              <div className="order-1 lg:order-2">
                <div className="overflow-hidden rounded-2xl shadow-2xl shadow-stone-900/20 ring-1 ring-stone-300/60">
                  <div className="flex items-center gap-1.5 border-b border-stone-200 bg-stone-200/80 px-4 py-3">
                    <span className="h-3 w-3 rounded-full bg-red-400" />
                    <span className="h-3 w-3 rounded-full bg-amber-400" />
                    <span className="h-3 w-3 rounded-full bg-green-500" />
                    <span className="ml-3 flex-1 rounded bg-stone-300/60 px-3 py-1 text-center text-xs text-stone-500">
                      weftmark.com
                    </span>
                  </div>
                  <video autoPlay muted loop playsInline className="w-full">
                    <source src="/hearts-treadle.mp4" type="video/mp4" />
                    <img src="/hearts-treadle.webp" alt="Weftmark draft viewer demo" />
                  </video>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Features — floats over angled hero clip */}
        <section className="relative z-10 -mt-12 px-6 pb-20">
          <div className="mx-auto max-w-6xl">
            <h2 className="mb-10 text-center text-2xl font-bold tracking-tight text-stone-900">
              Everything you need at the loom
            </h2>
            <div className="grid gap-6 sm:grid-cols-3">
              {FEATURES.map(({ title, body, Icon }) => (
                <div
                  key={title}
                  className="rounded-2xl bg-white p-7 shadow-md ring-1 ring-stone-200/80 transition-all duration-200 hover:-translate-y-1 hover:shadow-xl"
                >
                  <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl bg-amber-100 text-amber-600">
                    <Icon className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
                  </div>
                  <h3 className="mb-2 text-base font-semibold text-stone-900">{title}</h3>
                  <p className="text-sm leading-relaxed text-stone-500">{body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>

      <PublicFooter />
    </div>
  );
}
