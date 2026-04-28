interface Props {
  bodyHtml: string;
}

export function EulaContent({ bodyHtml }: Props) {
  return (
    <div
      className="text-sm leading-relaxed space-y-2"
      dangerouslySetInnerHTML={{ __html: bodyHtml }}
    />
  );
}
