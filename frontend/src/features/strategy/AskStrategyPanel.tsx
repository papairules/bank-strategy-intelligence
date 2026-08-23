import { FormEvent, useState } from "react";
import { strategyAgentApi } from "../../api/strategyAgent";
import { ApiError } from "../../api/hiring";
import { useSessionState } from "../../hooks/useSessionState";
import type { StrategyAgentAnswer, StrategyEvidence } from "../../types/strategyAgent";
import { titleCase } from "../../utils/format";

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
      <p>Ask about strategic priorities, technology direction, business initiatives, or recent developments. Results are grounded in cited external evidence and governed application validation.</p>
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
    <section><span className="strategy-answer__label">Strategy analysis</span><p>{answer.executive_summary}</p></section>
    {answer.status === "insufficient_evidence" && <div className="strategy-answer__insufficient"><strong>Available evidence is insufficient to support a reliable organization-wide strategic conclusion.</strong><span>The governed result has withheld unsupported findings.</span></div>}
    {answer.strategic_signals.length > 0 && <section><span className="strategy-answer__label">Strategic themes</span><div className="strategic-signals">{answer.strategic_signals.map((signal) => <article key={`${signal.priority}-${signal.direction}`}>
      <h3>{signal.priority}</h3><p>{signal.hypothesis}</p>
      {signal.time_horizon && <div className="strategic-signal__meta"><span>{signal.time_horizon}</span></div>}
      <ThemeSources evidence={signal.evidence} />
    </article>)}</div></section>}
  </div>;
}

function ThemeSources({ evidence }: { evidence: StrategyEvidence[] }) {
  const sources = Array.from(new Map(
    evidence.filter((item) => item.source_url.trim()).map((item) => [item.source_url, item]),
  ).values());
  if (sources.length === 0) return <p className="strategic-sources-empty">No external sources available.</p>;

  return <details className="strategic-theme-sources">
    <summary>{sources.length} source{sources.length === 1 ? "" : "s"}</summary>
    <div>{sources.map((source) => <div className="strategic-source" key={source.source_url}>
      <span><strong>{source.theme || titleCase(source.source_type)}</strong><small>{titleCase(source.source_type)}{source.publication_date ? ` · ${source.publication_date}` : ""}</small></span>
      <a href={source.source_url} target="_blank" rel="noreferrer">Open source ↗</a>
    </div>)}</div>
  </details>;
}
