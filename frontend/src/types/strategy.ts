export interface StrategicCoverageContext {
  total_jobs: number;
  jobs_with_evidence: number;
  hiring_evidence_coverage: number;
  enriched_jobs: number;
  enrichment_coverage: number;
  hiring_signal_count: number;
  technology_observation_count: number;
  technology_signal_count: number;
  observation_start: string | null;
  observation_end: string | null;
}

export interface CrossDomainStrategicSignal {
  signal_id: string;
  organization: string;
  signal_type: string;
  title: string;
  summary: string;
  primary_subject: string;
  related_subjects: string[];
  domains_involved: string[];
  observation_start: string;
  observation_end: string;
  strength: number;
  confidence: number;
  evidence_coverage: number;
  hiring_contributor_count: number;
  technology_contributor_count: number;
  unique_contributing_job_ids: string[];
  supporting_evidence_ids: string[];
  related_hiring_signal_ids: string[];
  related_technology_signal_ids: string[];
  limitations: string[];
  provenance: { generator: string; configuration_version: string; deterministic: boolean };
}

export interface StrategicSignalsResponse {
  organization: string;
  generated_at: string;
  generated_signal_count: number;
  coverage_context: StrategicCoverageContext;
  signals: CrossDomainStrategicSignal[];
  limitations: string[];
}
