import { useState, useEffect } from "react";
import { useLocation } from "react-router-dom";

const IS_DEV = import.meta.env.VITE_APP_ENV === "dev";
const DETAIL_PATTERN = /^\/projects\/[^/]+/;

const BANNER_PALETTE: Record<string, { background: string; color: string }> = {
  indigo: { background: "#c7d2fe", color: "#312e81" },
  blue: { background: "#bfdbfe", color: "#1e3a8a" },
  teal: { background: "#99f6e4", color: "#134e4a" },
  green: { background: "#bbf7d0", color: "#14532d" },
  purple: { background: "#e9d5ff", color: "#581c87" },
  pink: { background: "#fbcfe8", color: "#831843" },
  red: { background: "#fecaca", color: "#7f1d1d" },
};

const ENV_COLOR = (import.meta.env.VITE_DEV_BANNER_COLOR ?? "").toLowerCase();
const colorStyle = BANNER_PALETTE[ENV_COLOR] ?? null;

export function DevBanner() {
  const location = useLocation();
  const isDetailPage = DETAIL_PATTERN.test(location.pathname);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const showTimer = setTimeout(() => setVisible(true), 0);
    if (!isDetailPage) return () => clearTimeout(showTimer);
    const hideTimer = setTimeout(() => setVisible(false), 2000);
    return () => {
      clearTimeout(showTimer);
      clearTimeout(hideTimer);
    };
  }, [location.pathname, isDetailPage]);

  if (!IS_DEV) return null;
  return (
    <div
      className={`w-full text-center text-xs font-semibold py-1.5 px-4 select-none overflow-hidden${colorStyle ? "" : " bg-amber-400 text-amber-950"}`}
      style={{
        ...(colorStyle ?? {}),
        maxHeight: visible ? "3rem" : "0",
        opacity: visible ? 1 : 0,
        transition: "max-height 0.5s ease, opacity 0.5s ease",
      }}
    >
      ⚠️ Development environment — data may be reset at any time
    </div>
  );
}
