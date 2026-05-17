interface Props {
  ownerEmail?: string;
}

export function SuperuserInspectionBanner({ ownerEmail }: Props) {
  return (
    <div className="bg-amber-50 border-b border-amber-200 px-4 py-2 text-sm text-amber-900 flex items-center gap-2">
      <span className="font-semibold">Superuser inspection — read-only</span>
      {ownerEmail && <span className="text-amber-700">· {ownerEmail}</span>}
    </div>
  );
}
