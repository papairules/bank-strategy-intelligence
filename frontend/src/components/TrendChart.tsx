import type { TrendBucket } from "../types/hiring";
import { formatDate } from "../utils/format";

const MAX_X_LABELS = 10;

function formatShortDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" }).format(
    new Date(`${value.slice(0, 10)}T00:00:00Z`),
  );
}

export function TrendChart({ buckets }: { buckets: TrendBucket[] }) {
  if (!buckets.length) {
    return <div className="inline-empty">No hiring trend observations available.</div>;
  }
  const width = 760;
  const height = 260;
  const padLeft = 40;
  const padRight = 16;
  const padTop = 22;
  const padBottom = 44;
  const plotWidth = width - padLeft - padRight;
  const plotHeight = height - padTop - padBottom;
  const max = Math.max(...buckets.map((bucket) => bucket.job_count), 1);
  const points = buckets.map((bucket, index) => ({
    ...bucket,
    x: padLeft + (index * plotWidth) / Math.max(buckets.length - 1, 1),
    y: padTop + plotHeight - (bucket.job_count / max) * plotHeight,
  }));
  const line = points.map((point) => `${point.x},${point.y}`).join(" ");
  const yTicks = [0, 0.5, 1].map((ratio) => ({
    y: padTop + plotHeight - ratio * plotHeight,
    value: Math.round(max * ratio),
  }));
  const xLabelStep = Math.max(1, Math.ceil(points.length / MAX_X_LABELS));

  return (
    <div className="trend-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Observed weekly job posting counts">
        {yTicks.map((tick) => (
          <g key={tick.y}>
            <line x1={padLeft} x2={width - padRight} y1={tick.y} y2={tick.y} className="grid-line" />
            <text x={padLeft - 8} y={tick.y} className="trend-y-label" textAnchor="end" dominantBaseline="middle">{tick.value}</text>
          </g>
        ))}
        <polyline points={line} className="trend-line" />
        {points.map((point, index) => (
          <g key={point.bucket_start}>
            <circle cx={point.x} cy={point.y} r="5" className="trend-point">
              <title>{`${formatDate(point.bucket_start)}: ${point.job_count} jobs`}</title>
            </circle>
            <text x={point.x} y={point.y - 12} className="trend-value-label" textAnchor="middle">{point.job_count}</text>
            {index % xLabelStep === 0 && (
              <text x={point.x} y={height - padBottom + 16} className="trend-x-label" textAnchor="end" transform={`rotate(-40 ${point.x} ${height - padBottom + 16})`}>{formatShortDate(point.bucket_start)}</text>
            )}
          </g>
        ))}
      </svg>
    </div>
  );
}
