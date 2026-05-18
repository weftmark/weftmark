import { useOnlineStatus } from "@/hooks/useOnlineStatus";

export function OfflineBanner() {
  const isOnline = useOnlineStatus();
  if (isOnline) return null;
  return (
    <div className="shrink-0 bg-amber-500/10 border-b border-amber-500/30 px-4 py-2 text-center text-xs text-amber-700 dark:text-amber-400">
      You&rsquo;re offline &mdash; weaving steps will sync when you reconnect
    </div>
  );
}
