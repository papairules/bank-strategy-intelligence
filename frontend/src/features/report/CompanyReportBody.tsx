import { FormEvent, useState } from "react";
import { supervisorReportApi } from "../../api/supervisorReport";
import { ApiError } from "../../api/hiring";
import { useSessionState } from "../../hooks/useSessionState";
import type { IntelligenceOutlookRow, ReportQuestionAnswer, ReportQuestionReference, ReportReference, SupervisorReportAnswer } from "../../types/supervisorReport";
import { titleCase } from "../../utils/format";

export function CompanyReportBody({ organization }: { organization: string }) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useSessionState<SupervisorReportAnswer | null>(`bsi:company-report:${organization}`, null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (loading) return;
    setLoading(true); setError(null); setResult(null);
    try {
      setResult(await supervisorReportApi.generate({
        organization,
        ...(question.trim() ? { question: question.trim() } : {}),
      }));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The company report could not be generated.");
    } finally {
      setLoading(false);
    }
  };

  return <>
    <section className="panel ask-strategy">
      <form className="ask-strategy__form" onSubmit={submit}>
        <label htmlFor="report-question">Report focus <span>(optional)</span></label>
        <textarea id="report-question" value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={2000} placeholder={`Generate a company intelligence report for ${organization}`} disabled={loading} />
        <div><span>The selected company remains authoritative.</span><button className="primary-button" disabled={loading}>{loading ? "Generating report…" : "Generate Report"}</button></div>
      </form>
      {!result && !error && !loading && <div className="ask-strategy__idle">No report request is made until you select Generate Report.</div>}
      {loading && <div className="ask-strategy__state" role="status"><span className="spinner" /> Combining governed intelligence…</div>}
      {error && <div className="ask-strategy__error" role="alert"><strong>Report unavailable</strong><p>{error}</p></div>}
    </section>
    {result && <Report answer={result} />}
  </>;
}

