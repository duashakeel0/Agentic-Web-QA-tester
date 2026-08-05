import "./BarList.css";

interface BarItem {
  label: string;
  value: number;
  color?: string;
}

/** Horizontal bar list - magnitude across discrete labels, so one hue
 * (or the caller's status color per row) rather than a rainbow. */
function BarList({ items, defaultColor = "var(--accent)" }: { items: BarItem[]; defaultColor?: string }) {
  const max = Math.max(...items.map((i) => i.value), 1);

  if (items.length === 0) {
    return <p className="chart-empty">No data yet.</p>;
  }

  return (
    <div className="bar-list">
      {items.map((item) => (
        <div className="bar-list-row" key={item.label}>
          <span className="bar-list-label" title={item.label}>
            {item.label}
          </span>
          <div className="bar-list-track">
            <div
              className="bar-list-fill"
              style={{ width: `${(item.value / max) * 100}%`, background: item.color ?? defaultColor }}
            />
          </div>
          <span className="bar-list-value">{item.value}</span>
        </div>
      ))}
    </div>
  );
}

export default BarList;
