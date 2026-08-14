import "./LineChart.css";

interface Point {
  label: string;
  value: number;
}

function buildPath(points: Point[], width: number, height: number, max: number): string {
  if (points.length === 0) return "";
  const stepX = points.length > 1 ? width / (points.length - 1) : 0;
  return points
    .map((p, i) => {
      const x = points.length > 1 ? i * stepX : width / 2;
      const y = max > 0 ? height - (p.value / max) * height : height;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

/** Single-series line chart, thin 2px stroke, rounded caps, a filled area
 * under the line, and a direct label on the last point only (not one per
 * point) - matches the "selective direct labels" mark spec. */
function LineChart({ data, color, formatValue }: { data: Point[]; color: string; formatValue?: (v: number) => string }) {
  const width = 100;
  const height = 40;
  const max = Math.max(...data.map((d) => d.value), 1);
  const path = buildPath(data, width, height, max);
  const areaPath = data.length > 0 ? `${path} L${width},${height} L0,${height} Z` : "";
  const last = data.at(-1);
  const format = formatValue ?? ((v: number) => `${v}`);

  return (
    <div className="line-chart">
      {data.length === 0 ? (
        <p className="chart-empty">Not enough data yet.</p>
      ) : (
        <>
          <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="line-chart-svg">
            <path d={areaPath} fill={color} opacity="0.12" stroke="none" />
            <path d={path} fill="none" stroke={color} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
          </svg>
          <div className="line-chart-footer">
            <span className="line-chart-range">
              {data[0]?.label} – {last?.label}
            </span>
            {last && (
              <span className="line-chart-last" style={{ color }}>
                {format(last.value)}
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default LineChart;
