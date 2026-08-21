export type EvidenceAgentStatus = "answered" | "insufficient_evidence";

export type EvidenceRelationshipType =
  | "source_evidence"
  | "hiring_enrichment"
  | "hiring_signal"
  | "technology_observation"
  | "technology_signal"
  | "cross_domain_signal";

export interface EvidenceAgentAnswerRequest {
  organization: string;
  question: string;
}

export interface EvidenceAgentCitation {
  evidence_id: string;
  job_id: string;
  relationship_type: EvidenceRelationshipType;
  source_type: string | null;
  excerpt: string | null;
}

export interface EvidenceAgentAnswer {
  status: EvidenceAgentStatus;
  organization: string;
  question: string;
  answer: string;
  citations: EvidenceAgentCitation[];
  evidence_records_considered: number;
  tool_calls_used: number;
  reliability: number;
  limitations: string[];
  provider: string;
  model: string;
  agent_version: string;
}
