import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} {...props} />;
}

export function SkeletonCardGrid({
  count = 4,
  cardClassName = "h-32",
  gridClassName = "grid gap-4 sm:grid-cols-2",
}: Readonly<{
  count?: number;
  cardClassName?: string;
  gridClassName?: string;
}>) {
  return (
    <div className={gridClassName}>
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} className={cn("rounded-lg", cardClassName)} />
      ))}
    </div>
  );
}
