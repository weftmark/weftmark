const IS_DEV = import.meta.env.VITE_APP_ENV === "dev";

export function DevBanner() {
  if (!IS_DEV) return null;
  return (
    <div className="w-full bg-amber-400 text-amber-950 text-center text-xs font-semibold py-1.5 px-4 select-none">
      ⚠️ Development environment — data may be reset at any time
    </div>
  );
}