function Report({ answer }: { answer: SupervisorReportAnswer }) {
  return <article className="panel strategy-answer">
    <section><span className="strategy-answer__label">Executive Summary</span><p className="report-executive-summary">{answer.report.executive_summary}</p></section>
    <section>
      <p className="report-company-summary"><strong>{answer.report.organization}</strong><span aria-hidden="true"> · </span>{answer.report.total_hiring_jobs.toLocaleString()} Total Hiring Jobs</p>
      <span className="strategy-answer__label">Intelligence Outlook</span>
      {answer.report.intelligence_outlook_rows.length > 0 ? <div className="report-table-scroll"><table className="report-table report-table--outlook"><thead><tr><th>Opportunity</th><th>Relevant Hiring Jobs</th><th>30 Days</th><th>60 Days</th><th>90 Days</th><th>180 Days</th><th>360 Days</th></tr></thead><tbody>{answer.report.intelligence_outlook_rows.map((row) => <OutlookRow key={`${row.supervisor_priority}:${row.opportunity_theme}`} row={row} />)}</tbody></table></div> : <p className="report-empty">No supported intelligence outlook is available for this report.</p>}
    </section>
    <Sources references={answer.report.evidence_traceability} />
    <details className="report-methodology"><summary>Methodology &amp; Limitations</summary>{answer.report.limitations.length > 0 ? <ul>{answer.report.limitations.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No additional limitations were supplied.</p>}</details>
    <ReportQA report={answer} />
  </article>;
}

const suggestedQuestions = [
  "What are the top opportunities?",
  "Where should we focus first?",
  "Where do strategy and hiring align?",
  "What should we prioritize in the next 90 days?",
];

function ReportQA({ report }: { report: SupervisorReportAnswer }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useSessionState<ReportQuestionAnswer | null>(`bsi:company-report-qa:${report.report.organization}`, null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const ask = async (event?: FormEvent, suggested?: string) => {
    event?.preventDefault();
    const value = (suggested ?? question).trim();
    if (!value || loading) return;
    if (suggested) setQuestion(suggested);
    setLoading(true); setError(null); setAnswer(null);
    const cited = new Set(report.report.intelligence_outlook_rows.flatMap((row) => [
      ...row.supporting_evidence_ids, ...row.hiring_signal_ids, ...row.kg_concept_references,
    ]));
    for (const finding of [
      ...report.report.strategic_priorities,
      ...report.report.cross_domain_alignment,
    ]) {
      for (const referenceId of finding.supporting_reference_ids) cited.add(referenceId);
    }
    const references = report.report.evidence_traceability
      .filter((item) => item.source_url || cited.has(item.reference_id))
      .slice(0, 100);
    try {
      setAnswer(await supervisorReportApi.answer({
        organization: report.report.organization,
        question: value,
        report: {
          organization: report.report.organization,
          total_hiring_jobs: report.report.total_hiring_jobs,
          executive_summary: report.report.executive_summary,
          intelligence_outlook_rows: report.report.intelligence_outlook_rows,
          strategic_priorities: report.report.strategic_priorities.slice(0, 10),
          cross_domain_alignment: report.report.cross_domain_alignment.slice(0, 10),
          evidence_traceability: references,
          limitations: report.report.limitations.slice(0, 30),
        },
      }));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The report question could not be answered.");
    } finally {
      setLoading(false);
    }
  };

  return <section className="report-qa">
    <span className="strategy-answer__label">Ask about this report</span>
    <p className="report-qa__scope-note">Answers are limited to this generated report — no new research is performed.</p>
    <form className="report-qa__form" onSubmit={(event) => void ask(event)}>
      <label className="sr-only" htmlFor="report-follow-up">Ask a follow-up question about this report</label>
      <input id="report-follow-up" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Where do strategy and hiring align?" maxLength={1000} disabled={loading} />
      <button className="primary-button" disabled={loading || !question.trim()}>{loading ? "Asking…" : "Ask"}</button>
    </form>
    <div className="report-qa__suggestions">{suggestedQuestions.map((item) => <button type="button" key={item} disabled={loading} onClick={() => void ask(undefined, item)}>{item}</button>)}</div>
    {loading && <div className="report-qa__state" role="status"><span className="spinner" /> Reviewing report evidence…</div>}
    {error && <div className="ask-strategy__error" role="alert"><strong>Answer unavailable</strong><p>{error}</p></div>}
    {answer && <div className="report-qa__answer">
      {!answer.evidence_sufficient && <strong className="report-qa__insufficient">The current report does not contain enough evidence for a fully supported answer.</strong>}
      <p className="report-qa__answer-text">{answer.answer}</p>
      {answer.supporting_references.length > 0 && <SupportingReferences references={answer.supporting_references} />}
      {answer.limitations.length > 0 && <small>{answer.limitations.join(" ")}</small>}
    </div>}
  </section>;
}

function OutlookRow({ row }: { row: IntelligenceOutlookRow }) {
  return <tr>
    <td className="report-outlook-theme"><strong>{row.opportunity_theme}</strong></td>
    <td className="report-outlook-count">{row.relevant_hiring_jobs == null ? "—" : row.relevant_hiring_jobs.toLocaleString()}</td>
    <HorizonCell value={row.horizon_30} />
    <HorizonCell value={row.horizon_60} />
    <HorizonCell value={row.horizon_90} />
    <HorizonCell value={row.horizon_180} />
    <HorizonCell value={row.horizon_360} />
  </tr>;
}

function HorizonCell({ value }: { value?: string | null }) {
  const displayValue = value?.trim();
  return <td>{!displayValue || displayValue === "No action needed" ? "No action recommended" : displayValue}</td>;
}

function Sources({ references }: { references: ReportReference[] }) {
  const sources = deduplicateReferences(
    references.filter((reference) => reference.domain === "strategy" && reference.source_url?.trim()),
  );
  return sources.length > 0 ? <details className="report-sources"><summary>{sources.length} report source{sources.length === 1 ? "" : "s"}</summary><div className="report-reference-list">{sources.map((source) => <div className="report-reference" key={source.reference_id}>
    <span><strong>{source.source_url ? sourceName(source.source_url) : titleCase(source.domain)}</strong><small>{titleCase(source.domain)}{source.source_url ? ` · ${sourceName(source.source_url)}` : " · Internal evidence"}</small></span>
    {source.source_url && <a href={source.source_url} target="_blank" rel="noreferrer">Open source ↗</a>}
  </div>)}</div></details> : <p className="report-empty">No source references are available.</p>;
}

function SupportingReferences({ references }: { references: ReportQuestionReference[] }) {
  const distinctReferences = deduplicateQASupportingReferences(references);
  const groups = classifyQASupportingReferences(distinctReferences);
  return <details className="report-supporting-references"><summary>{distinctReferences.length} supporting reference{distinctReferences.length === 1 ? "" : "s"}</summary><div className="report-supporting-reference-groups">
    <ReferenceGroup heading="External Sources" references={groups.external} />
    <ReferenceGroup heading="Report Opportunities" references={groups.opportunities} />
    {groups.hiring.length > 0 && <AggregatedReferenceGroup heading="Internal Hiring Evidence" label="Hiring Intelligence" count={groups.hiring.length} />}
    {groups.report.length > 0 && <AggregatedReferenceGroup heading="Report Evidence" label="Strategy report evidence" count={groups.report.length} />}
    <ReferenceGroup heading="Other Supporting Evidence" references={groups.other} />
  </div></details>;
}

function ReferenceGroup({ heading, references }: { heading: string; references: ReportQuestionReference[] }) {
  if (references.length === 0) return null;
  return <section className="report-supporting-reference-group"><h3>{heading}</h3><div className="report-reference-list">{references.map((reference) => <div className="report-reference" key={reference.reference_id}>
    <span><strong>{displayReferenceLabel(reference)}</strong><small>{reference.source_url && isValidExternalUrl(reference.source_url) ? sourceName(reference.source_url) : reference.hiring_job_count != null ? `${reference.hiring_job_count.toLocaleString()} relevant jobs` : titleCase(reference.reference_type)}</small></span>
    {reference.source_url && isValidExternalUrl(reference.source_url) && <a href={reference.source_url} target="_blank" rel="noreferrer">Open source ↗</a>}
  </div>)}</div></section>;
}

function AggregatedReferenceGroup({ heading, label, count }: { heading: string; label: string; count: number }) {
  return <section className="report-supporting-reference-group"><h3>{heading}</h3><div className="report-reference report-reference--aggregate"><span><strong>{label}</strong><small>{count} supporting reference{count === 1 ? "" : "s"}</small></span></div></section>;
}

function deduplicateQASupportingReferences(references: ReportQuestionReference[]) {
  const seenIds = new Set<string>();
  const seenUrls = new Set<string>();
  return references.filter((reference) => {
    const url = reference.source_url?.trim();
    if (seenIds.has(reference.reference_id) || (url && isValidExternalUrl(url) && seenUrls.has(url))) return false;
    seenIds.add(reference.reference_id);
    if (url && isValidExternalUrl(url)) seenUrls.add(url);
    return true;
  });
}

function classifyQASupportingReferences(references: ReportQuestionReference[]) {
  const groups: Record<"external" | "opportunities" | "hiring" | "report" | "other", ReportQuestionReference[]> = {
    external: [], opportunities: [], hiring: [], report: [], other: [],
  };
  for (const reference of references) {
    const type = reference.reference_type.toLowerCase();
    const label = reference.label.toLowerCase();
    if (reference.source_url && isValidExternalUrl(reference.source_url)) groups.external.push(reference);
    else if (type.includes("opportunity")) groups.opportunities.push(reference);
    else if (type.includes("hiring") || label.includes("hiring intelligence")) groups.hiring.push(reference);
    else if (type.includes("strategy") || type.includes("report") || label === "strategy" || label.includes("report evidence")) groups.report.push(reference);
    else groups.other.push(reference);
  }
  return groups;
}

function deduplicateReferences<T extends { reference_id: string; source_url?: string | null }>(references: T[]): T[] {
  const seenIds = new Set<string>();
  const seenUrls = new Set<string>();
  return references.filter((reference) => {
    const url = reference.source_url?.trim();
    if (seenIds.has(reference.reference_id) || (url && seenUrls.has(url))) return false;
    seenIds.add(reference.reference_id);
    if (url) seenUrls.add(url);
    return true;
  });
}

function displayReferenceLabel(reference: ReportQuestionReference) {
  if (reference.label.trim() && !isInternalId(reference.label)) return reference.label;
  return titleCase(reference.reference_type);
}

function isInternalId(value: string) {
  const normalized = value.trim();
  return /^EV[_-]?\d+$/i.test(normalized)
    || /^[0-9a-f]{8}-[0-9a-f-]{27,}$/i.test(normalized)
    || /^(outlook|hiring|kg|strategy|report|evidence)[_:-][a-z0-9_:-]+$/i.test(normalized);
}

function sourceName(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "Strategy source";
  }
}

function isValidExternalUrl(url: string) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}
