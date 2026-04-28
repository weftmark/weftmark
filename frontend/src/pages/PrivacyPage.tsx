import { Link } from "react-router-dom";
import { WeftmarkLogo } from "@/components/WeftmarkLogo";
import { PublicFooter } from "@/components/PublicFooter";

const DATA_COMMITMENTS = [
  "Your WIF files are stored privately and are only accessible to you.",
  "Photos you upload are stored privately and are only accessible to you.",
  "Your weaving activity data (picks, looms, yarn, projects) is stored privately.",
  "Your data is not sold, shared with third parties, or used to train AI models without your consent.",
  "You can delete your account and all associated data at any time from your account settings.",
  "Authentication is handled by Clerk. Weftmark does not store your password.",
  "Email addresses are used only for account management — no marketing email.",
];

export function PrivacyPage() {
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
            <h1 className="text-3xl font-bold tracking-tight mb-2">Data &amp; Privacy</h1>
            <p className="text-sm text-stone-400">Last updated: [placeholder — update before launch]</p>
          </div>

          <div className="space-y-3">
            <p className="text-stone-600 leading-relaxed">
              Weftmark is a personal project. It collects only what it needs to function. Here is a
              plain-language summary of how your data is handled:
            </p>
            <ul className="space-y-3">
              {DATA_COMMITMENTS.map((item) => (
                <li key={item} className="flex gap-3 text-stone-600">
                  <span className="mt-1 shrink-0 text-amber-700">&#8212;</span>
                  <span className="leading-relaxed">{item}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="space-y-3">
            <h2 className="text-lg font-semibold">Questions</h2>
            <p className="text-stone-600 leading-relaxed">
              If you have questions about your data, reach out through the project's GitHub
              repository.{" "}
              <span className="text-stone-400 text-sm">[Link coming — see issue #52]</span>
            </p>
          </div>
        </div>
      </main>

      <PublicFooter />
    </div>
  );
}
