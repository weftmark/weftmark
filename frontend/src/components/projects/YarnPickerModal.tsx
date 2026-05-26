import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { listYarn, yarnPhotoUrl, type YarnSummary } from "@/api/yarn";
import { AppIcons } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { AuthedImage } from "@/components/ui/AuthedImage";

interface Props {
  colorHex: string;
  currentYarnId: string | null;
  onSelect: (yarnId: string, yarn: YarnSummary) => void;
  onUnlink: () => void;
  onClose: () => void;
  isSaving: boolean;
}

export function YarnPickerModal({ colorHex, currentYarnId, onSelect, onUnlink, onClose, isSaving }: Props) {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");

  const { data: yarns = [], isLoading } = useQuery({
    queryKey: ["yarn"],
    queryFn: () => listYarn(false),
  });

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const q = search.trim().toLowerCase();
  const filtered: YarnSummary[] = q
    ? yarns.filter(
        (y) =>
          y.brand.toLowerCase().includes(q) ||
          y.name.toLowerCase().includes(q) ||
          (y.color_name ?? "").toLowerCase().includes(q) ||
          (y.color_hex ?? "").toLowerCase().includes(q),
      )
    : yarns;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-lg border border-border bg-card shadow-lg flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-border">
          <div className="flex items-center gap-2">
            <span
              className="inline-block h-5 w-5 rounded border border-border flex-shrink-0"
              style={{ background: colorHex }}
            />
            <h2 className="text-base font-semibold">{t("yarnPicker.title")}</h2>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <AppIcons.close className="h-4 w-4" />
          </button>
        </div>

        {/* Search */}
        <div className="px-4 pt-3 pb-2">
          <input
            type="search"
            className="w-full rounded border border-input bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            placeholder={t("yarnPicker.searchPlaceholder")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            autoFocus
          />
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-0.5">
          {isLoading && (
            <p className="text-sm text-muted-foreground text-center py-6">{t("yarnPicker.loading")}</p>
          )}
          {!isLoading && filtered.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-6">{t("yarnPicker.noResults")}</p>
          )}
          {filtered.map((yarn) => {
            const isCurrent = yarn.id === currentYarnId;
            return (
              <button
                key={yarn.id}
                className={`w-full flex items-center gap-3 rounded-md px-3 py-2 text-sm text-left transition-colors ${
                  isCurrent
                    ? "bg-copper-subtle text-copper-on-subtle"
                    : "hover:bg-muted"
                }`}
                onClick={() => onSelect(yarn.id, yarn)}
                disabled={isSaving}
              >
                {/* Yarn photo / color swatch */}
                <div className="h-8 w-8 rounded border border-border flex-shrink-0 overflow-hidden">
                  {yarn.has_photo ? (
                    <AuthedImage
                      src={yarnPhotoUrl(yarn.id)}
                      alt=""
                      className="h-full w-full object-cover"
                    />
                  ) : yarn.ravelry_colorway_thumbnail_url ? (
                    <img
                      src={yarn.ravelry_colorway_thumbnail_url}
                      alt=""
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <span
                      className="block h-full w-full"
                      style={{ background: yarn.color_hex ?? "#e5e7eb" }}
                    />
                  )}
                </div>

                {/* Name + color */}
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">
                    {yarn.brand} — {yarn.name}
                  </p>
                  {yarn.color_name && (
                    <p className="text-xs text-muted-foreground truncate">{yarn.color_name}</p>
                  )}
                </div>

                {/* Current badge */}
                {isCurrent && (
                  <AppIcons.check className="h-4 w-4 flex-shrink-0 text-accent" />
                )}
              </button>
            );
          })}
        </div>

        {/* Footer */}
        {currentYarnId && (
          <div className="px-4 py-3 border-t border-border">
            <Button
              variant="outline"
              size="sm"
              className="w-full text-muted-foreground"
              onClick={onUnlink}
              disabled={isSaving}
            >
              {t("yarnPicker.unlink")}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
