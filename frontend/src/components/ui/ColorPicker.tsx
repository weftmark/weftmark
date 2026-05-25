import { useState, useRef, useEffect } from "react";
import { HexColorPicker } from "react-colorful";

interface ColorPickerProps {
  value: string;
  onChange: (hex: string) => void;
  size?: "sm" | "md";
  className?: string;
}

const PICKER_HEIGHT = 280; // approx height of picker + hex input + padding

export function ColorPicker({ value, onChange, size = "md", className }: ColorPickerProps) {
  const [open, setOpen] = useState(false);
  const [openUp, setOpenUp] = useState(false);
  const [hexInput, setHexInput] = useState(value);
  const ref = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setHexInput(value);
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

  function handleHexInput(e: React.ChangeEvent<HTMLInputElement>) {
    let v = e.target.value;
    if (!v.startsWith("#")) v = `#${v}`;
    setHexInput(v);
    if (/^#[0-9a-fA-F]{6}$/.test(v)) onChange(v);
  }

  const swatchClass =
    size === "sm"
      ? "h-6 w-10 rounded border border-input cursor-pointer p-0.5"
      : "h-8 w-12 rounded border border-input cursor-pointer";

  const popoverPosition = openUp ? "bottom-full mb-1" : "top-full mt-1";

  return (
    <div ref={ref} className={`relative inline-block ${className ?? ""}`}>
      <button
        ref={buttonRef}
        type="button"
        className={swatchClass}
        style={{ backgroundColor: value }}
        onClick={handleToggle}
        aria-label="Pick color"
      />
      {open && (
        <div className={`absolute left-0 z-50 ${popoverPosition} rounded-lg border border-border bg-card p-3 shadow-lg space-y-2`}>
          <HexColorPicker color={value} onChange={onChange} />
          <input
            className="w-full rounded border border-input bg-background px-2 py-1 text-xs font-mono text-card-foreground"
            value={hexInput}
            onChange={handleHexInput}
            maxLength={7}
            placeholder="#000000"
            spellCheck={false}
          />
        </div>
      )}
    </div>
  );
}
