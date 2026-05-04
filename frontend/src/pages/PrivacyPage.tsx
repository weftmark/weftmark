import { Link } from "react-router-dom";
import { WeftmarkLogo } from "@/components/WeftmarkLogo";
import { PublicFooter } from "@/components/PublicFooter";

export function PrivacyPage() {
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
            <h1 className="text-3xl font-bold tracking-tight mb-2">Privacy Policy</h1>
            <p className="text-sm text-stone-400">Effective: 3 May 2026</p>
          </div>

          <section className="space-y-3">
            <p className="text-stone-600 leading-relaxed">
              This policy explains what personal data WeftMark collects, why, and how it is
              handled. WeftMark is operated as an individual project. If you are located in the
              European Economic Area (EEA), the United Kingdom, or anywhere else, the same rules
              apply — we treat all users under the GDPR baseline.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-semibold">1. Data controller</h2>
            <p className="text-stone-600 leading-relaxed">
              The data controller is the operator of WeftMark. For data-related enquiries, write to{" "}
              <a
                href="mailto:admin@weftmark.com"
                className="text-amber-800 underline hover:text-amber-900 transition-colors"
              >
                admin@weftmark.com
              </a>
              .
            </p>
            <p className="text-stone-600 leading-relaxed">
              WeftMark is intended for users aged 18 or older. We do not knowingly collect personal
              data from minors.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-semibold">2. What we collect and why</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-stone-600 border-collapse">
                <thead>
                  <tr className="border-b border-stone-200">
                    <th className="py-2 pr-4 text-left font-semibold text-stone-700 w-1/3">Data</th>
                    <th className="py-2 pr-4 text-left font-semibold text-stone-700 w-1/3">Purpose</th>
                    <th className="py-2 text-left font-semibold text-stone-700">Lawful basis</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  <tr>
                    <td className="py-2 pr-4 align-top">Email address, display name</td>
                    <td className="py-2 pr-4 align-top">Account identity, access control</td>
                    <td className="py-2 align-top">Performance of contract (Art. 6(1)(b))</td>
                  </tr>
                  <tr>
                    <td className="py-2 pr-4 align-top">WIF files, photos, activity data, looms, yarn records</td>
                    <td className="py-2 pr-4 align-top">Core service — storing your weaving work</td>
                    <td className="py-2 align-top">Performance of contract (Art. 6(1)(b))</td>
                  </tr>
                  <tr>
                    <td className="py-2 pr-4 align-top">Last-active timestamp</td>
                    <td className="py-2 pr-4 align-top">Account maintenance, abuse prevention</td>
                    <td className="py-2 align-top">Legitimate interests (Art. 6(1)(f))</td>
                  </tr>
                  <tr>
                    <td className="py-2 pr-4 align-top">Audit log (event type, timestamp, actor)</td>
                    <td className="py-2 pr-4 align-top">Security, compliance, dispute resolution</td>
                    <td className="py-2 align-top">Legitimate interests (Art. 6(1)(f))</td>
                  </tr>
                  <tr>
                    <td className="py-2 pr-4 align-top">AI training consent flag</td>
                    <td className="py-2 pr-4 align-top">Honouring your preference on AI training use</td>
                    <td className="py-2 align-top">Consent (Art. 6(1)(a))</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="text-stone-600 leading-relaxed">
              We collect only what is necessary to provide the service. We do not build advertising
              profiles, sell data, or share data with third parties except the processors listed
              below.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-semibold">3. Third-party processors</h2>
            <p className="text-stone-600 leading-relaxed">
              The following processors handle data on our behalf under data processing agreements.
              All are contractually bound to process data only on our instructions.
            </p>
            <ul className="space-y-2 text-stone-600">
              <li className="flex gap-3">
                <span className="mt-1 shrink-0 text-amber-700">&#8212;</span>
                <span className="leading-relaxed">
                  <strong>Clerk</strong> — authentication and session management. Clerk stores
                  email addresses and manages sign-in. Servers are US-based; EU Standard
                  Contractual Clauses apply.
                </span>
              </li>
              <li className="flex gap-3">
                <span className="mt-1 shrink-0 text-amber-700">&#8212;</span>
                <span className="leading-relaxed">
                  <strong>Cloudflare R2</strong> — object storage for WIF files and photos.
                  Data is stored at-rest within Cloudflare's infrastructure.
                </span>
              </li>
              <li className="flex gap-3">
                <span className="mt-1 shrink-0 text-amber-700">&#8212;</span>
                <span className="leading-relaxed">
                  <strong>Neon</strong> — managed PostgreSQL database. Relational data (account
                  records, activity history) is stored on Neon servers in the US.
                </span>
              </li>
              <li className="flex gap-3">
                <span className="mt-1 shrink-0 text-amber-700">&#8212;</span>
                <span className="leading-relaxed">
                  <strong>Transactional email provider</strong> — used only to send
                  account-related messages (invite links, access notifications). No marketing
                  email is sent.
                </span>
              </li>
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-semibold">4. Cookies and local storage</h2>
            <p className="text-stone-600 leading-relaxed">
              WeftMark uses a single session cookie set by Clerk to keep you signed in. No
              analytics, advertising, or third-party tracking cookies are set. No cookie consent
              banner is required because the session cookie is strictly necessary to provide the
              service you have requested.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-semibold">5. Data retention</h2>
            <ul className="space-y-2 text-stone-600">
              <li className="flex gap-3">
                <span className="mt-1 shrink-0 text-amber-700">&#8212;</span>
                <span className="leading-relaxed">
                  Account and content data is retained for as long as your account exists. You can
                  request deletion at any time from Settings. All associated data (WIF files,
                  photos, activity records, looms, yarn, projects) will be permanently purged
                  within 72 hours on a best-effort basis.
                </span>
              </li>
              <li className="flex gap-3">
                <span className="mt-1 shrink-0 text-amber-700">&#8212;</span>
                <span className="leading-relaxed">
                  Audit log entries are retained for 24 months for security and compliance purposes,
                  then deleted.
                </span>
              </li>
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-semibold">6. Your rights</h2>
            <p className="text-stone-600 leading-relaxed">
              Under the GDPR (and equivalent laws) you have the right to:
            </p>
            <ul className="space-y-2 text-stone-600">
              {[
                "Access — request a copy of the personal data we hold about you.",
                "Rectification — ask us to correct inaccurate data.",
                "Erasure — request deletion of your data via Settings → Delete account; data is purged within 72 hours.",
                "Portability — request your data in a structured, machine-readable format.",
                "Objection — object to processing based on legitimate interests.",
                "Restriction — request that we limit processing while a dispute is resolved.",
                "Withdraw consent — withdraw AI training consent at any time from Settings.",
                "Lodge a complaint — with your national data protection authority.",
              ].map((right) => (
                <li key={right} className="flex gap-3">
                  <span className="mt-1 shrink-0 text-amber-700">&#8212;</span>
                  <span className="leading-relaxed">{right}</span>
                </li>
              ))}
            </ul>
            <p className="text-stone-600 leading-relaxed">
              To exercise any right other than erasure and consent withdrawal (which are self-serve
              in Settings), email{" "}
              <a
                href="mailto:admin@weftmark.com"
                className="text-amber-800 underline hover:text-amber-900 transition-colors"
              >
                admin@weftmark.com
              </a>
              . We will respond within 30 days.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-semibold">7. Changes to this policy</h2>
            <p className="text-stone-600 leading-relaxed">
              If we make material changes, we will update the effective date above. Users will be
              presented with the updated Terms of Service at their next sign-in and must acknowledge
              them before continuing to use WeftMark. The Privacy Policy is incorporated by
              reference into the Terms of Service, so acceptance covers both documents.
            </p>
          </section>
        </div>
      </main>

      <PublicFooter />
    </div>
  );
}
