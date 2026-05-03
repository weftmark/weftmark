import { Link } from "react-router-dom";
import { Layers, CheckSquare, Wrench } from "lucide-react";
import { WeftmarkLogo } from "@/components/WeftmarkLogo";
import { PublicFooter } from "@/components/PublicFooter";

const FEATURES = [
  {
    title: "Track your weaves",
    body: "Upload your WIF draft and step through every pick. Weftmark keeps your place so you can put down the shuttle and pick it right back up.",
    Icon: Layers,
  },
  {
    title: "Record every pick",
    body: "Advance, reverse, or jump to any row. Mark a project complete when the last pick is woven in.",
    Icon: CheckSquare,
  },
  {
    title: "Manage your tools",
    body: "Keep a record of your looms and yarn. Assign a loom to a project and track what's on the beam.",
    Icon: Wrench,
  },
];

export function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col bg-white text-stone-900">
      <header className="sticky top-0 z-10 border-b border-stone-200 bg-white/95 px-6 py-4 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <div className="flex items-center gap-2.5">
            <WeftmarkLogo className="h-7 w-auto text-amber-800" />
            <span className="text-base font-semibold tracking-tight">Weftmark</span>
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
        <section className="bg-gradient-to-br from-stone-50 via-white to-amber-50/30 px-6 py-16 lg:py-24">
          <div className="mx-auto max-w-6xl">
            <div className="grid items-center gap-12 lg:grid-cols-2">
              {/* Text */}
              <div className="order-2 lg:order-1">
                <span className="mb-5 inline-block rounded-full bg-amber-100 px-3.5 py-1 text-xs font-medium tracking-wide text-amber-800">
                  Weaving companion for handweavers
                </span>
                <h1 className="mb-5 text-4xl font-bold tracking-tight text-stone-900 sm:text-5xl lg:text-6xl">
                  Your weaving,
                  <br />
                  <span className="text-amber-800">row by row.</span>
                </h1>
                <p className="mb-8 max-w-lg text-lg leading-relaxed text-stone-600">
                  Upload your WIF draft, follow along pick by pick, and keep a complete record of every
                  project from first warp to last pick.
                </p>
                <div className="flex flex-col gap-3 sm:flex-row">
                  <Link
                    to="/login"
                    className="rounded-lg bg-amber-800 px-6 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-amber-900"
                  >
                    Sign In
                  </Link>
                  <Link
                    to="/register"
                    className="rounded-lg border border-stone-300 px-6 py-3 text-sm font-semibold text-stone-700 transition-colors hover:bg-stone-50"
                  >
                    Create Account
                  </Link>
                </div>
              </div>

              {/* Video demo */}
              <div className="order-1 lg:order-2">
                <div className="overflow-hidden rounded-2xl shadow-2xl ring-1 ring-stone-200/80">
                  {/* Browser chrome */}
                  <div className="flex items-center gap-1.5 border-b border-stone-200 bg-stone-100 px-4 py-3">
                    <span className="h-3 w-3 rounded-full bg-red-400" />
                    <span className="h-3 w-3 rounded-full bg-amber-400" />
                    <span className="h-3 w-3 rounded-full bg-green-500" />
                    <span className="ml-3 flex-1 rounded bg-stone-200 px-3 py-1 text-center text-xs text-stone-400">
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

        {/* Features */}
        <section className="border-t border-stone-200 bg-stone-50 px-6 py-16">
          <div className="mx-auto max-w-6xl">
            <h2 className="mb-10 text-center text-2xl font-bold tracking-tight text-stone-900">
              Everything you need at the loom
            </h2>
            <div className="grid gap-6 sm:grid-cols-3">
              {FEATURES.map(({ title, body, Icon }) => (
                <div
                  key={title}
                  className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-stone-200"
                >
                  <div className="mb-3 text-amber-700">
                    <Icon className="h-6 w-6" strokeWidth={1.75} aria-hidden="true" />
                  </div>
                  <h3 className="mb-2 text-base font-semibold text-stone-900">{title}</h3>
                  <p className="text-sm leading-relaxed text-stone-600">{body}</p>
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
