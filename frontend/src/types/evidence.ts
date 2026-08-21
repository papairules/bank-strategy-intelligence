export interface EvidenceSignalReference {
  signal_id: string;
  signal_type: string;
  title: string;
}

export interface UnifiedEvidenceRecord {
  evidence_id: string;
  organization: string;
  source: string;
  source_type: string;
  source_url: string;
  captured_at: string;
  observed_at: string;
  job_id: string;
  job_title: string;
  job_location: string;
  business_unit: string | null;
  enrichment_present: boolean;
  enrichment_provider: string | null;
  enrichment_model: string | null;
  enrichment_schema_version: string | null;
  application_confidence: number | null;
  technologies: string[];
  capabilities: string[];
  skills: string[];
  seniority: string | null;
  related_hiring_signals: EvidenceSignalReference[];
  related_technology_observation_count: number;
  related_technology_signals: EvidenceSignalReference[];
  evidence_preview: string | null;
}

export interface UnifiedEvidenceDetail extends UnifiedEvidenceRecord {
  source_excerpt: string | null;
  raw_reference: string | null;
  collector_identity: string;
  provenance_metadata: Record<string, unknown>;
  enrichment_limitations: string[];
  technology_observations: {
    technology: string;
    category: string;
    confidence: number;
    support_excerpt: string | null;
  }[];
}

export interface EvidenceSummary {
  organization: string;
  total_evidence_records: number;
  total_jobs: number;
  jobs_with_evidence: number;
  evidence_coverage: number;
  enriched_evidence_count: number;
  enrichment_coverage: number;
  evidence_supporting_hiring_signals: number;
  evidence_supporting_technology_observations: number;
  evidence_supporting_technology_signals: number;
  source_distribution: { source: string; source_type: string; evidence_count: number }[];
  observation_start: string | null;
  observation_end: string | null;
  generated_at: string;
}

export interface EvidenceRecordFilters {
  search?: string;
  source?: string;
  enriched?: boolean;
  technology?: string;
  capability?: string;
  location?: string;
  limit: number;
  offset: number;
}

export interface EvidenceRecordsResponse {
  items: UnifiedEvidenceRecord[];
  total: number;
  limit: number;
  offset: number;
  returned_count: number;
}
