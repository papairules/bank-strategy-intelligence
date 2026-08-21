import { useEffect } from "react";
import { hiringApi } from "../../api/hiring";
import { EmptyState, ErrorState, LoadingState } from "../../components/States";
import { useApi } from "../../hooks/useApi";
import { formatDate, formatPercent, titleCase } from "../../utils/format";

export function JobDetailPanel({ jobId, onClose }: { jobId: string; onClose: () => void }) {
  const { data, error, loading } = useApi(
    (signal) => hiringApi.jobDetail(jobId, signal),
    [jobId],
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
                <h3>Job information</h3>
                <dl className="detail-grid">
                  <div><dt>Organization</dt><dd>{data.job.organization}</dd></div>
                  <div><dt>Location</dt><dd>{data.job.location}</dd></div>
                  <div><dt>Posted</dt><dd>{formatDate(data.job.posted_date)}</dd></div>
                  <div><dt>Employment</dt><dd>{data.job.employment_type ? titleCase(data.job.employment_type) : "Not classified"}</dd></div>
                  <div><dt>Seniority</dt><dd>{data.job.seniority_level ? titleCase(data.job.seniority_level) : "Not classified"}</dd></div>
                  <div><dt>Source ID</dt><dd>{data.job.source_job_id}</dd></div>
                </dl>
                <p className="job-description">{data.job.description}</p>
              </section>

              <section className="detail-section">
                <div className="section-heading-inline"><h3>AI enrichment</h3>{data.enrichment && <span className="confidence-badge">{formatPercent(data.enrichment.confidence * 100)} confidence</span>}</div>
                {!data.enrichment ? (
                  <EmptyState message="AI enrichment not yet available" />
                ) : (
                  <div className="enrichment-content">
                    <DetailTags label="Capabilities" values={data.enrichment.capability_classifications} />
                    <DetailTags label="Hiring themes" values={data.enrichment.hiring_themes} />
                    <DetailTags label="Skills" values={data.enrichment.skills} />
                    <DetailTags label="Technologies" values={data.enrichment.technologies} />
                    <dl className="detail-grid detail-grid--compact">
                      <div><dt>Business unit</dt><dd>{data.enrichment.business_unit ?? "Not supported by evidence"}</dd></div>
                      <div><dt>Seniority</dt><dd>{titleCase(data.enrichment.seniority_level)}</dd></div>
                      <div><dt>Leadership</dt><dd>{data.enrichment.is_leadership ? "Yes" : "No"}</dd></div>
                      <div><dt>Model</dt><dd>{data.enrichment.model_metadata.model}</dd></div>
                      <div><dt>Provider</dt><dd>{titleCase(data.enrichment.model_metadata.provider)}</dd></div>
                      <div><dt>Schema</dt><dd>{data.enrichment.model_metadata.prompt_schema_version}</dd></div>
                    </dl>
                    {data.enrichment.limitations.length > 0 && <div className="limitations"><strong>Limitations</strong><ul>{data.enrichment.limitations.map((item) => <li key={item}>{item}</li>)}</ul></div>}
                  </div>
                )}
              </section>

              <section className="detail-section">
                <h3>Evidence</h3>
                <dl className="detail-grid detail-grid--compact">
                  <div><dt>Source</dt><dd>{titleCase(data.evidence.source_type)}</dd></div>
                  <div><dt>Retrieved</dt><dd>{formatDate(data.evidence.retrieved_at)}</dd></div>
                  <div><dt>Collector</dt><dd>{data.evidence.collector_identity}</dd></div>
                  <div><dt>Evidence ID</dt><dd className="mono">{data.evidence.evidence_id}</dd></div>
                </dl>
                {data.evidence.source_excerpt && <blockquote>{data.evidence.source_excerpt}</blockquote>}
                <a className="source-link" href={data.evidence.source_url} target="_blank" rel="noreferrer">View public source ↗</a>
              </section>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

function DetailTags({ label, values }: { label: string; values: string[] }) {
  if (!values.length) return null;
  return <div className="tag-group"><span>{label}</span><div>{values.map((value) => <span className="tag" key={value}>{value}</span>)}</div></div>;
}
