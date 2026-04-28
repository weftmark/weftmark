import { Link } from "react-router-dom";
import { WeftmarkLogo } from "@/components/WeftmarkLogo";
import { PublicFooter } from "@/components/PublicFooter";

const FEATURES = [
  {
    title: "Track your weaves",
    body: "Upload your WIF draft and step through every pick. Weftmark keeps your place so you can put down the shuttle and pick it right back up.",
  },
  {
    title: "Record every pick",
    body: "Advance, reverse, or jump to any row. Mark a project complete when the last pick is woven in.",
  },
  {
    title: "Manage your tools",
    body: "Keep a record of your looms and yarn. Assign a loom to a project and track what's on the beam.",
  },
];

export function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col bg-stone-50 text-stone-900">
      <header className="border-b border-stone-200 bg-stone-50 px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <div className="flex items-center gap-3">
            <WeftmarkLogo className="h-8 w-auto text-amber-800" />
            <span className="text-lg font-semibold tracking-tight">Weftmark</span>
          </div>
          <Link
            to="/login"
            className="text-sm text-stone-600 hover:text-stone-900 transition-colors"
          >
            Sign in
          </Link>
        </div>
      </header>

      <main className="flex-1">
        <section className="mx-auto max-w-4xl px-6 py-20 text-center">
          <WeftmarkLogo className="mx-auto mb-6 h-16 w-auto text-amber-800" />
          <h1 className="mb-3 text-4xl font-bold tracking-tight sm:text-5xl">Weftmark</h1>
          <p className="mb-6 text-xl text-stone-600 sm:text-2xl">
            Track your weaving, from first pick to finished cloth.
          </p>
          <p className="mx-auto mb-10 max-w-xl text-base text-stone-600">
            A weaving companion for handweavers. Upload your WIF file, follow your draft row by row,
            and keep a record of every project from first warp to last pick.
          </p>
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
            <Link
              to="/login"
              className="rounded-md bg-amber-800 px-6 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-amber-900 transition-colors"
            >
              Sign In
            </Link>
            <Link
              to="/register"
              className="rounded-md border border-amber-800 px-6 py-2.5 text-sm font-medium text-amber-800 hover:bg-amber-50 transition-colors"
            >
              Create Account
            </Link>
          </div>
        </section>

        <section className="border-t border-stone-200 bg-stone-100 px-6 py-16">
          <div className="mx-auto max-w-4xl">
            <div className="grid gap-8 sm:grid-cols-3">
              {FEATURES.map(({ title, body }) => (
                <div key={title} className="space-y-2">
                  <h2 className="text-base font-semibold text-stone-900">{title}</h2>
                  <p className="text-sm text-stone-600 leading-relaxed">{body}</p>
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
