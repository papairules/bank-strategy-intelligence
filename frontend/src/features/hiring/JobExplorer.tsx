import { type FormEvent, useState } from "react";
import { hiringApi } from "../../api/hiring";
import { EmptyState, ErrorState, LoadingState } from "../../components/States";
import { useApi } from "../../hooks/useApi";
import type { JobFilters, SeniorityLevel } from "../../types/hiring";
import { formatDate, titleCase } from "../../utils/format";
import { JobDetailPanel } from "./JobDetailPanel";

const PAGE_SIZE = 10;
const initialFilters: JobFilters = { limit: PAGE_SIZE, offset: 0 };

export function JobExplorer({ organization }: { organization: string }) {
  const [filters, setFilters] = useState<JobFilters>(initialFilters);
  const [draft, setDraft] = useState({ location: "", capability: "", seniority: "" });
  const [selectedJob, setSelectedJob] = useState<string | null>(null);
  const { data, error, loading } = useApi(
    (signal) => hiringApi.jobs(organization, filters, signal),
    [organization, filters.location, filters.capability, filters.seniority, filters.offset],
  );

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    setFilters({
      ...initialFilters,
      location: draft.location.trim() || undefined,
      capability: draft.capability.trim() || undefined,
      seniority: draft.seniority as SeniorityLevel | "",
    });
  }

  return (
    <section className="panel jobs-panel" id="jobs">
      <header className="panel__header jobs-header">
        <div><div className="eyebrow">Normalized job records</div><h2>Job explorer</h2></div>
        <span className="result-count">{data ? `${data.total} observed roles` : ""}</span>
      </header>
      <form className="filters" onSubmit={applyFilters}>
        <label><span>Location</span><input value={draft.location} onChange={(event) => setDraft({ ...draft, location: event.target.value })} placeholder="e.g. Charlotte" /></label>
        <label><span>Capability</span><input value={draft.capability} onChange={(event) => setDraft({ ...draft, capability: event.target.value })} placeholder="e.g. Data & Analytics" /></label>
        <label><span>Seniority</span><select value={draft.seniority} onChange={(event) => setDraft({ ...draft, seniority: event.target.value })}><option value="">All levels</option>{["entry", "mid", "senior", "manager", "director", "executive"].map((level) => <option key={level} value={level}>{titleCase(level)}</option>)}</select></label>
        <button className="primary-button" type="submit">Apply filters</button>
      </form>
      {loading && <LoadingState label="Loading observed jobs…" />}
      {error && <ErrorState message={error} />}
      {data && data.items.length === 0 && <EmptyState message="No hiring observations match the selected filters." />}
      {data && data.items.length > 0 && (
        <>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Role</th><th>Location</th><th>Posted</th><th>Capability</th><th>Seniority</th><th /></tr></thead>
              <tbody>{data.items.map((job) => (
                <tr key={job.job_id}>
                  <td><button className="job-title-button" onClick={() => setSelectedJob(job.job_id)}>{job.title}</button><span className="table-subtext">{job.source_job_id}</span></td>
                  <td>{job.location}</td><td>{formatDate(job.posted_date)}</td>
                  <td>{job.capability_classifications[0] ?? <span className="muted">Unclassified</span>}</td>
                  <td>{job.seniority_level ? titleCase(job.seniority_level) : <span className="muted">Unclassified</span>}</td>
                  <td><button className="row-action" onClick={() => setSelectedJob(job.job_id)} aria-label={`View ${job.title}`}>View</button></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <div className="pagination">
            <span>Showing {data.offset + 1}–{Math.min(data.offset + data.returned_count, data.total)} of {data.total}</span>
            <div><button disabled={filters.offset === 0} onClick={() => setFilters({ ...filters, offset: Math.max(0, filters.offset - PAGE_SIZE) })}>Previous</button><button disabled={filters.offset + data.returned_count >= data.total} onClick={() => setFilters({ ...filters, offset: filters.offset + PAGE_SIZE })}>Next</button></div>
          </div>
        </>
      )}
      {selectedJob && <JobDetailPanel organization={organization} jobId={selectedJob} onClose={() => setSelectedJob(null)} />}
    </section>
  );
}
