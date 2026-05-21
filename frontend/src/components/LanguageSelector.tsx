import { useRef, useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { SUPPORTED_LANGUAGES } from "@/i18n/config";

interface Props {
  variant?: "public" | "app";
}

export function LanguageSelector({ variant = "app" }: Props) {
  const { i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const current = SUPPORTED_LANGUAGES.find((l) => l.code === i18n.language) ?? SUPPORTED_LANGUAGES[0];

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function select(code: string) {
    i18n.changeLanguage(code);
    localStorage.setItem("wm_lang", code);
    setOpen(false);
  }

  const triggerClass =
    variant === "public"
      ? "flex cursor-pointer items-center gap-1.5 text-sm font-medium text-stone-600 transition-colors hover:text-stone-900 select-none"
      : "flex cursor-pointer items-center gap-1.5 rounded-md border border-border bg-background px-3 py-2 text-sm select-none hover:bg-accent";

  const dropdownClass =
    variant === "public"
      ? "absolute right-0 top-full z-50 mt-1.5 min-w-[9rem] overflow-hidden rounded-lg border border-stone-200 bg-white py-1 shadow-lg"
      : "absolute right-0 top-full z-50 mt-1.5 min-w-[9rem] overflow-hidden rounded-lg border border-border bg-popover py-1 shadow-lg";

  const optionBase = "flex w-full cursor-pointer items-center gap-2.5 px-3 py-2 text-sm transition-colors";
  const optionIdle =
    variant === "public"
      ? "text-stone-700 hover:bg-stone-100"
      : "text-popover-foreground hover:bg-accent";
  const optionActive =
    variant === "public"
      ? "bg-stone-100 font-medium text-stone-900"
      : "bg-accent font-medium";

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={triggerClass}
      >
        <span role="img" aria-label={current.label} className="text-base leading-none">
          {current.flag}
        </span>
        <span>{current.label}</span>
        <svg
          className={`h-3.5 w-3.5 opacity-50 transition-transform ${open ? "rotate-180" : ""}`}
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {open && (
        <ul role="listbox" className={dropdownClass}>
          {SUPPORTED_LANGUAGES.map((lang) => (
            <li key={lang.code} role="option" aria-selected={lang.code === current.code}>
              <button
                type="button"
                onClick={() => select(lang.code)}
                className={`${optionBase} ${lang.code === current.code ? optionActive : optionIdle}`}
              >
                <span role="img" aria-label={lang.label} className="text-base leading-none">
                  {lang.flag}
                </span>
                {lang.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
