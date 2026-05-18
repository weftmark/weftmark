import { Link } from "react-router-dom";

export function PublicFooter() {
  return (
    <footer className="border-t border-border bg-muted py-4 px-6">
      <div className="mx-auto flex max-w-4xl flex-col items-center gap-2 sm:flex-row sm:justify-between">
        <nav className="flex flex-wrap gap-4 text-sm text-subdued">
          <Link to="/about" className="hover:text-foreground transition-colors">About</Link>
          <Link to="/privacy" className="hover:text-foreground transition-colors">Privacy</Link>
          <Link to="/terms" className="hover:text-foreground transition-colors">Terms</Link>
          <Link to="/costs" className="hover:text-foreground transition-colors">Running costs</Link>
          <span className="text-muted-foreground">Contact</span>
        </nav>
        <Link to="/costs" className="text-xs text-muted-foreground hover:text-foreground transition-colors">
          ♥ Support WeftMark
        </Link>
      </div>
    </footer>
  );
}
