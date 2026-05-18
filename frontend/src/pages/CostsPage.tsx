import { Link } from "react-router-dom";
import { WeftmarkLogo } from "@/components/WeftmarkLogo";
import { PublicFooter } from "@/components/PublicFooter";
import { AppIcons } from "@/lib/icons";

interface CostRow {
  service: string;
  description: string;
  tier: string;
  monthlyCost: string;
  status: "free" | "paid" | "donation" | "goal";
  nextTier?: string;
  note?: string;
}

const COSTS: CostRow[] = [
  {
    service: "Hosting / Infrastructure",
    description: "Servers, networking, and operating environment for all services.",
    tier: "Equipment owner donation",
    monthlyCost: "$0",
    status: "donation",
    note: "Goal: donate $100/yr to the hosting owner as a thank-you.",
  },
  {
    service: "Domain registration",
    description: "weftmark.com domain name — annual renewal.",
    tier: "Annual renewal",
    monthlyCost: "~$1",
    status: "paid",
    note: "Billed ~$12/yr.",
  },
  {
    service: "Claude Max ×5",
    description: "AI-assisted development — makes it possible for one person to manage system complexity and ship features alongside a full-time job and family.",
    tier: "Max ×5 subscription",
    monthlyCost: "~$100",
    status: "paid",
  },
  {
    service: "Claude API",
    description: "AI agents used for market research and automated analysis tasks.",
    tier: "Pay-as-you-go",
    monthlyCost: "~$20",
    status: "paid",
  },
  {
    service: "Neon (PostgreSQL)",
    description: "Managed PostgreSQL database — stores all your drafts, projects, and settings.",
    tier: "Free (100 CU-hr/mo, 0.5 GB)",
    monthlyCost: "$0",
    status: "free",
    nextTier: "Launch plan: ~$19/mo",
  },
  {
    service: "SMTP2Go (Email)",
    description: "Transactional email delivery — account notifications and admin alerts.",
    tier: "Free (1,000 emails/mo)",
    monthlyCost: "$0",
    status: "free",
    nextTier: "Starter: $10/mo (10k emails/mo)",
  },
  {
    service: "Cloudflare R2 (Storage)",
    description: "Object storage for drawdown images, WIF files, and project photos.",
    tier: "Free (10 GB, 1M writes, 10M reads/mo)",
    monthlyCost: "$0",
    status: "free",
    nextTier: "$0.015/GB + $4.50/M write ops above free tier",
  },
  {
    service: "Clerk (Authentication)",
    description: "Secure sign-in, account management, and session handling.",
    tier: "Free (50,000 MAU)",
    monthlyCost: "$0",
    status: "free",
    nextTier: "Pro: $20/mo + $0.02/MAU over limit",
  },
];

const STATUS_BADGE: Record<CostRow["status"], string> = {
  free: "bg-green-100 text-green-800",
  paid: "bg-amber-100 text-amber-800",
  donation: "bg-blue-100 text-blue-800",
  goal: "bg-purple-100 text-purple-800",
};

const STATUS_LABEL: Record<CostRow["status"], string> = {
  free: "Free tier",
  paid: "Paid",
  donation: "Donated",
  goal: "Goal",
};

// Replace with the actual GitHub Sponsors URL once approved.
const GITHUB_SPONSORS_URL: string | null = null;

