import { hiringApi } from "../api/hiring";
import { MetricCard } from "../components/MetricCard";
import { Panel } from "../components/Panel";
import { RankedBars } from "../components/RankedBars";
import { ErrorState, LoadingState } from "../components/States";
import { TrendChart } from "../components/TrendChart";
import { JobExplorer } from "../features/hiring/JobExplorer";
import { useApi } from "../hooks/useApi";
import { formatDate, formatNumber, formatPercent, titleCase } from "../utils/format";

const ORGANIZATION = "Wells Fargo";

export function HiringIntelligencePage() {
  const summary = useApi((signal) => hiringApi.summary(ORGANIZATION, signal), [ORGANIZATION]);
  const analytics = useApi((signal) => hiringApi.analytics(ORGANIZATION, signal), [ORGANIZATION]);
  const signals = useApi((signal) => hiringApi.signals(ORGANIZATION, signal), [ORGANIZATION]);

  const topCity = summary.data?.geographic.by_city[0];
  const topCapability = summary.data?.capability.capabilities[0];
  const seniorityCoverage = summary.data && summary.data.total_observed_jobs > 0
    ? (summary.data.seniority.jobs_with_seniority / summary.data.total_observed_jobs) * 100
    : 0;

  return (
    <div className="page">
      <div className="page-heading">
        <div><span className="eyebrow">Hiring Intelligence</span><h1>Workforce demand and capability signals</h1><p>Evidence-backed view of observed public hiring activity. Concentrations indicate hiring demand—not confirmed strategic investment.</p></div>
        <label className="organization-select"><span>Organization</span><select value={ORGANIZATION} disabled><option>Wells Fargo</option></select></label>
      </div>

      {summary.loading && <LoadingState label="Loading executive summary…" />}
      {summary.error && <ErrorState message={summary.error} />}
      {summary.data && (
        <>
          <div className="context-strip"><span><strong>Observation period</strong>{formatDate(summary.data.observation_start)} – {formatDate(summary.data.observation_end)}</span><span><strong>Latest collection</strong>{summary.data.latest_collection_run ? `${titleCase(summary.data.latest_collection_run.status)} · ${formatDate(summary.data.latest_collection_run.completed_at)}` : "No collection run available"}</span><span><strong>Evidence coverage</strong>{formatPercent(summary.data.evidence_coverage, 0)}</span></div>
          <div className="metrics-grid">
            <MetricCard icon="01" label="Observed jobs" value={formatNumber(summary.data.total_observed_jobs)} context="Persisted normalized roles" />
            <MetricCard icon="02" label="Enrichment coverage" value={formatPercent(summary.data.enrichment_coverage, 0)} context={`${summary.data.enriched_job_count} enriched records`} />
            {summary.data.seniority.jobs_with_seniority > 0 ? <MetricCard icon="03" label="Leadership hiring" value={formatNumber(summary.data.seniority.leadership_job_count)} context={`${formatPercent(summary.data.seniority.leadership_percentage, 1)} of observed jobs`} /> : <MetricCard icon="03" label="Seniority coverage" value={formatPercent(seniorityCoverage, 0)} context="No normalized seniority classifications" />}
            {topCity && <MetricCard icon="04" label="Top hiring geography" value={topCity.value} context={`${topCity.job_count} jobs · ${formatPercent(topCity.percentage_of_total, 1)}`} />}
            {topCapability && <MetricCard icon="05" label="Top capability" value={topCapability.capability} context={`${formatPercent(topCapability.percentage_of_classified_jobs, 1)} of classified jobs`} />}
          </div>
          {(summary.data.capability.classified_job_count === 0 || summary.data.seniority.jobs_with_seniority === 0) && <div className="data-notice"><strong>Classification coverage is limited.</strong><span>Capability and seniority views show only normalized classifications currently persisted; unavailable values are not inferred in the browser.</span></div>}
        </>
      )}

      {analytics.loading && <LoadingState label="Loading hiring analytics…" />}
      {analytics.error && <ErrorState message={analytics.error} />}
      {analytics.data && (
        <div className="analytics-grid">
          <Panel title="Observed hiring cadence" eyebrow="Weekly posting volume" className="panel--wide" action={<span className="panel-note">{analytics.data.weekly_trend.buckets.length} observed buckets · no forecast</span>}><TrendChart buckets={analytics.data.weekly_trend.buckets} /></Panel>
          <Panel title="Geographic concentration" eyebrow="Top cities"><RankedBars emptyMessage="No geographic hiring observations available." items={analytics.data.geographic.by_city.map((item) => ({ label: item.value, count: item.job_count, percentage: item.percentage_of_total }))} /><div className="coverage-note">Country coverage: {analytics.data.geographic.by_country.map((item) => `${item.value} ${formatPercent(item.percentage_of_total, 1)}`).join(" · ")}</div></Panel>
          <Panel title="Capability concentration" eyebrow={`${analytics.data.capability.classified_job_count} classified jobs`}><RankedBars emptyMessage="No capability classifications available." items={analytics.data.capability.capabilities.map((item) => ({ label: item.capability, count: item.job_count, percentage: item.percentage_of_classified_jobs }))} /></Panel>
          <Panel title="Seniority and leadership" eyebrow="Classified distribution"><div className="seniority-summary"><div className="leadership-callout"><strong>{analytics.data.seniority.jobs_with_seniority ? formatNumber(analytics.data.seniority.leadership_job_count) : "—"}</strong><span>Leadership roles</span><small>{analytics.data.seniority.jobs_with_seniority ? `${formatPercent(analytics.data.seniority.leadership_percentage, 1)} of observed jobs` : "Not available without classifications"}</small></div><div className="seniority-list">{analytics.data.seniority.distribution.length ? analytics.data.seniority.distribution.map((item) => <div key={item.seniority_level}><span>{titleCase(item.seniority_level)}</span><strong>{item.job_count}</strong><div className="microbar"><i style={{ width: `${item.percentage_of_jobs_with_seniority}%` }} /></div></div>) : <div className="inline-empty">No seniority classifications available.</div>}</div></div><div className="coverage-note">Coverage: {analytics.data.seniority.jobs_with_seniority} of {analytics.data.seniority.total_jobs} observed jobs</div></Panel>
        </div>
      )}

      <Panel title="Strategic hiring signals" eyebrow="Observed hiring intelligence" action={signals.data ? <span className="panel-note">{signals.data.returned_count} signals</span> : undefined}>
        <p className="panel-intro">Threshold-based observations generated from persisted hiring evidence. These signals do not confirm bank strategy or investment decisions.</p>
        {signals.loading && <LoadingState label="Generating deterministic signals…" />}
        {signals.error && <ErrorState message={signals.error} />}
        {signals.data?.items.length === 0 && <div className="inline-empty">No intelligence signals generated for the current observation period.</div>}
        {signals.data && signals.data.items.length > 0 && <div className="signals-list">{signals.data.items.map((item) => <article className="signal-card" key={item.signal.signal_id}><div className="signal-card__meta"><span>{titleCase(item.signal.signal_type)}</span><span>{formatPercent(item.score.confidence * 100)} confidence</span></div><h3>{item.title}</h3><p>{item.signal.summary}</p><div className="signal-score"><span>Strength</span><div><i style={{ width: `${item.score.strength * 100}%` }} /></div><strong>{formatPercent(item.score.strength * 100)}</strong></div><footer><span>{formatDate(item.signal.observation_period.start_date)} – {formatDate(item.signal.observation_period.end_date)}</span><span>{item.signal.supporting_evidence_ids.length} evidence records</span></footer>{item.signal.limitations.length > 0 && <details><summary>Limitations</summary><ul>{item.signal.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></details>}</article>)}</div>}
      </Panel>

      <JobExplorer organization={ORGANIZATION} />
    </div>
  );
}
