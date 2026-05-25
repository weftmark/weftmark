interface Props {
  bodyHtml: string;
}

export function EulaContent({ bodyHtml }: Props) {
  return (
    <div
      className="eula-content text-sm leading-relaxed space-y-2"
      dangerouslySetInnerHTML={{ __html: bodyHtml }} // nosemgrep: typescript.react.security.audit.react-dangerouslysetinnerhtml.react-dangerouslysetinnerhtml
    />
  );
}
