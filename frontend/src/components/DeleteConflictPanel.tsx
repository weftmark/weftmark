import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import type { DeleteConflict } from "@/api/drafts";

interface DeleteConflictPanelProps {
  readonly conflict: DeleteConflict;
  readonly usedByMessage: string;
  readonly conflictNote: string;
  readonly confirmForceDelete: boolean;
  readonly onRequestForceDelete: () => void;
  readonly forceDeleteLabel: string;
  readonly triggerButtonClassName?: string;
  readonly onConfirmForceDelete: () => void;
  readonly confirmForceDeleteLabel: string;
  readonly busy: boolean;
  readonly busyLabel?: string;
  readonly onCancel: () => void;
}

export function DeleteConflictPanel({
  conflict,
  usedByMessage,
  conflictNote,
  confirmForceDelete,
  onRequestForceDelete,
  forceDeleteLabel,
  triggerButtonClassName,
  onConfirmForceDelete,
  confirmForceDeleteLabel,
  busy,
  busyLabel,
  onCancel,
}: DeleteConflictPanelProps) {
  const { t } = useTranslation();

  return (
    <div className="space-y-2">
      <p className="text-sm text-destructive font-medium">{usedByMessage}</p>
      <ul className="text-xs text-muted-foreground space-y-0.5 pl-3">
        {conflict.projects.map((p) => <li key={p.id}>· {p.name}</li>)}
      </ul>
      <p className="text-xs text-muted-foreground">{conflictNote}</p>
      {!confirmForceDelete ? (
        <Button variant="outline" size="sm" className={triggerButtonClassName} onClick={onRequestForceDelete}>
          {forceDeleteLabel}
        </Button>
      ) : (
        <div className="flex gap-2">
          <Button variant="destructive" size="sm" onClick={onConfirmForceDelete} disabled={busy}>
            {busy && busyLabel ? busyLabel : confirmForceDeleteLabel}
          </Button>
          <Button variant="outline" size="sm" onClick={onCancel}>{t("common.cancel")}</Button>
        </div>
      )}
    </div>
  );
}
