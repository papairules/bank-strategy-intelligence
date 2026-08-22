export type HiringAgentStatus = "analyzed" | "insufficient_data";

export interface HiringAgentAnswerRequest {
  organization: string;
}

export interface HiringAgentSignal {
  company_id: string;
  business_unit: string | null;
  department: string | null;
  capability: string;
  direction: "concentration" | "growth" | "decline" | "stable" | "unknown";
  strength: number;
  job_count: number;
  previous_job_count: number | null;
  senior_role_count: number;
  related_skills: string[];
  related_technologies: string[];
  supporting_job_ids: string[];
  evidence_date: string;
  analysis_period: string;
  confidence: number;
  confidence_breakdown: Record<string, number>;
}

export interface HiringAgentEvidence {
  evidence_id: string;
  company_id: string;
  source_job_id: string;
  job_title: string;
  business_unit: string | null;
  capability: string;
  location: string | null;
  posting_date: string | null;
  source_url: string;
  statement: string;
}

export interface HiringAgentAnswer {
  status: HiringAgentStatus;
  organization: string;
  generated_at: string;
  total_input_jobs: number;
  unique_jobs: number;
  enriched_jobs: number;
  failed_enrichments: number;
  hiring_signals: HiringAgentSignal[];
  evidence: HiringAgentEvidence[];
  warnings: string[];
  provider: string;
  model: string;
  agent_version: string;
}
