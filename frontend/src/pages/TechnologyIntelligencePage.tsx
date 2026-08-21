import { useState } from "react";
import { technologyApi } from "../api/technology";
import { MetricCard } from "../components/MetricCard";
import { Panel } from "../components/Panel";
import { RankedBars } from "../components/RankedBars";
import { ErrorState, LoadingState } from "../components/States";
import { CURRENT_ORGANIZATION } from "../config/organization";
import { JobDetailPanel } from "../features/hiring/JobDetailPanel";
import { EvidenceDetailPanel } from "../features/evidence/EvidenceDetailPanel";
import { useApi } from "../hooks/useApi";
import { formatDate, formatNumber, formatPercent, titleCase } from "../utils/format";

const PAGE_SIZE = 25;

export function TechnologyIntelligencePage() {
  const [selectedJob, setSelectedJob] = useState<string | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<string | null>(null);
  const summary = useApi((signal) => technologyApi.summary(CURRENT_ORGANIZATION, signal), [CURRENT_ORGANIZATION]);
  const analytics = useApi((signal) => technologyApi.analytics(CURRENT_ORGANIZATION, signal), [CURRENT_ORGANIZATION]);
  const signals = useApi((signal) => technologyApi.signals(CURRENT_ORGANIZATION, signal), [CURRENT_ORGANIZATION]);
  const observations = useApi(
    (signal) => technologyApi.observations(CURRENT_ORGANIZATION, { limit: PAGE_SIZE, offset: 0 }, signal),
    [CURRENT_ORGANIZATION],
  );

  return (
    <div className="page">
      <div className="page-heading">
        <div><span className="eyebrow">Technology Intelligence</span><h1>Observed technology demand from hiring evidence</h1><p>Traceable technologies extracted from persisted hiring enrichment. Observations indicate demand in classified roles—not confirmed organization-wide technology strategy.</p></div>
        <label className="organization-select"><span>Organization</span><select value={CURRENT_ORGANIZATION} disabled><option>{CURRENT_ORGANIZATION}</option></select></label>
      </div>

      {summary.loading && <LoadingState label="Loading technology coverage…" />}
      {summary.error && <ErrorState message={summary.error} />}
      {summary.data && <>
        <div className="technology-coverage-notice"><strong>Classification coverage</strong><span>Technology classifications are available for {summary.data.snapshot.enriched_jobs} of {summary.data.snapshot.total_jobs} observed hiring records.</span>{summary.data.coverage_limitation && <small>{summary.data.coverage_limitation}</small>}</div>
        <div className="metrics-grid metrics-grid--four">
          <MetricCard icon="01" label="Enriched jobs" value={formatNumber(summary.data.snapshot.enriched_jobs)} context={`${summary.data.snapshot.total_jobs} total observed jobs`} />
          <MetricCard icon="02" label="Technology observations" value={formatNumber(summary.data.snapshot.technology_observation_count)} context="Evidence-linked mentions" />
          <MetricCard icon="03" label="Unique technologies" value={formatNumber(summary.data.snapshot.unique_technologies)} context="Conservatively normalized" />
          <MetricCard icon="04" label="Classification coverage" value={formatPercent(summary.data.snapshot.technology_coverage_percentage, 1)} context={`${formatDate(summary.data.snapshot.observation_start)} – ${formatDate(summary.data.snapshot.observation_end)}`} />
        </div>
      </>}

      {analytics.loading && <LoadingState label="Loading technology analytics…" />}
      {analytics.error && <ErrorState message={analytics.error} />}
      {analytics.data && <div className="analytics-grid">
        <Panel title="Top observed technologies" eyebrow="Share of enriched jobs"><RankedBars emptyMessage="No technology observations available." items={analytics.data.top_technologies.map((item) => ({ label: item.technology, count: item.job_count, percentage: item.percentage_of_enriched_jobs }))} /><p className="coverage-note">Percentages use enriched jobs as the denominator, not all observed jobs.</p></Panel>
        <Panel title="Technology category mix" eyebrow="Observed classifications">{analytics.data.categories.length ? <div className="category-list">{analytics.data.categories.map((item) => <div key={item.category}><span>{item.category}</span><strong>{item.observation_count}</strong><small>{item.unique_technology_count} unique technologies · {item.job_count} jobs</small></div>)}</div> : <div className="inline-empty">No technology categories available.</div>}</Panel>
      </div>}

      <Panel title="Technology signals" eyebrow="Observed hiring intelligence" action={signals.data ? <span className="panel-note">{signals.data.generated_signal_count} signals</span> : undefined}>
        <p className="panel-intro">Deterministic signals are generated only when enriched hiring coverage and contributing evidence meet conservative minimum thresholds.</p>
        {signals.loading && <LoadingState label="Evaluating technology signal thresholds…" />}
        {signals.error && <ErrorState message={signals.error} />}
        {signals.data?.signals.length === 0 && <div className="technology-signal-empty"><strong>No deterministic technology signal met every configured support threshold.</strong><span>{signals.data.enriched_jobs} of {signals.data.total_jobs} observed jobs are enriched ({formatPercent(signals.data.enrichment_coverage * 100, 1)} classification coverage). Signal suppression may still reflect contributor, concentration, source, or observation-period requirements.</span>{signals.data.limitations.length > 0 && <ul>{signals.data.limitations.map((item) => <li key={item}>{item}</li>)}</ul>}</div>}
        {signals.data && signals.data.signals.length > 0 && <div className="signals-list">{signals.data.signals.map((item) => <article className="signal-card" key={item.signal_id}><div className="signal-card__meta"><span>Deterministic signal · {titleCase(item.signal_type)}</span><span>{formatPercent(item.confidence * 100, 0)} confidence</span></div><h3>{item.title}</h3><p>{item.summary}</p><div className="signal-score"><span>Strength</span><div><i style={{ width: `${item.strength * 100}%` }} /></div><strong>{formatPercent(item.strength * 100, 0)}</strong></div><div className="technology-signal-metrics"><span>Evidence coverage <strong>{formatPercent(item.evidence_coverage * 100, 0)}</strong></span><span>{item.supporting_job_ids.length} jobs</span><span>{item.supporting_evidence_ids.length} evidence records</span></div><footer><span>{formatDate(item.observation_start)} – {formatDate(item.observation_end)}</span><span className="signal-actions">{item.supporting_job_ids[0] && <button className="signal-reference-button" onClick={() => setSelectedJob(item.supporting_job_ids[0])}>View job</button>}{item.supporting_evidence_ids[0] && <button className="signal-reference-button" onClick={() => setSelectedEvidence(item.supporting_evidence_ids[0])}>View evidence</button>}</span></footer>{item.limitations.length > 0 && <details><summary>Limitations</summary><ul>{item.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></details>}</article>)}</div>}
      </Panel>

      <Panel title="Technology observations" eyebrow="Job and evidence traceability" action={observations.data ? <span className="panel-note">{observations.data.total} observations</span> : undefined}>
        {observations.loading && <LoadingState label="Loading technology observations…" />}
        {observations.error && <ErrorState message={observations.error} />}
        {observations.data?.items.length === 0 && <div className="inline-empty">No technology observations are available for this organization.</div>}
        {observations.data && observations.data.items.length > 0 && <div className="table-wrap"><table><thead><tr><th>Technology</th><th>Category</th><th>Related job</th><th>Business unit</th><th>Location</th><th>Evidence</th><th>Confidence</th></tr></thead><tbody>{observations.data.items.map((item) => <tr key={`${item.job_id}-${item.normalized_technology}`}><td><strong>{item.normalized_technology}</strong>{item.technology !== item.normalized_technology && <span className="table-subtext">Source: {item.technology}</span>}</td><td>{item.category}</td><td><button className="job-title-button" onClick={() => setSelectedJob(item.job_id)}>{item.job_title}</button></td><td>{item.business_unit ?? <span className="muted">Not available</span>}</td><td>{item.location}</td><td><button className="job-title-button mono evidence-reference" title={item.evidence_id} onClick={() => setSelectedEvidence(item.evidence_id)}>{item.evidence_id.slice(0, 8)}…</button>{item.support_references[0]?.excerpt && <span className="table-subtext support-snippet">{item.support_references[0].excerpt}</span>}</td><td>{formatPercent(item.confidence * 100, 0)}<span className="table-subtext">{titleCase(item.provenance.provider)}</span></td></tr>)}</tbody></table></div>}
      </Panel>
      {selectedJob && <JobDetailPanel organization={CURRENT_ORGANIZATION} jobId={selectedJob} onClose={() => setSelectedJob(null)} />}
      {selectedEvidence && <EvidenceDetailPanel organization={CURRENT_ORGANIZATION} evidenceId={selectedEvidence} onClose={() => setSelectedEvidence(null)} onViewJob={(jobId) => { setSelectedEvidence(null); setSelectedJob(jobId); }} />}
    </div>
  );
}
