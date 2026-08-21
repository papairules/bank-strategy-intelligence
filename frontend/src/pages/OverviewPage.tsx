import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { evidenceApi } from "../api/evidence";
import { hiringApi } from "../api/hiring";
import { strategyApi } from "../api/strategy";
import { technologyApi } from "../api/technology";
import { ErrorState, LoadingState } from "../components/States";
import { useApi } from "../hooks/useApi";
import { formatDate, formatNumber, formatPercent } from "../utils/format";

const ORGANIZATION = "Wells Fargo";

export function OverviewPage() {
  const hiring = useApi((signal) => hiringApi.summary(ORGANIZATION, signal), [ORGANIZATION]);
  const technology = useApi((signal) => technologyApi.summary(ORGANIZATION, signal), [ORGANIZATION]);
  const technologySignals = useApi((signal) => technologyApi.signals(ORGANIZATION, signal), [ORGANIZATION]);
  const evidence = useApi((signal) => evidenceApi.summary(ORGANIZATION, signal), [ORGANIZATION]);
  const strategy = useApi((signal) => strategyApi.signals(ORGANIZATION, signal), [ORGANIZATION]);
  const loading = hiring.loading || technology.loading || technologySignals.loading || evidence.loading || strategy.loading;
  const hasError = Boolean(hiring.error || technology.error || technologySignals.error || evidence.error || strategy.error);
  const intelligence = hiring.data && technology.data && technologySignals.data && evidence.data && strategy.data
    ? { hiring: hiring.data, technology: technology.data, technologySignals: technologySignals.data, evidence: evidence.data, strategy: strategy.data }
    : null;
  const topGeography = intelligence?.hiring.geographic.by_state_region[0] ?? intelligence?.hiring.geographic.by_city[0];

  return <div className="page overview-page">
    <section className="executive-header">
      <div><span className="eyebrow">Executive intelligence workspace</span><h1>Bank Strategy Intelligence</h1><p>Observed hiring evidence, deterministic intelligence, and governed interpretation for <strong>{ORGANIZATION}</strong>.</p></div>
      <div className="executive-header__scope"><span>Evidence scope</span><strong>Public hiring records</strong><small>Observed evidence—not enterprise-wide disclosure</small></div>
    </section>

    {loading && <LoadingState label="Loading executive intelligence…" />}
    {hasError && <ErrorState message="One or more intelligence domains could not be loaded." />}
    {intelligence && <>
      <div className="executive-context" aria-label="Intelligence context">
        <span><small>Organization</small><strong>{ORGANIZATION}</strong></span>
        <span><small>Observation period</small><strong>{formatDate(intelligence.hiring.observation_start)} – {formatDate(intelligence.hiring.observation_end)}</strong></span>
        <span><small>Source evidence coverage</small><strong>{formatPercent(intelligence.evidence.evidence_coverage, 0)}</strong></span>
        <span><small>AI enrichment coverage</small><strong>{formatPercent(intelligence.hiring.enrichment_coverage, 0)}</strong></span>
      </div>

      <section className="executive-section" aria-labelledby="snapshot-title">
        <div className="executive-section__heading"><div><span className="eyebrow">Intelligence snapshot</span><h2 id="snapshot-title">What the current evidence supports</h2></div><span className="section-note">All metrics are backend-derived</span></div>
        <div className="executive-metrics">
          <MetricGroup label="Observed foundation" tone="source" items={[[formatNumber(intelligence.hiring.total_observed_jobs), "Observed jobs"], [formatNumber(intelligence.evidence.total_evidence_records), "Evidence records"], [formatPercent(intelligence.evidence.evidence_coverage, 0), "Source coverage"]]} />
          <MetricGroup label="Classified intelligence" tone="enriched" items={[[formatNumber(intelligence.hiring.enriched_job_count), "Enriched jobs"], [formatNumber(intelligence.technology.snapshot.technology_observation_count), "Technology observations"], [formatNumber(intelligence.technology.snapshot.unique_technologies), "Unique technologies"]]} />
          <MetricGroup label="Deterministic signals" tone="signal" items={[[formatNumber(intelligence.hiring.signal_count), "Hiring signals"], [formatNumber(intelligence.technologySignals.generated_signal_count), "Technology signals"], [formatNumber(intelligence.strategy.generated_signal_count), "Cross-domain signals"]]} />
        </div>
      </section>

      <div className="executive-grid">
        <ExecutiveCard eyebrow="Observed hiring" title="Hiring activity in context" action={{ label: "View Hiring Intelligence", to: "/hiring" }}>
          <p>{intelligence.hiring.total_observed_jobs} public job postings were observed during the current period. These records describe hiring activity, not confirmed investment.</p>
          <dl className="executive-facts"><div><dt>Hiring signals</dt><dd>{intelligence.hiring.signal_count}</dd></div><div><dt>Strongest geography</dt><dd>{topGeography ? `${topGeography.value} · ${topGeography.job_count} jobs` : "Not available"}</dd></div><div><dt>Evidence-backed jobs</dt><dd>{intelligence.hiring.jobs_with_evidence} of {intelligence.hiring.total_observed_jobs}</dd></div></dl>
        </ExecutiveCard>

        <ExecutiveCard eyebrow="Technology observed in hiring evidence" title="A bounded technology footprint" action={{ label: "View Technology Intelligence", to: "/technology" }}>
          <p>Persisted enrichment produced {intelligence.technology.snapshot.technology_observation_count} evidence-linked observations across {intelligence.technology.snapshot.unique_technologies} normalized technologies. This is not an enterprise technology stack.</p>
          <dl className="executive-facts"><div><dt>Classification coverage</dt><dd>{formatPercent(intelligence.technology.snapshot.technology_coverage_percentage, 0)}</dd></div><div><dt>Deterministic signals</dt><dd>{intelligence.technologySignals.generated_signal_count}</dd></div><div><dt>Signal scope</dt><dd>Observed hiring evidence</dd></div></dl>
        </ExecutiveCard>

        <ExecutiveCard eyebrow="Strategic signals" title={intelligence.strategy.generated_signal_count ? "Supported cross-domain patterns" : "Cross-domain conclusions are withheld"} action={{ label: "View Strategic Signals", to: "/signals" }} className="executive-card--suppressed">
          {intelligence.strategy.generated_signal_count ? <p>{intelligence.strategy.generated_signal_count} cross-domain signals meet the configured independent-support thresholds.</p> : <p>No cross-domain signal currently meets every configured requirement. This is a governed suppression state, not missing data or a system failure.</p>}
          <ul className="executive-limitations">{intelligence.strategy.limitations.slice(0, 3).map((item) => <li key={item}>{item}</li>)}</ul>
        </ExecutiveCard>

        <ExecutiveCard eyebrow="Evidence & traceability" title="Every output resolves to observed evidence" action={{ label: "Explore Evidence", to: "/evidence" }}>
          <p>Source records, AI enrichment, and derived intelligence remain visibly separate while preserving job and evidence relationships.</p>
          <dl className="executive-facts"><div><dt>Enriched evidence</dt><dd>{intelligence.evidence.enriched_evidence_count} of {intelligence.evidence.total_evidence_records}</dd></div><div><dt>Supports observations</dt><dd>{intelligence.evidence.evidence_supporting_technology_observations} records</dd></div><div><dt>Supports tech signals</dt><dd>{intelligence.evidence.evidence_supporting_technology_signals} records</dd></div></dl>
        </ExecutiveCard>
      </div>

      <section className="governed-ai-entry" aria-labelledby="governed-ai-title">
        <div><span className="eyebrow">Governed AI</span><h2 id="governed-ai-title">Ask the evidence. Then ask across intelligence.</h2><p>Both agents execute only after explicit submission, use approved read-only tools, and return application-validated provenance and reliability.</p></div>
        <div className="governed-ai-actions"><Link to="/evidence#ask-evidence"><span>Evidence retrieval</span><strong>Ask Evidence</strong><small>Grounded factual and provenance questions</small></Link><Link to="/signals#ask-strategy"><span>Strategic synthesis</span><strong>Ask Strategy</strong><small>Governed interpretation across intelligence domains</small></Link></div>
      </section>

      <section className="intelligence-flow" aria-label="Intelligence provenance flow">
        {["Observed evidence", "AI enrichment", "Derived analytics", "Deterministic signals", "Governed interpretation"].map((item, index) => <div key={item}><span>{String(index + 1).padStart(2, "0")}</span><strong>{item}</strong>{index < 4 && <i aria-hidden="true" />}</div>)}
      </section>
    </>}
  </div>;
}

function MetricGroup({ label, tone, items }: { label: string; tone: string; items: [string, string][] }) {
  return <article className={`metric-group metric-group--${tone}`}><header>{label}</header><div>{items.map(([value, itemLabel]) => <span key={itemLabel}><strong>{value}</strong><small>{itemLabel}</small></span>)}</div></article>;
}

function ExecutiveCard({ eyebrow, title, action, children, className = "" }: { eyebrow: string; title: string; action: { label: string; to: string }; children: ReactNode; className?: string }) {
  return <article className={`executive-card ${className}`}><span className="eyebrow">{eyebrow}</span><h2>{title}</h2><div className="executive-card__body">{children}</div><Link to={action.to}>{action.label}<span aria-hidden="true">→</span></Link></article>;
}
