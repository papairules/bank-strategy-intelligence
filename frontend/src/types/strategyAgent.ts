export type StrategyAgentStatus = "answered" | "insufficient_evidence";
export type StrategySupportClass =
  | "source_evidence"
  | "ai_enrichment"
  | "derived_analytics"
  | "derived_signal";

export interface StrategyAgentAnswerRequest {
  organization: string;
  question: string;
  time_horizon?: string;
}

export interface StrategyEvidence {
  evidence_id: string;
  theme: string;
  business_unit: string | null;
  signal_type: "GROWTH" | "INVESTMENT" | "REVENUE_GROWTH" | "CAPITAL_ALLOCATION" | "NEW_PRODUCT" | "MARKET_EXPANSION" | "PARTNERSHIP" | "ACQUISITION" | "TECHNOLOGY_ADOPTION" | "TRANSFORMATION" | "COST_REDUCTION" | "REGULATORY_PRIORITY" | "GUIDANCE";
  direction: string | null;
  statement: string;
  time_horizon: string | null;
  source_id: string;
  source_url: string;
  source_type: string;
  publication_date: string | null;
}

export interface NativeStrategicSignal {
  priority: string;
  business_unit: string | null;
  direction: "grow" | "increase_investment" | "transform" | "optimize" | "reduce" | "exit" | "maintain" | "reallocate";
  time_horizon: string | null;
  hypothesis: string;
  supporting_evidence_ids: string[];
  confidence: number;
  confidence_breakdown: Record<string, number>;
  evidence: StrategyEvidence[];
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
  strategic_signals: NativeStrategicSignal[];
}
