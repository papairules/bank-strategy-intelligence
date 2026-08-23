export type TechnologyCategory =
  | "Programming Language"
  | "Database"
  | "Data Platform"
  | "Cloud Platform"
  | "BI / Visualization"
  | "Analytics / Statistical Tool"
  | "Data Engineering"
  | "AI / ML"
  | "DevOps / Infrastructure"
  | "Enterprise Platform"
  | "Other";

export interface TechnologyRecordReference {
  job_id: string;
  evidence_id: string;
}

export interface TechnologySnapshot {
  organization: string;
  total_jobs: number;
  enriched_jobs: number;
  technology_observation_count: number;
  unique_technologies: number;
  technology_coverage_percentage: number;
  jobs_with_technology_signal: number;
  technology_signal_coverage_percentage: number;
  observation_start: string | null;
  observation_end: string | null;
  generated_at: string;
}

export interface TechnologyObservation {
  technology: string;
  normalized_technology: string;
  category: TechnologyCategory;
  organization: string;
  job_id: string;
  job_title: string;
  evidence_id: string;
  source_type: string;
  observation_date: string;
  location: string;
  business_unit: string | null;
  seniority: string;
  confidence: number;
  provenance: {
    provider: string;
    model: string;
    prompt_schema_version: string;
    enrichment_timestamp: string;
  };
  support_references: { evidence_id: string; excerpt: string | null }[];
}

export interface TopTechnology {
  technology: string;
  category: TechnologyCategory;
  job_count: number;
  observation_count: number;
  percentage_of_enriched_jobs: number;
  percentage_of_technology_classified_jobs: number;
  evidence_count: number;
  contributing_records: TechnologyRecordReference[];
}

export interface TechnologyCategoryAggregate {
  category: TechnologyCategory;
  unique_technology_count: number;
  observation_count: number;
  job_count: number;
  contributing_records: TechnologyRecordReference[];
}

export interface TechnologyAnalytics {
  snapshot: TechnologySnapshot;
  top_technologies: TopTechnology[];
  categories: TechnologyCategoryAggregate[];
  business_unit_technologies: { business_unit: string; technology: string; job_count: number; contributing_records: TechnologyRecordReference[] }[];
  geography_technologies: { location: string; technology: string; job_count: number; contributing_records: TechnologyRecordReference[] }[];
  seniority_technologies: { seniority: string; technology: string; job_count: number; contributing_records: TechnologyRecordReference[] }[];
}

export interface TechnologySummary {
  snapshot: TechnologySnapshot;
  coverage_limitation: string | null;
}

export interface TechnologyObservationList {
  items: TechnologyObservation[];
  total: number;
  limit: number;
  offset: number;
  returned_count: number;
}

export interface TechnologySignal {
  signal_id: string;
  organization: string;
  signal_type: string;
  title: string;
  summary: string;
  subject: string;
  observation_start: string;
  observation_end: string;
  confidence: number;
  strength: number;
  evidence_coverage: number;
  supporting_job_ids: string[];
  supporting_evidence_ids: string[];
  limitations: string[];
  provenance: {
    generator: string;
    configuration_version: string;
    deterministic: boolean;
  };
}

export interface TechnologySignalsResponse {
  organization: string;
  generated_at: string;
  total_jobs: number;
  enriched_jobs: number;
  enrichment_coverage: number;
  technology_observation_count: number;
  generated_signal_count: number;
  signals: TechnologySignal[];
  limitations: string[];
}
