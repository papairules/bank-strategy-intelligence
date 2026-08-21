import { useEffect } from "react";
import { hiringApi } from "../../api/hiring";
import { EmptyState, ErrorState, LoadingState } from "../../components/States";
import { useApi } from "../../hooks/useApi";
import type { HiringEnrichment } from "../../types/hiring";
import { formatDate, formatPercent, titleCase } from "../../utils/format";

export function JobDetailPanel({ organization, jobId, onClose }: { organization: string; jobId: string; onClose: () => void }) {
  const { data, error, loading } = useApi(
    (signal) => hiringApi.jobDetail(organization, jobId, signal),
    [organization, jobId],
  );

  useEffect(() => {
    const listener = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [onClose]);

  return (
    <div className="drawer-backdrop" onMouseDown={onClose}>
      <aside className="job-drawer" role="dialog" aria-modal="true" aria-label="Job detail" onMouseDown={(event) => event.stopPropagation()}>
        <header className="drawer-header">
          <div><span className="eyebrow">Job intelligence record</span><h2>{data?.job.title ?? "Job detail"}</h2></div>
          <button className="icon-button" onClick={onClose} aria-label="Close job detail">×</button>
        </header>
        <div className="drawer-content">
          {loading && <LoadingState label="Loading job intelligence…" />}
          {error && <ErrorState message={error} />}
          {data && (
            <>
              <section className="detail-section">
                <SectionTitle title="Job information" origin="Source data" />
                <dl className="detail-grid">
                  <div><dt>Organization</dt><dd>{data.job.organization}</dd></div>
                  <div><dt>Location</dt><dd>{data.job.location}</dd></div>
                  <div><dt>Posted</dt><dd>{formatDate(data.job.posted_date)}</dd></div>
                  <div><dt>Employment</dt><dd>{data.job.employment_type ? titleCase(data.job.employment_type) : "Not classified"}</dd></div>
                  <div><dt>Normalized seniority</dt><dd>{data.job.seniority_level ? titleCase(data.job.seniority_level) : "Not classified"}</dd></div>
                  <div><dt>Source job ID</dt><dd>{data.job.source_job_id}</dd></div>
                </dl>
                <p className="job-description">{data.job.description}</p>
              </section>

              <section className="detail-section">
                <SectionTitle title="Source evidence" origin="Public career source" />
                <dl className="detail-grid detail-grid--compact">
                  <div><dt>Source type</dt><dd>{titleCase(data.evidence.source_type)}</dd></div>
                  <div><dt>Retrieved</dt><dd>{formatDate(data.evidence.retrieved_at)}</dd></div>
                  <div><dt>Collector</dt><dd>{data.evidence.collector_identity}</dd></div>
                  <div><dt>Evidence ID</dt><dd className="mono">{data.evidence.evidence_id}</dd></div>
                </dl>
                {data.evidence.source_excerpt && <blockquote>{data.evidence.source_excerpt}</blockquote>}
                <a className="source-link" href={data.evidence.source_url} target="_blank" rel="noreferrer">View public source ↗</a>
              </section>

              <section className="detail-section detail-section--ai">
                <div className="section-heading-inline"><SectionTitle title="AI enrichment" origin="Gemini-classified" />{data.enrichment && <span className="confidence-badge">{formatPercent(data.enrichment.confidence * 100)} confidence</span>}</div>
                {!data.enrichment ? (
                  <EmptyState message="AI enrichment not yet available" />
                ) : (
                  <div className="enrichment-content">
                    <p className="origin-explainer">Model-assisted classifications grounded in the source evidence above. They do not replace the normalized source record.</p>
                    <DetailTags label="Capabilities" values={data.enrichment.capability_classifications} />
                    <DetailTags label="Hiring themes" values={data.enrichment.hiring_themes} />
                    <DetailTags label="Skills" values={data.enrichment.skills} />
                    <DetailTags label="Technologies" values={data.enrichment.technologies} />
                    <dl className="detail-grid detail-grid--compact">
                      <div><dt>Business unit</dt><dd>{data.enrichment.business_unit ?? "Not supported by evidence"}</dd></div>
                      <div><dt>Seniority</dt><dd>{titleCase(data.enrichment.seniority_level)}</dd></div>
                      <div><dt>Leadership</dt><dd>{data.enrichment.is_leadership ? "Yes" : "No"}</dd></div>
                    </dl>
                  </div>
                )}
              </section>

              {data.enrichment && <EnrichmentQuality enrichment={data.enrichment} />}
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

function EnrichmentQuality({ enrichment }: { enrichment: HiringEnrichment }) {
  return <>
    <section className="detail-section">
      <SectionTitle title="Enrichment quality" origin="Application validated" />
      <dl className="detail-grid detail-grid--compact">
        <div><dt>Application confidence</dt><dd>{formatPercent(enrichment.confidence * 100)}</dd></div>
        <div><dt>Model confidence</dt><dd>{formatPercent(enrichment.model_metadata.model_confidence * 100)}</dd></div>
        <div><dt>Provider</dt><dd>{titleCase(enrichment.model_metadata.provider)}</dd></div>
        <div><dt>Model</dt><dd>{enrichment.model_metadata.model}</dd></div>
        <div><dt>Schema version</dt><dd>{enrichment.model_metadata.prompt_schema_version}</dd></div>
        <div><dt>Generated</dt><dd>{formatDate(enrichment.model_metadata.enrichment_timestamp)}</dd></div>
      </dl>
      {Object.keys(enrichment.field_confidences).length > 0 && <div className="field-confidence"><strong>Field confidence</strong>{Object.entries(enrichment.field_confidences).map(([field, confidence]) => <span key={field}>{titleCase(field)} <b>{formatPercent(confidence * 100)}</b></span>)}</div>}
      {enrichment.limitations.length > 0 && <div className="limitations"><strong>Limitations</strong><ul>{enrichment.limitations.map((item) => <li key={item}>{item}</li>)}</ul></div>}
    </section>
    <section className="detail-section">
      <SectionTitle title="Traceability" origin="Evidence references" />
      <p className="traceability-copy">All persisted support references resolve to evidence <span className="mono">{enrichment.evidence_id}</span>.</p>
      {enrichment.field_support.length ? <div className="support-list">{enrichment.field_support.map((support) => <div key={`${support.field}-${support.value}`}><strong>{support.value}</strong><span>{titleCase(support.field)}</span><q>{support.excerpt}</q></div>)}</div> : <div className="inline-empty">No field-level support excerpts are persisted for this enrichment.</div>}
    </section>
  </>;
}

function SectionTitle({ title, origin }: { title: string; origin: string }) {
  return <div className="section-title"><h3>{title}</h3><span>{origin}</span></div>;
}

function DetailTags({ label, values }: { label: string; values: string[] }) {
  if (!values.length) return null;
  return <div className="tag-group"><span>{label}</span><div>{values.map((value) => <span className="tag" key={value}>{value}</span>)}</div></div>;
}
