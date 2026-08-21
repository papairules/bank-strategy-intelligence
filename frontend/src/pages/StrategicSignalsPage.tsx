import { Link } from "react-router-dom";
import { strategyApi } from "../api/strategy";
import { MetricCard } from "../components/MetricCard";
import { Panel } from "../components/Panel";
import { ErrorState, LoadingState } from "../components/States";
import { useApi } from "../hooks/useApi";
import { AskStrategyPanel } from "../features/strategy/AskStrategyPanel";
import { formatDate, formatNumber, formatPercent, titleCase } from "../utils/format";

const ORGANIZATION = "Wells Fargo";

export function StrategicSignalsPage() {
  const result = useApi((signal) => strategyApi.signals(ORGANIZATION, signal), [ORGANIZATION]);
  return <div className="page">
    <div className="page-heading"><div><span className="eyebrow">Strategic Signals</span><h1>Cross-domain observed intelligence patterns</h1><p>Cross-domain patterns derived from evidence-backed hiring and technology intelligence. Signals describe sufficiently supported overlap—not recommendations, causation, or confirmed organizational strategy.</p></div><label className="organization-select"><span>Organization</span><select value={ORGANIZATION} disabled><option>Wells Fargo</option></select></label></div>
    {result.loading && <LoadingState label="Evaluating cross-domain evidence…" />}
    {result.error && <ErrorState message={result.error} />}
    {result.data && <>
      <div className="metrics-grid metrics-grid--four"><MetricCard icon="01" label="Hiring evidence coverage" value={formatPercent(result.data.coverage_context.hiring_evidence_coverage * 100, 1)} context={`${result.data.coverage_context.jobs_with_evidence} of ${result.data.coverage_context.total_jobs} jobs`} /><MetricCard icon="02" label="Enrichment coverage" value={formatPercent(result.data.coverage_context.enrichment_coverage * 100, 1)} context={`${result.data.coverage_context.enriched_jobs} enriched jobs`} /><MetricCard icon="03" label="Domain contributors" value={formatNumber(result.data.coverage_context.technology_observation_count)} context={`${result.data.coverage_context.hiring_signal_count} hiring signals · ${result.data.coverage_context.technology_signal_count} technology signals`} /><MetricCard icon="04" label="Strategic signals" value={formatNumber(result.data.generated_signal_count)} context={`${formatDate(result.data.coverage_context.observation_start)} – ${formatDate(result.data.coverage_context.observation_end)}`} /></div>
      <Panel title="Cross-domain strategic signals" eyebrow="Deterministic intelligence alignment" action={<span className="panel-note">{result.data.generated_signal_count} signals</span>}>
        {result.data.signals.length === 0 ? <div className="strategic-suppression"><strong>Not enough independent support yet for a governed cross-domain signal.</strong><p>Source evidence covers {result.data.coverage_context.jobs_with_evidence} of {result.data.coverage_context.total_jobs} jobs, and AI enrichment covers {result.data.coverage_context.enriched_jobs}. Coverage alone does not satisfy observation-period, overlap, concentration, and independent-contributor requirements.</p>{result.data.limitations.length > 0 && <ul>{result.data.limitations.map((item) => <li key={item}>{item}</li>)}</ul>}<Link className="primary-button primary-button--link" to="/evidence">Inspect supporting evidence</Link></div> : <div className="signals-list">{result.data.signals.map((signal) => <article className="signal-card strategic-signal-card" key={signal.signal_id}><div className="signal-card__meta"><span>Deterministic signal · {titleCase(signal.signal_type)}</span><span>{formatPercent(signal.confidence * 100)} confidence</span></div><h3>{signal.title}</h3><p>{signal.summary}</p><div className="domain-tags">{signal.domains_involved.map((domain) => <span key={domain}>{titleCase(domain)}</span>)}</div><div className="signal-score"><span>Strength</span><div><i style={{ width: `${signal.strength * 100}%` }} /></div><strong>{formatPercent(signal.strength * 100)}</strong></div><div className="strategic-signal-metrics"><span>Evidence coverage <strong>{formatPercent(signal.evidence_coverage * 100)}</strong></span><span>{signal.hiring_contributor_count} hiring contributors</span><span>{signal.technology_contributor_count} technology contributors</span><span>{signal.supporting_evidence_ids.length} evidence records</span></div><footer><span>{formatDate(signal.observation_start)} – {formatDate(signal.observation_end)}</span><Link to="/evidence">Trace evidence</Link></footer>{signal.limitations.length > 0 && <details><summary>Limitations</summary><ul>{signal.limitations.map((item) => <li key={item}>{item}</li>)}</ul></details>}</article>)}</div>}
      </Panel>
      <div className="intelligence-divider"><span>Agent-generated strategic synthesis</span></div>
      <div id="ask-strategy"><AskStrategyPanel organization={ORGANIZATION} /></div>
    </>}
  </div>;
}
