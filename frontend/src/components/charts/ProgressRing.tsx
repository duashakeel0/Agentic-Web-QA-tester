import "./ProgressRing.css";

function ProgressRing({ percent, label }: { percent: number; label: string }) {
  const radius = 15.9155;
  const circumference = 2 * Math.PI * radius;
  const dash = (Math.min(100, Math.max(0, percent)) / 100) * circumference;

  return (
    <div className="progress-ring">
      <svg viewBox="0 0 36 36" className="progress-ring-svg">
        <circle cx="18" cy="18" r={radius} fill="none" stroke="var(--border)" strokeWidth="3" />
        <circle
          cx="18"
          cy="18"
          r={radius}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="3"
          strokeDasharray={`${dash} ${circumference - dash}`}
          strokeLinecap="round"
          transform="rotate(-90 18 18)"
        />
      </svg>
      <div className="progress-ring-center">
        <span className="progress-ring-value">{Math.round(percent)}%</span>
        <span className="progress-ring-label">{label}</span>
      </div>
    </div>
  );
}

export default ProgressRing;
