import type { TrendBucket } from "../types/hiring";
import { formatDate } from "../utils/format";

export function TrendChart({ buckets }: { buckets: TrendBucket[] }) {
  if (!buckets.length) {
    return <div className="inline-empty">No hiring trend observations available.</div>;
  }
  const width = 760;
  const height = 240;
  const padding = 32;
  const max = Math.max(...buckets.map((bucket) => bucket.job_count), 1);
  const points = buckets.map((bucket, index) => ({
    ...bucket,
    x: padding + (index * (width - padding * 2)) / Math.max(buckets.length - 1, 1),
    y: height - padding - (bucket.job_count / max) * (height - padding * 2),
  }));
  const line = points.map((point) => `${point.x},${point.y}`).join(" ");

  return (
    <div className="trend-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Observed weekly job posting counts">
        {[0, 0.5, 1].map((ratio) => {
          const y = padding + ratio * (height - padding * 2);
          return <line key={ratio} x1={padding} x2={width - padding} y1={y} y2={y} className="grid-line" />;
        })}
        <polyline points={line} className="trend-line" />
        {points.map((point) => (
          <g key={point.bucket_start}>
            <circle cx={point.x} cy={point.y} r="5" className="trend-point">
              <title>{`${formatDate(point.bucket_start)}: ${point.job_count} jobs`}</title>
            </circle>
          </g>
        ))}
      </svg>
      <div className="trend-axis">
        <span>{formatDate(buckets[0].bucket_start)}</span>
        <span>{formatDate(buckets[buckets.length - 1].bucket_start)}</span>
      </div>
    </div>
  );
}
