import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { evidenceApi } from "../api/evidence";
import { hiringApi } from "../api/hiring";
import { strategyApi } from "../api/strategy";
import { technologyApi } from "../api/technology";
import { ErrorState, LoadingState } from "../components/States";
import { useOrganization } from "../context/OrganizationContext";
import { useApi } from "../hooks/useApi";
import { formatDate, formatNumber, formatPercent } from "../utils/format";

export function OverviewPage() {
  const { organization } = useOrganization();
  const hiring = useApi((signal) => hiringApi.summary(organization, signal), [organization]);
  const technology = useApi((signal) => technologyApi.summary(organization, signal), [organization]);
  const technologySignals = useApi((signal) => technologyApi.signals(organization, signal), [organization]);
  const evidence = useApi((signal) => evidenceApi.summary(organization, signal), [organization]);
  const strategy = useApi((signal) => strategyApi.signals(organization, signal), [organization]);
  const loading = hiring.loading || technology.loading || technologySignals.loading || evidence.loading || strategy.loading;
  const hasError = Boolean(hiring.error || technology.error || technologySignals.error || evidence.error || strategy.error);
  const intelligence = hiring.data && technology.data && technologySignals.data && evidence.data && strategy.data
    ? { hiring: hiring.data, technology: technology.data, technologySignals: technologySignals.data, evidence: evidence.data, strategy: strategy.data }
    : null;
  const topGeography = intelligence?.hiring.geographic.by_state_region[0] ?? intelligence?.hiring.geographic.by_city[0];

  return <div className="page overview-page">
    <section className="executive-header">
      <div><span className="eyebrow">Executive intelligence workspace</span><h1>Bank Strategy Intelligence</h1><p>Observed hiring evidence, deterministic intelligence, and governed interpretation for <strong>{organization}</strong>.</p></div>
      <div className="executive-header__scope"><span>Evidence scope</span><strong>Public hiring records</strong><small>Observed evidence—not enterprise-wide disclosure</small></div>
    </section>

    {loading && <LoadingState label="Loading executive intelligence…" />}
    {hasError && <ErrorState message="One or more intelligence domains could not be loaded." />}
    {intelligence && <>
      <div className="executive-context" aria-label="Intelligence context">
        <span><small>Organization</small><strong>{organization}</strong></span>
        <span><small>Observation period</small><strong>{formatDate(intelligence.hiring.observation_start)} – {formatDate(intelligence.hiring.observation_end)}</strong></span>
        <span><small>Source evidence coverage</small><strong>{formatPercent(intelligence.evidence.evidence_coverage, 0)}</strong></span>
        <span><small>AI enrichment coverage</small><strong>{formatPercent(intelligence.hiring.enrichment_coverage, 0)}</strong></span>
      </div>

      <section className="executive-section" aria-labelledby="snapshot-title">
        <div className="executive-section__heading"><div><span className="eyebrow">Intelligence snapshot</span><h2 id="snapshot-title">What the current evidence supports</h2></div><span className="section-note">All metrics are backend-derived</span></div>
        <div className="executive-metrics executive-metrics--compact">
          <MetricGroup label="Current intelligence" tone="signal" items={[[formatNumber(intelligence.hiring.total_observed_jobs), "Observed jobs"], [formatNumber(intelligence.hiring.signal_count), "Hiring signals"], [formatNumber(intelligence.strategy.generated_signal_count), "Strategic signals"]]} />
        </div>
      </section>

      <div className="executive-grid">
        <ExecutiveCard eyebrow="Observed hiring" title="Hiring activity in context" action={{ label: "View Hiring Intelligence", to: "/hiring" }}>
          <p>{intelligence.hiring.total_observed_jobs} public job postings were observed during the current period. These records describe hiring activity, not confirmed investment.</p>
          <dl className="executive-facts"><div><dt>Observed jobs</dt><dd>{formatNumber(intelligence.hiring.total_observed_jobs)}</dd></div><div><dt>Hiring signals</dt><dd>{intelligence.hiring.signal_count}</dd></div><div><dt>Strongest geography</dt><dd>{topGeography ? `${topGeography.value} · ${topGeography.job_count} jobs` : "Not available"}</dd></div></dl>
        </ExecutiveCard>

        <ExecutiveCard eyebrow="Strategic signals" title={intelligence.strategy.generated_signal_count ? "Supported cross-domain patterns" : "Cross-domain conclusions are withheld"} action={{ label: "View Strategic Signals", to: "/signals" }} className="executive-card--suppressed">
          {intelligence.strategy.generated_signal_count ? <p><strong>{intelligence.strategy.generated_signal_count} strategic signals</strong> represent supported patterns observed across the current intelligence domains.</p> : <p>No strategic signal currently meets every configured support requirement.</p>}
        </ExecutiveCard>

        <ExecutiveCard eyebrow="Company report" title="Evidence-backed company outlook" action={{ label: "View Company Report", to: "/report" }}>
          <p>Combine Strategy, Hiring, and Hiring KG intelligence into an evidence-grounded company outlook with opportunities and time horizons.</p>
        </ExecutiveCard>
      </div>
    </>}
  </div>;
}

function MetricGroup({ label, tone, items }: { label: string; tone: string; items: [string, string][] }) {
  return <article className={`metric-group metric-group--${tone}`}><header>{label}</header><div>{items.map(([value, itemLabel]) => <span key={itemLabel}><strong>{value}</strong><small>{itemLabel}</small></span>)}</div></article>;
}

function ExecutiveCard({ eyebrow, title, action, children, className = "" }: { eyebrow: string; title: string; action: { label: string; to: string }; children: ReactNode; className?: string }) {
  return <article className={`executive-card ${className}`}><span className="eyebrow">{eyebrow}</span><h2>{title}</h2><div className="executive-card__body">{children}</div><Link to={action.to}>{action.label}<span aria-hidden="true">→</span></Link></article>;
}
