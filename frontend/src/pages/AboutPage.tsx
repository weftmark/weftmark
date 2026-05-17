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
            <span className="text-lg font-semibold tracking-tight" style={{ fontFamily: '"Segoe UI", system-ui, sans-serif' }}>weftmark</span>
          </Link>
        </div>
      </header>

      <main className="flex-1 px-6 py-16">
        <div className="mx-auto max-w-2xl space-y-10">
          <div>
            <h1 className="text-3xl font-bold tracking-tight mb-4">About weftmark</h1>
            <p className="text-stone-600 leading-relaxed">
              weftmark is a weaving companion built by a weaver to solve a weaver's problem: keeping
              track of where you are in a long treadling sequence. It is not a commercial product. It
              is a personal project, built in spare hours, to scratch a specific itch.
            </p>
          </div>

          <div className="space-y-3">
            <h2 className="text-lg font-semibold">A note from the developer</h2>
            <div className="space-y-3 text-stone-600 leading-relaxed">
              <p>
                In the last couple of years, my wife has grown a passion for weaving and I've
                learned about the process along the way. As she dove into pattern design and WIF
                files, she asked if I could build a tool to help her track the lifts on her Jane
                without needing a pencil and paper.
              </p>
              <p>
                I work in industrial automation and although I touch a lot of technology and
                infrastructure, I'm not an application developer — I'm an integrator.
              </p>
              <p>
                Modern AI tools like Claude have allowed me to play the role of "product owner" by defining
                architecture, documenting scope, and nudging design with constant feedback; without
                the demands of learning every framework and toolkit along the way.
              </p>
              <p>
                This is very much a learning experience. I plan to continue posting all code on
                GitHub and it is open for review and criticism.
              </p>
              <p className="text-stone-500">All the best — Derek</p>
            </div>
          </div>

          <div className="space-y-3">
            <h2 className="text-lg font-semibold">How it was built</h2>
            <p className="text-stone-600 leading-relaxed">
              weftmark was built with significant assistance from AI tools — specifically Anthropic's
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
            <h2 className="text-lg font-semibold">Source code</h2>
            <p className="text-stone-600 leading-relaxed">
              The source code is available on{" "}
              <a
                href="https://github.com/weftmark/weftmark"
                target="_blank"
                rel="noopener noreferrer"
                className="text-amber-800 underline hover:text-amber-900 transition-colors"
              >
                GitHub
              </a>
              .
            </p>
          </div>
        </div>
      </main>

      <PublicFooter />
    </div>
  );
}
