import { FormEvent, useState } from "react";
import { evidenceAgentApi } from "../../api/evidenceAgent";
import { ApiError } from "../../api/hiring";
import type { EvidenceAgentAnswer, EvidenceAgentCitation } from "../../types/evidenceAgent";
import { formatPercent, titleCase } from "../../utils/format";

interface Props { organization: string; onViewEvidence: (evidenceId: string) => void; }

export function AskEvidencePanel({ organization, onViewEvidence }: Props) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<EvidenceAgentAnswer | null>(null);
  const [error, setError] = useState<{ code?: string; message: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const normalized = question.trim();
    if (!normalized || submitting) return;
    setSubmitting(true); setError(null); setAnswer(null);
    try { setAnswer(await evidenceAgentApi.answer({ organization, question: normalized })); }
    catch (caught) { setError(caught instanceof ApiError ? { code: caught.code, message: caught.message } : { message: "The Evidence Agent could not complete this request." }); }
    finally { setSubmitting(false); }
  };
  return <section className="ask-evidence" aria-labelledby="ask-evidence-title">
    <div className="ask-evidence__intro"><div><span className="eyebrow">Governed Evidence Agent</span><h2 id="ask-evidence-title">Ask Evidence</h2></div><p>Answers are grounded in available evidence and may be limited by evidence coverage. Reliability is an evidence-support indicator, not a probability of factual certainty.</p></div>
    <form className="ask-evidence__form" onSubmit={submit}><label htmlFor="evidence-question">Question</label><textarea id="evidence-question" value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={2000} placeholder="Ask a question grounded in available evidence…" disabled={submitting} /><div><span>{question.length}/2000</span><button className="primary-button" type="submit" disabled={submitting || !question.trim()}>{submitting ? "Analyzing evidence…" : "Ask Evidence"}</button></div></form>
    {!answer && !error && !submitting && <div className="ask-evidence__idle">No agent request is made until you submit a question.</div>}
    {submitting && <div className="ask-evidence__state" role="status"><span className="spinner" /> Reviewing approved evidence sources…</div>}
    {error && <AgentError code={error.code} message={error.message} />}
    {answer && <AgentAnswer answer={answer} onViewEvidence={onViewEvidence} />}
  </section>;
}

function AgentError({ code, message }: { code?: string; message: string }) {
  const title = code === "disabled_agent" ? "Evidence Agent unavailable" : ["provider_unavailable", "timeout", "quota"].includes(code ?? "") ? "Provider temporarily unavailable" : "Grounded answer unavailable";
  return <div className="ask-evidence__error" role="alert"><strong>{title}</strong><p>{message}</p><small>No automatic retry was attempted.</small></div>;
}

function AgentAnswer({ answer, onViewEvidence }: { answer: EvidenceAgentAnswer; onViewEvidence: (evidenceId: string) => void }) {
  return <div className="agent-answer"><header><span className={`status-badge ${answer.status === "answered" ? "status-badge--enriched" : ""}`}>{titleCase(answer.status)}</span><span>{answer.evidence_records_considered} evidence record{answer.evidence_records_considered === 1 ? "" : "s"} considered</span></header><section><span className="agent-answer__label">Answer</span><p>{answer.answer}</p></section>{answer.status === "insufficient_evidence" && <div className="agent-answer__insufficient">Available evidence does not support a broader answer. No unsupported conclusion was generated.</div>}<div className="agent-answer__quality"><div><span>Reliability</span><strong>{formatPercent(answer.reliability * 100, 1)}</strong><small>Evidence-support indicator</small></div><div><span>Governance</span><strong>{answer.tool_calls_used} approved tool call{answer.tool_calls_used === 1 ? "" : "s"}</strong><small>Read-only evidence operations</small></div></div><section><span className="agent-answer__label">Evidence used</span>{answer.citations.length ? <div className="agent-citations">{answer.citations.map((citation, index) => <CitationCard key={`${citation.evidence_id}-${citation.relationship_type}`} citation={citation} index={index} onViewEvidence={onViewEvidence} />)}</div> : <p className="agent-answer__empty">No citation met the governed evidence requirements.</p>}</section>{answer.limitations.length > 0 && <section className="agent-answer__limitations"><span className="agent-answer__label">Limitations</span><ul>{answer.limitations.map((item) => <li key={item}>{item}</li>)}</ul></section>}<footer><span><strong>Provider</strong>{answer.provider}</span><span><strong>Model</strong>{answer.model}</span><span><strong>Agent version</strong>{answer.agent_version}</span></footer></div>;
}

function CitationCard({ citation, index, onViewEvidence }: { citation: EvidenceAgentCitation; index: number; onViewEvidence: (evidenceId: string) => void }) {
  const classification = relationshipClassification(citation.relationship_type);
  return <article className="agent-citation"><div><span>Citation {index + 1}</span><strong>{classification.label}</strong></div><dl><div><dt>Evidence</dt><dd className="mono">{citation.evidence_id}</dd></div><div><dt>Job</dt><dd className="mono">{citation.job_id}</dd></div><div><dt>Relationship</dt><dd>{titleCase(citation.relationship_type)}</dd></div><div><dt>Source type</dt><dd>{citation.source_type ? titleCase(citation.source_type) : "Not supplied"}</dd></div></dl><p className="agent-citation__classification"><strong>{classification.label}:</strong> {classification.description}</p>{citation.excerpt && <blockquote>{citation.excerpt}</blockquote>}<button className="row-action" onClick={() => onViewEvidence(citation.evidence_id)}>View Evidence</button></article>;
}

function relationshipClassification(relationship: EvidenceAgentCitation["relationship_type"]) {
  if (relationship === "source_evidence") return { label: "Source evidence", description: "Directly captured from the authoritative source." };
  if (relationship === "hiring_enrichment") return { label: "AI enrichment", description: "Model-derived classification grounded in source evidence; not an original source field." };
  return { label: "Derived intelligence", description: "Deterministic intelligence derived by the application from linked evidence." };
}
