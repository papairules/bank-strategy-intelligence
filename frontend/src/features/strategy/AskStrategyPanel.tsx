import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { strategyAgentApi } from "../../api/strategyAgent";
import { ApiError } from "../../api/hiring";
import { useSessionState } from "../../hooks/useSessionState";
import type { StrategyAgentAnswer, StrategySupportClass } from "../../types/strategyAgent";
import { formatPercent, titleCase } from "../../utils/format";

export function AskStrategyPanel({ organization }: { organization: string }) {
  const [question, setQuestion] = useState("");
  const [timeHorizon, setTimeHorizon] = useState("");
  const [answer, setAnswer] = useSessionState<StrategyAgentAnswer | null>(`bsi:strategy-agent:${organization}`, null);
  const [error, setError] = useState<{ code?: string; message: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const normalized = question.trim();
    if (!normalized || submitting) return;
    setSubmitting(true);
    setError(null);
    setAnswer(null);
    try {
      setAnswer(await strategyAgentApi.answer({
        organization,
        question: normalized,
        ...(timeHorizon.trim() ? { time_horizon: timeHorizon.trim() } : {}),
      }));
    } catch (caught) {
      setError(caught instanceof ApiError
        ? { code: caught.code, message: caught.message }
        : { message: "The Strategy Agent could not complete this request." });
    } finally {
      setSubmitting(false);
    }
  };

  return <section className="ask-strategy" aria-labelledby="ask-strategy-title">
    <div className="ask-strategy__intro">
      <div><span className="eyebrow">Governed Strategy Agent</span><h2 id="ask-strategy-title">Ask Strategy</h2></div>
      <p>AI-assisted synthesis constrained by available evidence and governed application validation. It does not replace deterministic strategic signals or establish corporate intent.</p>
    </div>
    <form className="ask-strategy__form" onSubmit={submit}>
      <label htmlFor="strategy-question">Strategic question</label>
      <textarea id="strategy-question" value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={2000} placeholder="Ask an evidence-grounded strategic question…" disabled={submitting} />
      <label htmlFor="strategy-time-horizon">Time horizon <span>(optional)</span></label>
      <input id="strategy-time-horizon" value={timeHorizon} onChange={(event) => setTimeHorizon(event.target.value)} maxLength={100} placeholder="e.g. 2025–2027" disabled={submitting} />
      <div><span>{question.length}/2000</span><button className="primary-button" type="submit" disabled={submitting || !question.trim()}>{submitting ? "Analyzing intelligence…" : "Analyze"}</button></div>
    </form>
    {!answer && !error && !submitting && <div className="ask-strategy__idle">No Strategy Agent request is made until you explicitly submit a question.</div>}
    {submitting && <div className="ask-strategy__state" role="status"><span className="spinner" /> Reviewing approved intelligence sources…</div>}
    {error && <StrategyError code={error.code} message={error.message} />}
    {answer && <StrategyAnswer answer={answer} />}
  </section>;
}

function StrategyError({ code, message }: { code?: string; message: string }) {
  const title = code === "organization_scope_mismatch"
    ? "Organization scope mismatch"
    : code === "disabled_agent"
      ? "Strategy Agent unavailable"
    : ["provider_unavailable", "timeout", "quota"].includes(code ?? "")
      ? "Provider temporarily unavailable"
      : "Governed synthesis unavailable";
  return <div className="ask-strategy__error" role="alert"><strong>{title}</strong><p>{message}</p><small>No automatic retry was attempted.</small></div>;
}

function StrategyAnswer({ answer }: { answer: StrategyAgentAnswer }) {
  return <div className="strategy-answer">
    <header><span className={`status-badge ${answer.status === "answered" ? "status-badge--enriched" : ""}`}>{titleCase(answer.status)}</span><span>{answer.tool_calls_used} approved intelligence tool call{answer.tool_calls_used === 1 ? "" : "s"}</span></header>
    <section><span className="strategy-answer__label">Executive assessment</span><p>{answer.executive_summary}</p></section>
    {answer.status === "insufficient_evidence" && <div className="strategy-answer__insufficient"><strong>Available evidence is insufficient to support a reliable organization-wide strategic conclusion.</strong><span>The governed result has withheld unsupported findings.</span></div>}
    {answer.strategic_signals.length > 0 && <section><span className="strategy-answer__label">Strategic signals</span><div className="strategic-signals">{answer.strategic_signals.map((signal) => <article key={`${signal.priority}-${signal.direction}`}>
      <header><span>{titleCase(signal.direction)}</span><strong>{formatPercent(signal.confidence * 100, 1)} confidence</strong></header>
      <h3>{signal.priority}</h3><p>{signal.hypothesis}</p>
      <div className="strategic-signal__meta">{signal.business_unit && <span>{signal.business_unit}</span>}{signal.time_horizon && <span>{signal.time_horizon}</span>}</div>
      {signal.evidence.length > 0 && <details><summary>{signal.evidence.length} supporting evidence item{signal.evidence.length === 1 ? "" : "s"}</summary>{signal.evidence.map((evidence) => <div className="strategic-evidence" key={evidence.evidence_id}><p>{evidence.statement}</p><small>{titleCase(evidence.source_type)}{evidence.publication_date ? ` · ${evidence.publication_date}` : ""} · Evidence {evidence.evidence_id}</small><a href={evidence.source_url} target="_blank" rel="noreferrer">Open source</a></div>)}</details>}
    </article>)}</div></section>}
    {answer.findings.length > 0 && <section><span className="strategy-answer__label">Findings</span><div className="strategy-findings">{answer.findings.map((finding) => <article key={finding.title}><h3>{finding.title}</h3><p>{finding.statement}</p><div className="strategy-support">{finding.support.map((support) => <div key={support.reference}><span>{supportLabel(support.support_class)}</span><small>{titleCase(support.domain)} · validated application reference</small>{support.evidence_ids.length > 0 && <Link to="/evidence">View supporting evidence</Link>}</div>)}</div></article>)}</div></section>}
    <div className="strategy-answer__quality"><div><span>Evidence-support reliability</span><strong>{formatPercent(answer.reliability * 100, 1)}</strong><small>This is an evidence-support indicator, not a probability.</small></div><div><span>Governance</span><strong>Application validated</strong><small>References, provenance, scope, and reliability are server controlled.</small></div></div>
    {answer.limitations.length > 0 && <section className="strategy-answer__limitations"><span className="strategy-answer__label">Limitations</span><ul>{answer.limitations.map((item) => <li key={item}>{item}</li>)}</ul></section>}
    <footer><span><strong>Provider</strong>{answer.provider}</span><span><strong>Model</strong>{answer.model}</span><span><strong>Agent version</strong>{answer.agent_version}</span></footer>
  </div>;
}

function supportLabel(supportClass: StrategySupportClass) {
  return {
    source_evidence: "Source Evidence",
    ai_enrichment: "AI Enrichment",
    derived_analytics: "Derived Analytics",
    derived_signal: "Derived Signal",
  }[supportClass];
}
