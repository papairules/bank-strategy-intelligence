import { formatPercent } from "../utils/format";

interface RankedItem {
  label: string;
  count: number;
  percentage: number;
}

export function RankedBars({ items, emptyMessage }: { items: RankedItem[]; emptyMessage: string }) {
  if (!items.length) return <div className="inline-empty">{emptyMessage}</div>;
  return (
    <div className="ranked-bars">
      {items.slice(0, 7).map((item, index) => (
        <div className="ranked-row" key={item.label}>
          <span className="ranked-row__index">{String(index + 1).padStart(2, "0")}</span>
          <div className="ranked-row__content">
            <div className="ranked-row__labels">
              <strong>{item.label}</strong>
              <span>{item.count} jobs · {formatPercent(item.percentage, 1)}</span>
            </div>
            <div className="bar-track" aria-label={`${item.label} ${item.percentage}%`}>
              <span style={{ width: `${Math.min(item.percentage, 100)}%` }} />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
