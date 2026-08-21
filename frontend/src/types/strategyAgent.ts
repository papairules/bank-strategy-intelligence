export type StrategyAgentStatus = "answered" | "insufficient_evidence";
export type StrategySupportClass =
  | "source_evidence"
  | "ai_enrichment"
  | "derived_analytics"
  | "derived_signal";

export interface StrategyAgentAnswerRequest {
  organization: string;
  question: string;
}

export interface StrategySupportReference {
  reference: string;
  domain: string;
  support_class: StrategySupportClass;
  tool_name: string;
  evidence_ids: string[];
  job_ids: string[];
  signal_ids: string[];
}

export interface StrategyFinding {
  title: string;
  statement: string;
  support: StrategySupportReference[];
}

export interface StrategyAgentAnswer {
  status: StrategyAgentStatus;
  organization: string;
  question: string;
  executive_summary: string;
  findings: StrategyFinding[];
  reliability: number;
  limitations: string[];
  tool_calls_used: number;
  provider: string;
  model: string;
  agent_version: string;
}
