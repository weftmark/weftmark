interface TieUpDiagramProps {
  tieup: number[][];
  numShafts: number;
  numTreadles: number;
  cellSize?: number;
}

export function TieUpDiagram({ tieup, numShafts, numTreadles, cellSize = 18 }: TieUpDiagramProps) {
  const labelW = 20;
  const labelH = 20;
  const width = labelW + numTreadles * cellSize;
  const height = labelH + numShafts * cellSize;

  const filled = new Set<string>();
  tieup.forEach((shafts, ti) => {
    shafts.forEach((s) => filled.add(`${ti}_${s}`));
  });

  return (
    <svg
      width={width}
      height={height}
      className="block overflow-visible"
      style={{ fontFamily: "ui-monospace, monospace" }}
    >
      {/* Treadle column labels */}
      {Array.from({ length: numTreadles }, (_, ti) => (
        <text
          key={`tc-${ti}`}
          x={labelW + ti * cellSize + cellSize / 2}
          y={labelH - 4}
          textAnchor="middle"
          fontSize={9}
          fill="currentColor"
          opacity={0.5}
        >
          {ti + 1}
        </text>
      ))}
      {/* Shaft row labels */}
      {Array.from({ length: numShafts }, (_, si) => (
        <text
          key={`sr-${si}`}
          x={labelW - 4}
          y={labelH + si * cellSize + cellSize / 2 + 3}
          textAnchor="end"
          fontSize={9}
          fill="currentColor"
          opacity={0.5}
        >
          {si + 1}
        </text>
      ))}
      {/* Grid cells */}
      {Array.from({ length: numTreadles }, (_, ti) =>
        Array.from({ length: numShafts }, (_, si) => {
          const isFilled = filled.has(`${ti}_${si + 1}`);
          return (
            <rect
              key={`${ti}_${si}`}
              x={labelW + ti * cellSize + 0.5}
              y={labelH + si * cellSize + 0.5}
              width={cellSize - 1}
              height={cellSize - 1}
              fill={isFilled ? "currentColor" : "none"}
              stroke="currentColor"
              strokeWidth={0.5}
              opacity={isFilled ? 0.75 : 0.12}
              rx={1}
            />
          );
        })
      )}
    </svg>
  );
}
