import { hiringApi } from "../../api/hiring";
import { Panel } from "../../components/Panel";
import { ErrorState, LoadingState } from "../../components/States";
import { TrendChart } from "../../components/TrendChart";
import { useApi } from "../../hooks/useApi";

export function HiringIntelligenceSummary({ organization }: { organization: string }) {
  const analytics = useApi((signal) => hiringApi.analytics(organization, signal), [organization]);

  return <>
    {analytics.loading && <LoadingState label="Loading hiring analytics…" />}
    {analytics.error && <ErrorState message={analytics.error} />}
    {analytics.data && (
      <div className="analytics-grid">
        <Panel title="Observed hiring cadence" eyebrow="Weekly posting volume" className="panel--wide" action={<span className="panel-note">{analytics.data.weekly_trend.buckets.length} observed buckets · no forecast</span>}><TrendChart buckets={analytics.data.weekly_trend.buckets} /></Panel>
      </div>
    )}
  </>;
}
