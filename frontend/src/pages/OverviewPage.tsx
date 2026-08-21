import { Link } from "react-router-dom";

export function OverviewPage() {
  return (
    <div className="page overview-page">
      <div className="page-heading"><div><span className="eyebrow">Platform overview</span><h1>Evidence-backed intelligence for bank strategy</h1><p>Connect public-source research, deterministic analysis, and traceable intelligence signals in one executive workspace.</p></div></div>
      <section className="overview-hero">
        <div><span className="eyebrow">Available intelligence vertical</span><h2>Hiring Intelligence</h2><p>Examine observed workforce demand, capability concentration, geographic activity, enrichment, and supporting source evidence.</p><Link className="primary-button primary-button--link" to="/hiring">Open hiring intelligence</Link></div>
        <div className="flow-diagram"><span>Public hiring evidence</span><i /><span>Normalized intelligence</span><i /><span>Executive signals</span></div>
      </section>
      <div className="roadmap-grid">{["Technology Intelligence", "Organization Intelligence", "Strategy Intelligence"].map((name) => <article key={name}><span>Planned capability</span><h3>{name}</h3><p>Coming soon as the platform expands beyond the validated Hiring Intelligence vertical.</p></article>)}</div>
    </div>
  );
}
