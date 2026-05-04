import { useState } from "react";
import { Copy, Check } from "lucide-react";

export function CopyEmail({ email }: { email: string }) {
  const [copied, setCopied] = useState(false);

  function handleCopy(e: React.MouseEvent) {
    e.stopPropagation();
    navigator.clipboard.writeText(email).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <span className="group/copy inline-flex items-center gap-1 max-w-full overflow-hidden">
      <span className="flex-1 min-w-0 truncate">{email}</span>
      <button
        type="button"
        onClick={handleCopy}
        title="Copy email"
        className="shrink-0 opacity-0 group-hover/copy:opacity-100 transition-opacity text-muted-foreground/60 hover:text-foreground"
      >
        {copied ? (
          <Check className="h-3 w-3 text-green-500" />
        ) : (
          <Copy className="h-3 w-3" />
        )}
      </button>
    </span>
  );
}
