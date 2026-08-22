import { useState } from "react";
import { hiringAgentApi } from "../../api/hiringAgent";
import { ApiError } from "../../api/hiring";
import type { HiringAgentAnswer, HiringAgentSignal } from "../../types/hiringAgent";
import { formatPercent, titleCase } from "../../utils/format";

export function HiringAgentPanel({ organization }: { organization: string }) {
  const [answer, setAnswer] = useState<HiringAgentAnswer | null>(null);
  const [error, setError] = useState<{ code?: string; message: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const run = async () => {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    setAnswer(null);
    try {
      setAnswer(await hiringAgentApi.answer({ organization }));
    } catch (caught) {
      setError(caught instanceof ApiError
        ? { code: caught.code, message: caught.message }
        : { message: "The Hiring Agent could not complete this analysis." });
    } finally {
      setSubmitting(false);
    }
  };

  return <section className="ask-strategy" aria-labelledby="hiring-agent-title">
    <div className="ask-strategy__intro">
      <div><span className="eyebrow">LLM-Assisted Hiring Agent</span><h2 id="hiring-agent-title">Classify Hiring Signals</h2></div>
      <p>Classifies persisted job postings into capability, business-unit, and seniority concentrations using an LLM-assisted pipeline. This is a separate agent-generated view from the deterministic hiring signals above—it does not confirm bank strategy or investment decisions.</p>
    </div>
    <div className="ask-strategy__form">
      <div><span>Organization: {organization}</span><button className="primary-button" type="button" onClick={run} disabled={submitting}>{submitting ? "Analyzing hiring data…" : "Run analysis"}</button></div>
    </div>
    {!answer && !error && !submitting && <div className="ask-strategy__idle">No Hiring Agent request is made until you explicitly run an analysis.</div>}
    {submitting && <div className="ask-strategy__state" role="status"><span className="spinner" /> Classifying persisted job postings…</div>}
    {error && <HiringAgentErrorState code={error.code} message={error.message} />}
    {answer && <HiringAgentResult answer={answer} />}
  </section>;
}

function HiringAgentErrorState({ code, message }: { code?: string; message: string }) {
  const title = code === "disabled_agent"
    ? "Hiring Agent unavailable"
    : code === "authentication"
      ? "Hiring Agent not configured"
      : "Hiring Agent analysis unavailable";
  return <div className="ask-strategy__error" role="alert"><strong>{title}</strong><p>{message}</p><small>No automatic retry was attempted.</small></div>;
}

function HiringAgentResult({ answer }: { answer: HiringAgentAnswer }) {
  return <div className="strategy-answer">
    <header><span className={`status-badge ${answer.status === "analyzed" ? "status-badge--enriched" : ""}`}>{titleCase(answer.status)}</span><span>{answer.unique_jobs} job{answer.unique_jobs === 1 ? "" : "s"} analyzed</span></header>
    {answer.status === "insufficient_data" && <div className="strategy-answer__insufficient"><strong>No persisted jobs are available for this organization yet.</strong><span>Run a hiring collection first, then re-run this analysis.</span></div>}
    {answer.hiring_signals.length > 0 && <section><span className="strategy-answer__label">Capability signals</span><div className="strategic-signals">{answer.hiring_signals.map((signal) => <HiringAgentSignalCard key={`${signal.capability}-${signal.business_unit ?? "none"}-${signal.department ?? "none"}`} signal={signal} />)}</div></section>}
    {answer.warnings.length > 0 && <section className="strategy-answer__limitations"><span className="strategy-answer__label">Limitations</span><ul>{answer.warnings.map((item) => <li key={item}>{item}</li>)}</ul></section>}
    <footer><span><strong>Provider</strong>{answer.provider}</span><span><strong>Model</strong>{answer.model}</span><span><strong>Agent version</strong>{answer.agent_version}</span></footer>
  </div>;
}

function HiringAgentSignalCard({ signal }: { signal: HiringAgentSignal }) {
  return <article>
    <header><span>{titleCase(signal.direction)}</span><strong>{formatPercent(signal.confidence * 100, 1)} confidence</strong></header>
    <h3>{signal.capability}</h3>
    <div className="strategic-signal__meta">
      {signal.business_unit && <span>{signal.business_unit}</span>}
      <span>{signal.job_count} job{signal.job_count === 1 ? "" : "s"}</span>
      {signal.senior_role_count > 0 && <span>{signal.senior_role_count} senior role{signal.senior_role_count === 1 ? "" : "s"}</span>}
    </div>
    {signal.related_technologies.length > 0 && <details><summary>{signal.related_technologies.length} related technolog{signal.related_technologies.length === 1 ? "y" : "ies"}</summary><p>{signal.related_technologies.join(", ")}</p></details>}
  </article>;
}
