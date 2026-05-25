import { useState, useRef, useEffect } from "react";
import { HexColorPicker } from "react-colorful";
import { useTranslation } from "react-i18next";

// ---------------------------------------------------------------------------
// Conversion utilities
// ---------------------------------------------------------------------------

function hexToRgb(hex: string): [number, number, number] | null {
  const m = hex.match(/^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
  if (!m) return null;
  return [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)];
}

function rgbToHex(r: number, g: number, b: number): string {
  return `#${[r, g, b]
    .map((v) => Math.max(0, Math.min(255, v)).toString(16).padStart(2, "0"))
    .join("")}`;
}

function hexToHsl(hex: string): [number, number, number] | null {
  const rgb = hexToRgb(hex);
  if (!rgb) return null;
  const [r, g, b] = rgb.map((v) => v / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, Math.round(l * 100)];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = 0;
  if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
  else if (max === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;
  return [Math.round(h * 60), Math.round(s * 100), Math.round(l * 100)];
}

function hslToHex(h: number, s: number, l: number): string {
  const sl = s / 100;
  const ll = l / 100;
  const c = (1 - Math.abs(2 * ll - 1)) * sl;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = ll - c / 2;
  let rv = 0, gv = 0, bv = 0;
  if (h < 60) { rv = c; gv = x; bv = 0; }
  else if (h < 120) { rv = x; gv = c; bv = 0; }
  else if (h < 180) { rv = 0; gv = c; bv = x; }
  else if (h < 240) { rv = 0; gv = x; bv = c; }
  else if (h < 300) { rv = x; gv = 0; bv = c; }
  else { rv = c; gv = 0; bv = x; }
  return rgbToHex(Math.round((rv + m) * 255), Math.round((gv + m) * 255), Math.round((bv + m) * 255));
}

// Yarn-relevant color names that are absent from the CSS named-color set
const YARN_COLOR_NAMES: Record<string, string> = {
  ecru: "#c2b280",
  taupe: "#483c32",
  mauve: "#e0b0ff",
  sage: "#b2ac88",
  terracotta: "#e2725b",
  burgundy: "#800020",
  ochre: "#cc7722",
  umber: "#635147",
  celadon: "#ace1af",
  woad: "#4a7fc1",
  madder: "#e32636",
};

// All 148 CSS named colors — used to populate the datalist for autocomplete
const CSS_COLOR_NAMES = [
  "aliceblue","antiquewhite","aqua","aquamarine","azure","beige","bisque","black",
  "blanchedalmond","blue","blueviolet","brown","burlywood","cadetblue","chartreuse",
  "chocolate","coral","cornflowerblue","cornsilk","crimson","cyan","darkblue",
  "darkcyan","darkgoldenrod","darkgray","darkgreen","darkgrey","darkkhaki",
  "darkmagenta","darkolivegreen","darkorange","darkorchid","darkred","darksalmon",
  "darkseagreen","darkslateblue","darkslategray","darkslategrey","darkturquoise",
  "darkviolet","deeppink","deepskyblue","dimgray","dimgrey","dodgerblue","firebrick",
  "floralwhite","forestgreen","fuchsia","gainsboro","ghostwhite","gold","goldenrod",
  "gray","green","greenyellow","grey","honeydew","hotpink","indianred","indigo",
  "ivory","khaki","lavender","lavenderblush","lawngreen","lemonchiffon","lightblue",
  "lightcoral","lightcyan","lightgoldenrodyellow","lightgray","lightgreen","lightgrey",
  "lightpink","lightsalmon","lightseagreen","lightskyblue","lightslategray",
  "lightslategrey","lightsteelblue","lightyellow","lime","limegreen","linen",
  "magenta","maroon","mediumaquamarine","mediumblue","mediumorchid","mediumpurple",
  "mediumseagreen","mediumslateblue","mediumspringgreen","mediumturquoise",
  "mediumvioletred","midnightblue","mintcream","mistyrose","moccasin","navajowhite",
  "navy","oldlace","olive","olivedrab","orange","orangered","orchid","palegoldenrod",
  "palegreen","paleturquoise","palevioletred","papayawhip","peachpuff","peru","pink",
  "plum","powderblue","purple","rebeccapurple","red","rosybrown","royalblue",
  "saddlebrown","salmon","sandybrown","seagreen","seashell","sienna","silver",
  "skyblue","slateblue","slategray","slategrey","snow","springgreen","steelblue",
  "tan","teal","thistle","tomato","turquoise","violet","wheat","white","whitesmoke",
  "yellow","yellowgreen",
];

// Combined list for autocomplete datalist (yarn extensions first so they surface above CSS duplicates)
const ALL_COLOR_NAME_OPTIONS = [
  ...Object.keys(YARN_COLOR_NAMES),
  ...CSS_COLOR_NAMES.filter((n) => !(n in YARN_COLOR_NAMES)),
];

function resolveColorName(name: string): string | null {
  const s = name.trim().toLowerCase();
  if (!s) return null;
  if (YARN_COLOR_NAMES[s]) return YARN_COLOR_NAMES[s];
  // Resolve CSS named colors via canvas — no dependency, 147 built-in names
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 1;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  const sentinel = "#fe2347";
  ctx.fillStyle = sentinel;
  ctx.fillStyle = s;
  if (ctx.fillStyle === sentinel) return null;
  const hex = ctx.fillStyle;
  return /^#[0-9a-f]{6}$/i.test(hex) ? hex.toLowerCase() : null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

type Mode = "hex" | "rgb" | "hsl" | "name";

const PICKER_HEIGHT = 360;

interface ColorPickerProps {
  value: string;
  onChange: (hex: string) => void;
  size?: "sm" | "md";
  className?: string;
}

export function ColorPicker({ value, onChange, size = "md", className }: ColorPickerProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [openUp, setOpenUp] = useState(false);
  const [mode, setMode] = useState<Mode>("hex");
  const [hexInput, setHexInput] = useState(value);
  const [rgbInput, setRgbInput] = useState<[string, string, string]>(() => {
    const rgb = hexToRgb(value);
    return rgb ? (rgb.map(String) as [string, string, string]) : ["0", "0", "0"];
  });
  const [hslInput, setHslInput] = useState<[string, string, string]>(() => {
    const hsl = hexToHsl(value);
    return hsl ? (hsl.map(String) as [string, string, string]) : ["0", "0", "0"];
  });
  const [nameInput, setNameInput] = useState("");
  const [nameError, setNameError] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  function syncAllInputs(hex: string) {
    setHexInput(hex);
    const rgb = hexToRgb(hex);
    if (rgb) setRgbInput(rgb.map(String) as [string, string, string]);
    const hsl = hexToHsl(hex);
    if (hsl) setHslInput(hsl.map(String) as [string, string, string]);
  }

  // Sync all inputs when value changes externally (e.g., wheel drag or parent update)
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    syncAllInputs(value);
  }, [value]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: PointerEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  function handleToggle() {
    if (!open && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setOpenUp(window.innerHeight - rect.bottom < PICKER_HEIGHT);
    }
    setOpen((v) => !v);
  }

  function handleWheelChange(hex: string) {
    syncAllInputs(hex);
    onChange(hex);
    setNameInput("");
    setNameError(false);
  }

  function handleHexInput(e: React.ChangeEvent<HTMLInputElement>) {
    let v = e.target.value;
    if (!v.startsWith("#")) v = `#${v}`;
    setHexInput(v);
    if (/^#[0-9a-fA-F]{6}$/.test(v)) {
      const rgb = hexToRgb(v);
      if (rgb) setRgbInput(rgb.map(String) as [string, string, string]);
      const hsl = hexToHsl(v);
      if (hsl) setHslInput(hsl.map(String) as [string, string, string]);
      onChange(v);
    }
  }

  function handleRgbChange(index: 0 | 1 | 2, raw: string) {
    const next = [...rgbInput] as [string, string, string];
    next[index] = raw;
    setRgbInput(next);
    const nums = next.map(Number);
    if (next.every((v) => v !== "" && !isNaN(Number(v))) && nums.every((v) => v >= 0 && v <= 255)) {
      const hex = rgbToHex(nums[0], nums[1], nums[2]);
      setHexInput(hex);
      const hsl = hexToHsl(hex);
      if (hsl) setHslInput(hsl.map(String) as [string, string, string]);
      onChange(hex);
    }
  }

  function handleHslChange(index: 0 | 1 | 2, raw: string) {
    const next = [...hslInput] as [string, string, string];
    next[index] = raw;
    setHslInput(next);
    const [h, s, l] = next.map(Number);
    if (
      next.every((v) => v !== "" && !isNaN(Number(v))) &&
      h >= 0 && h <= 360 &&
      s >= 0 && s <= 100 &&
      l >= 0 && l <= 100
    ) {
      const hex = hslToHex(h, s, l);
      setHexInput(hex);
      const rgb = hexToRgb(hex);
      if (rgb) setRgbInput(rgb.map(String) as [string, string, string]);
      onChange(hex);
    }
  }

  function handleNameChange(e: React.ChangeEvent<HTMLInputElement>) {
    const v = e.target.value;
    setNameInput(v);
    setNameError(false);
    // Auto-resolve on exact match or datalist selection — sync all modes immediately
    const hex = resolveColorName(v);
    if (hex) {
      syncAllInputs(hex);
      onChange(hex);
    }
  }

  function handleNameCommit() {
    if (!nameInput.trim()) return;
    const hex = resolveColorName(nameInput);
    if (hex) {
      syncAllInputs(hex);
      onChange(hex);
      setNameError(false);
    } else {
      setNameError(true);
    }
  }

  const swatchClass =
    size === "sm"
      ? "h-6 w-10 rounded border border-input cursor-pointer p-0.5"
      : "h-8 w-12 rounded border border-input cursor-pointer";

  const popoverPosition = openUp ? "bottom-full mb-1" : "top-full mt-1";

  const modes: { key: Mode; label: string }[] = [
    { key: "hex", label: t("colorPicker.modeHex") },
    { key: "rgb", label: t("colorPicker.modeRgb") },
    { key: "hsl", label: t("colorPicker.modeHsl") },
    { key: "name", label: t("colorPicker.modeName") },
  ];

  const inputBase =
    "rounded border border-input bg-background px-2 py-1 text-xs font-mono text-card-foreground w-full";

  const rgbFields = [
    { label: "R", index: 0 as const, max: 255 },
    { label: "G", index: 1 as const, max: 255 },
    { label: "B", index: 2 as const, max: 255 },
  ];

  const hslFields = [
    { label: "H", index: 0 as const, max: 360 },
    { label: "S", index: 1 as const, max: 100 },
    { label: "L", index: 2 as const, max: 100 },
  ];

  return (
    <div ref={ref} className={`relative inline-block ${className ?? ""}`}>
      <button
        ref={buttonRef}
        type="button"
        className={swatchClass}
        style={{ backgroundColor: value }}
        onClick={handleToggle}
        aria-label={t("colorPicker.ariaLabel")}
      />
      {open && (
        <div
          className={`absolute left-0 z-50 ${popoverPosition} rounded-lg border border-border bg-card p-3 shadow-lg space-y-2`}
        >
          <HexColorPicker color={value} onChange={handleWheelChange} />

          {/* Mode tab strip */}
          <div className="flex gap-0.5">
            {modes.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                onClick={() => setMode(key)}
                className={`flex-1 rounded px-1 py-0.5 text-xs font-medium transition-colors ${
                  mode === key
                    ? "bg-muted text-card-foreground"
                    : "text-muted-foreground hover:text-card-foreground"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Hex input */}
          {mode === "hex" && (
            <input
              className={inputBase}
              value={hexInput}
              onChange={handleHexInput}
              maxLength={7}
              placeholder="#000000"
              spellCheck={false}
            />
          )}

          {/* RGB inputs */}
          {mode === "rgb" && (
            <div className="flex gap-1">
              {rgbFields.map(({ label, index, max }) => (
                <div key={label} className="flex flex-col items-center gap-0.5 flex-1">
                  <span className="text-xs text-muted-foreground">{label}</span>
                  <input
                    className={inputBase}
                    type="number"
                    min={0}
                    max={max}
                    value={rgbInput[index]}
                    onChange={(e) => handleRgbChange(index, e.target.value)}
                    placeholder="0"
                  />
                </div>
              ))}
            </div>
          )}

          {/* HSL inputs */}
          {mode === "hsl" && (
            <div className="flex gap-1">
              {hslFields.map(({ label, index, max }) => (
                <div key={label} className="flex flex-col items-center gap-0.5 flex-1">
                  <span className="text-xs text-muted-foreground">{label}</span>
                  <input
                    className={inputBase}
                    type="number"
                    min={0}
                    max={max}
                    value={hslInput[index]}
                    onChange={(e) => handleHslChange(index, e.target.value)}
                    placeholder="0"
                  />
                </div>
              ))}
            </div>
          )}

          {/* Color name input with custom autocomplete */}
          {mode === "name" && (() => {
            const q = nameInput.trim().toLowerCase();
            const suggestions = q
              ? [
                  ...ALL_COLOR_NAME_OPTIONS.filter((n) => n.startsWith(q)),
                  ...ALL_COLOR_NAME_OPTIONS.filter((n) => !n.startsWith(q) && n.includes(q)),
                ].slice(0, 8)
              : [];
            return (
              <div className="relative space-y-1">
                <input
                  className={inputBase}
                  value={nameInput}
                  onChange={handleNameChange}
                  onBlur={handleNameCommit}
                  onKeyDown={(e) => e.key === "Enter" && handleNameCommit()}
                  placeholder={t("colorPicker.namePlaceholder")}
                  spellCheck={false}
                />
                {suggestions.length > 0 && (
                  <ul className="absolute left-0 right-0 top-full mt-0.5 z-10 rounded border border-border bg-card shadow-md overflow-y-auto max-h-36">
                    {suggestions.map((name) => (
                      <li
                        key={name}
                        className="flex items-center gap-2 px-2 py-1 text-xs text-card-foreground cursor-pointer hover:bg-muted"
                        onMouseDown={(e) => {
                          e.preventDefault();
                          setNameInput(name);
                          setNameError(false);
                          const hex = resolveColorName(name);
                          if (hex) { syncAllInputs(hex); onChange(hex); }
                        }}
                      >
                        <span
                          className="inline-block h-3 w-3 rounded-sm border border-border flex-shrink-0"
                          style={{ backgroundColor: resolveColorName(name) ?? undefined }}
                        />
                        {name}
                      </li>
                    ))}
                  </ul>
                )}
                {nameError && (
                  <p className="text-xs text-destructive">{t("colorPicker.nameUnknown")}</p>
                )}
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}
