import "./DonutChart.css";

interface Segment {
  label: string;
  value: number;
  color: string;
}

/** Status-colored donut - pass/fail is a state, not a category, so it uses
 * the fixed status palette (good/critical) rather than categorical hues. */
function DonutChart({ segments, centerLabel }: { segments: Segment[]; centerLabel: string }) {
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  const radius = 15.9155;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  return (
    <div className="donut-chart">
      <svg viewBox="0 0 36 36" className="donut-chart-svg">
        <circle cx="18" cy="18" r={radius} fill="none" stroke="var(--border)" strokeWidth="3.2" />
        {total > 0 &&
          segments.map((segment) => {
            const fraction = segment.value / total;
            const dash = fraction * circumference;
            const circle = (
              <circle
                key={segment.label}
                cx="18"
                cy="18"
                r={radius}
                fill="none"
                stroke={segment.color}
                strokeWidth="3.2"
                strokeDasharray={`${dash} ${circumference - dash}`}
                strokeDashoffset={-offset}
                strokeLinecap="round"
                transform="rotate(-90 18 18)"
              />
            );
            offset += dash;
            return circle;
          })}
      </svg>
      <div className="donut-chart-center">
        <span className="donut-chart-value">{total > 0 ? `${Math.round((segments[0].value / total) * 100)}%` : "–"}</span>
        <span className="donut-chart-label">{centerLabel}</span>
      </div>
      <div className="donut-chart-legend">
        {segments.map((segment) => (
          <div className="donut-legend-row" key={segment.label}>
            <span className="donut-legend-dot" style={{ background: segment.color }} />
            {segment.label} ({segment.value})
          </div>
        ))}
      </div>
    </div>
  );
}

export default DonutChart;
