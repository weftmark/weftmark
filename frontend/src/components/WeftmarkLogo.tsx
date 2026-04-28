interface Props {
  className?: string;
}

export function WeftmarkLogo({ className = "" }: Props) {
  return (
    <svg
      viewBox="0 0 200 72"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="Weftmark"
      role="img"
    >
      <ellipse cx="100" cy="36" rx="90" ry="30" fill="currentColor" />
      <polyline
        points="55,24 75,50 100,34 125,50 145,24"
        fill="none"
        stroke="white"
        strokeWidth="5.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
