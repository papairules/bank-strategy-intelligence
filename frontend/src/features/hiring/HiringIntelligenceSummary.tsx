import { hiringApi } from "../../api/hiring";
import { MetricCard } from "../../components/MetricCard";
import { Panel } from "../../components/Panel";
import { ErrorState, LoadingState } from "../../components/States";
import { TrendChart } from "../../components/TrendChart";
import { useApi } from "../../hooks/useApi";
import { formatDate, formatNumber, formatPercent, titleCase } from "../../utils/format";

export function HiringIntelligenceSummary({ organization }: { organization: string }) {
  const summary = useApi((signal) => hiringApi.summary(organization, signal), [organization]);
  const analytics = useApi((signal) => hiringApi.analytics(organization, signal), [organization]);

  const topCity = summary.data?.geographic.by_city[0];
  const topCapability = summary.data?.capability.capabilities[0];

  return <>
    {summary.loading && <LoadingState label="Loading executive summary…" />}
    {summary.error && <ErrorState message={summary.error} />}
    {summary.data && (
      <>
        <div className="context-strip"><span><strong>Observation period</strong>{formatDate(summary.data.observation_start)} – {formatDate(summary.data.observation_end)}</span><span><strong>Latest collection</strong>{summary.data.latest_collection_run ? `${titleCase(summary.data.latest_collection_run.status)} · ${formatDate(summary.data.latest_collection_run.completed_at)}` : "No collection run available"}</span><span><strong>Evidence coverage</strong>{formatPercent(summary.data.evidence_coverage, 0)}</span></div>
        <div className="metrics-grid metrics-grid--three">
          <MetricCard icon="01" label="Observed jobs" value={formatNumber(summary.data.total_observed_jobs)} context="Persisted normalized roles" />
          {topCity && <MetricCard icon="02" label="Top hiring geography" value={topCity.value} context={`${topCity.job_count} jobs · ${formatPercent(topCity.percentage_of_total, 1)}`} />}
          {topCapability && <MetricCard icon="03" label="Top capability" value={topCapability.capability} context={`${formatPercent(topCapability.percentage_of_classified_jobs, 1)} of classified jobs`} />}
        </div>
        {summary.data.capability.classified_job_count === 0 && <div className="data-notice"><strong>Classification coverage is limited.</strong><span>Capability views show only normalized classifications currently persisted; unavailable values are not inferred in the browser.</span></div>}
      </>
    )}

    {analytics.loading && <LoadingState label="Loading hiring analytics…" />}
    {analytics.error && <ErrorState message={analytics.error} />}
    {analytics.data && (
      <div className="analytics-grid">
        <Panel title="Observed hiring cadence" eyebrow="Weekly posting volume" className="panel--wide" action={<span className="panel-note">{analytics.data.weekly_trend.buckets.length} observed buckets · no forecast</span>}><TrendChart buckets={analytics.data.weekly_trend.buckets} /></Panel>
      </div>
    )}
  </>;
}
