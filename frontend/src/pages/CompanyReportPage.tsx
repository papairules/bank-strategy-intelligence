import { FormEvent, useState } from "react";
import { supervisorReportApi } from "../api/supervisorReport";
import { ApiError } from "../api/hiring";
import { useOrganization } from "../context/OrganizationContext";
import type { IntelligenceOutlookRow, ReportQuestionAnswer, ReportReference, SupervisorReportAnswer } from "../types/supervisorReport";

export function CompanyReportPage() {
  const { organization } = useOrganization();
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<SupervisorReportAnswer | null>(null);
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

  return <div className="page">
    <div className="page-heading"><div><span className="eyebrow">Combined intelligence</span><h1>Company Report</h1><p>Evidence-aware Strategy, Hiring, and Hiring KG synthesis for {organization}.</p></div></div>
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
  </div>;
}

function Report({ answer }: { answer: SupervisorReportAnswer }) {
  return <article className="panel strategy-answer">
    <section><span className="strategy-answer__label">Executive Summary</span><p>{answer.report.executive_summary}</p></section>
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
  const [answer, setAnswer] = useState<ReportQuestionAnswer | null>(null);
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
      <p>{answer.answer}</p>
      {answer.supporting_references.length > 0 && <div><span className="strategy-answer__label">Sources / Evidence</span><ul>{answer.supporting_references.map((item) => <li key={item.reference_id}>{item.source_url ? <a href={item.source_url} target="_blank" rel="noreferrer">{sourceName(item.source_url)}</a> : item.label}{item.hiring_job_count != null ? ` · ${item.hiring_job_count.toLocaleString()} relevant jobs` : ""}</li>)}</ul></div>}
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
  return <td>{value?.trim() || "No action needed"}</td>;
}

function Sources({ references }: { references: ReportReference[] }) {
  const [expanded, setExpanded] = useState(false);
  const webSources = Array.from(new Map(references.filter((item) => item.source_url).map((item) => [item.source_url, item])).values());
  const sources = [...webSources, { reference_id: "hiring-dataset", domain: "hiring", evidence_ids: [], job_ids: [], source_url: null }];
  const visible = expanded ? sources : sources.slice(0, 3);
  return <section><span className="strategy-answer__label">Sources</span>{visible.length > 0 ? <><div className="report-table-scroll"><table className="report-table report-table--sources"><thead><tr><th>Source</th><th>Used For</th></tr></thead><tbody>{visible.map((source) => <tr key={source.source_url ?? source.reference_id}><td>{source.source_url ? <a href={source.source_url} target="_blank" rel="noreferrer">{sourceName(source.source_url)}</a> : "Hiring dataset"}</td><td>{source.domain === "hiring" ? "Hiring intelligence" : "Strategy evidence"}</td></tr>)}</tbody></table></div>{sources.length > 3 && <button className="report-sources-toggle" type="button" onClick={() => setExpanded((value) => !value)}>{expanded ? "Show less" : `Show all sources (${sources.length})`}</button>}</> : <p className="report-empty">No source references are available.</p>}</section>;
}

function sourceName(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "Strategy source";
  }
}