export function CostsPage() {
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
        <div className="mx-auto max-w-3xl space-y-12">

          {/* Intro */}
          <div className="space-y-4">
            <h1 className="text-3xl font-bold tracking-tight">Running costs</h1>
            <p className="text-stone-600 leading-relaxed">
              weftmark is a personal project, not a commercial product. In the spirit of transparency,
              here's exactly what it costs to keep the lights on — and why.
            </p>
            <p className="text-stone-600 leading-relaxed">
              Almost all infrastructure runs on free tiers. The meaningful recurring cost is the Claude
              subscription used to build and maintain the platform. weftmark is built and maintained
              by one person, around a full-time job and family — AI assistance is what makes it
              possible to manage the complexity of the system, keep up with bugs, and ship new
              features without it becoming a second job in itself.
            </p>
            <div className="inline-flex items-center gap-2 rounded-full bg-amber-100 px-4 py-1.5 text-sm font-medium text-amber-900">
              Approximate monthly cost: ~$121 / month
            </div>
          </div>

          {/* Cost table */}
          <div className="space-y-3">
            <h2 className="text-lg font-semibold">Service breakdown</h2>
            <div className="overflow-x-auto rounded-xl border border-stone-200">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-stone-200 bg-stone-100 text-left text-xs uppercase tracking-wide text-stone-500">
                    <th className="px-4 py-3">Service</th>
                    <th className="px-4 py-3 hidden sm:table-cell">What it does</th>
                    <th className="px-4 py-3">Tier</th>
                    <th className="px-4 py-3 text-right">Cost / mo</th>
                  </tr>
                </thead>
                <tbody>
                  {COSTS.map((row) => (
                    <tr key={row.service} className="border-b border-stone-200 last:border-0">
                      <td className="px-4 py-3 font-medium align-top">
                        <div>{row.service}</div>
                        <div className="mt-1 sm:hidden text-xs text-stone-500 font-normal">{row.description}</div>
                        {row.note && <div className="mt-1 sm:hidden text-xs text-stone-400 italic">{row.note}</div>}
                        <span className={`mt-1.5 inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[row.status]}`}>
                          {STATUS_LABEL[row.status]}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-stone-600 hidden sm:table-cell align-top">
                        <div>{row.description}</div>
                        {row.note && <div className="mt-1 text-xs text-stone-400 italic">{row.note}</div>}
                      </td>
                      <td className="px-4 py-3 text-stone-600 align-top">
                        <div>{row.tier}</div>
                        {row.nextTier && (
                          <div className="mt-1 text-xs text-stone-400">
                            Next: {row.nextTier}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right font-mono font-semibold align-top">{row.monthlyCost}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t-2 border-stone-300 bg-stone-50">
                    <td colSpan={3} className="px-4 py-3 text-sm font-medium text-right hidden sm:table-cell">Total (approximate)</td>
                    <td colSpan={2} className="px-4 py-3 text-sm font-medium sm:hidden">Total</td>
                    <td className="px-4 py-3 text-right font-mono font-bold">~$121 / mo</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>

          {/* Support CTA */}
          <div className="rounded-xl border border-stone-200 bg-white p-6 space-y-4">
            <div className="flex items-center gap-2">
              <AppIcons.support className="h-5 w-5 text-amber-600" />
              <h2 className="text-lg font-semibold">Support this project</h2>
            </div>
            <p className="text-stone-600 leading-relaxed">
              weftmark is free to use and always will be. If it saves you time, prevents treadling
              errors, or just makes weaving a little more enjoyable — and you'd like to help keep it
              running — a small contribution goes a long way toward the monthly Claude bill.
            </p>
            {GITHUB_SPONSORS_URL ? (
              <a
                href={GITHUB_SPONSORS_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-lg bg-amber-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-amber-700 transition-colors"
              >
                <AppIcons.support className="h-4 w-4" />
                Sponsor on GitHub
              </a>
            ) : (
              <div className="rounded-lg border border-dashed border-stone-300 bg-stone-50 px-4 py-3 text-sm text-stone-500">
                GitHub Sponsors profile pending approval — check back soon.
              </div>
            )}
          </div>

          {/* Free tiers note */}
          <div className="space-y-2">
            <h2 className="text-lg font-semibold">What happens if limits are hit?</h2>
            <p className="text-stone-600 leading-relaxed">
              All infrastructure services are well within their free tiers today. If weftmark grows
              to the point where paid tiers are needed, costs will be re-evaluated and this page will
              be updated. No features will be paywalled — the platform stays free to use.
            </p>
          </div>

        </div>
      </main>

      <PublicFooter />
    </div>
  );
}
