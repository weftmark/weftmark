import { useState, useEffect } from "react";
import { useLocation } from "react-router-dom";

const IS_DEV = import.meta.env.VITE_APP_ENV === "dev";
const DETAIL_PATTERN = /^\/projects\/[^/]+/;

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
      className="w-full bg-amber-400 text-amber-950 text-center text-xs font-semibold py-1.5 px-4 select-none overflow-hidden"
      style={{
        maxHeight: visible ? "3rem" : "0",
        opacity: visible ? 1 : 0,
        transition: "max-height 0.5s ease, opacity 0.5s ease",
      }}
    >
      ⚠️ Development environment — data may be reset at any time
    </div>
  );
}
