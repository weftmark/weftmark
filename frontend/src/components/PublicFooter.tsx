import { Link } from "react-router-dom";

export function PublicFooter() {
  return (
    <footer className="border-t border-stone-200 bg-stone-100 py-4 px-6">
      <div className="mx-auto flex max-w-4xl flex-col items-center gap-2 sm:flex-row sm:justify-between">
        <nav className="flex gap-4 text-sm text-stone-600">
          <Link to="/about" className="hover:text-stone-900 transition-colors">About</Link>
          <Link to="/privacy" className="hover:text-stone-900 transition-colors">Privacy</Link>
          <Link to="/terms" className="hover:text-stone-900 transition-colors">Terms</Link>
          <span className="text-stone-400">Contact</span>
        </nav>
        <p className="text-xs text-stone-500">Built by a weaver, with AI assistance.</p>
      </div>
    </footer>
  );
}
