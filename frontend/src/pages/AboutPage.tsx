import { Link } from "react-router-dom";
import { WeftmarkLogo } from "@/components/WeftmarkLogo";
import { PublicFooter } from "@/components/PublicFooter";

export function AboutPage() {
  return (
    <div className="flex min-h-screen flex-col bg-stone-50 text-stone-900">
      <header className="border-b border-stone-200 bg-stone-50 px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center gap-3">
          <Link to="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
            <WeftmarkLogo className="h-8 w-auto text-amber-800" />
            <span className="text-lg font-semibold tracking-tight">Weftmark</span>
          </Link>
        </div>
      </header>

      <main className="flex-1 px-6 py-16">
        <div className="mx-auto max-w-2xl space-y-10">
          <div>
            <h1 className="text-3xl font-bold tracking-tight mb-4">About Weftmark</h1>
            <p className="text-stone-600 leading-relaxed">
              Weftmark is a weaving companion built by a weaver to solve a weaver's problem: keeping
              track of where you are in a long treadling sequence. It is not a commercial product. It
              is a personal project, built in spare hours, to scratch a specific itch.
            </p>
          </div>

          <div className="space-y-3">
            <h2 className="text-lg font-semibold">How it was built</h2>
            <p className="text-stone-600 leading-relaxed">
              Weftmark was built with significant assistance from AI tools — specifically Anthropic's
              Claude. Claude helped with code generation, architecture decisions, and code review
              throughout the project. The developer is not a professional software engineer.
            </p>
            <p className="text-stone-600 leading-relaxed">
              What that means in practice: the developer understands what the application does and
              why it was built that way. AI wrote much of the implementation. Automated tests, a CI
              pipeline, and code review are in place to catch errors. The developer is responsible
              for all product decisions and data handling choices.
            </p>
          </div>

          <div className="space-y-3">
            <h2 className="text-lg font-semibold">A note from the developer</h2>
            <div className="rounded-lg border border-stone-200 bg-stone-100 px-5 py-4">
              <p className="text-sm text-stone-500 italic">
                [Placeholder — developer-voice content to be written before launch. This section
                will explain who built this, why, and what weaving means to them personally.]
              </p>
            </div>
          </div>

          <div className="space-y-3">
            <h2 className="text-lg font-semibold">Source code</h2>
            <p className="text-stone-600 leading-relaxed">
              The source code will be available on GitHub once the repository is made public.{" "}
              <span className="text-stone-400 text-sm">[Link coming — see issue #52]</span>
            </p>
          </div>
        </div>
      </main>

      <PublicFooter />
    </div>
  );
}
