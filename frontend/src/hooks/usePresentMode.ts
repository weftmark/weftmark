import { useState, useEffect, useCallback, useRef } from "react";

interface PresentModeResult {
  isPresent: boolean;
  isSupported: boolean;
  toggle: () => Promise<void>;
}

export function usePresentMode(): PresentModeResult {
  const [isPresent, setIsPresent] = useState(false);
  const wakeLockRef = useRef<WakeLockSentinel | null>(null);

  // Show button if either API is available — each is attempted independently
  const isSupported =
    "requestFullscreen" in document.documentElement ||
    "wakeLock" in navigator;

  const enter = useCallback(async () => {
    try {
      await document.documentElement.requestFullscreen();
    } catch { /* ignore — user may have denied or browser doesn't support */ }
    try {
      wakeLockRef.current = await navigator.wakeLock.request("screen");
    } catch { /* non-critical — screen may still go dark */ }
    setIsPresent(true);
  }, []);

  const exit = useCallback(async () => {
    if (document.fullscreenElement) {
      try { await document.exitFullscreen(); } catch { /* ignore */ }
    }
    if (wakeLockRef.current) {
      try { await wakeLockRef.current.release(); } catch { /* ignore */ }
      wakeLockRef.current = null;
    }
    setIsPresent(false);
  }, []);

  const toggle = useCallback(
    () => (isPresent ? exit() : enter()),
    [isPresent, enter, exit],
  );

  // Sync state when user presses Esc to exit fullscreen natively
  useEffect(() => {
    const onFullscreenChange = () => {
      if (!document.fullscreenElement && isPresent) {
        if (wakeLockRef.current) {
          wakeLockRef.current.release().catch(() => {});
          wakeLockRef.current = null;
        }
        setIsPresent(false);
      }
    };
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, [isPresent]);

  // Release everything on unmount
  useEffect(() => {
    return () => {
      if (document.fullscreenElement) {
        document.exitFullscreen().catch(() => {});
      }
      if (wakeLockRef.current) {
        wakeLockRef.current.release().catch(() => {});
        wakeLockRef.current = null;
      }
    };
  }, []);

  return { isPresent, isSupported, toggle };
}
