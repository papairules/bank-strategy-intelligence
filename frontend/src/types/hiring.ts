export type EmploymentType =
  | "full_time"
  | "part_time"
  | "contract"
  | "temporary"
  | "internship"
  | "other";

export type SeniorityLevel =
  | "entry"
  | "mid"
  | "senior"
  | "manager"
  | "director"
  | "executive";

export interface RecordReference {
  job_id: string;
  evidence_id: string;
}

export interface JobPosting {
  job_id: string;
  organization: string;
  source_job_id: string;
  title: string;
  description: string;
  location: string;
  country: string;
  business_unit: string | null;
  capability_classifications: string[];
  skills: string[];
  technologies: string[];
  seniority_level: SeniorityLevel | null;
  is_leadership: boolean;
  posted_date: string;
  closing_date: string | null;
  employment_type: EmploymentType | null;
  source_url: string;
  evidence_id: string;
}

export interface Evidence {
  evidence_id: string;
  source_url: string;
  source_type: string;
  source_title: string | null;
  retrieved_at: string;
  source_excerpt: string | null;
  raw_reference: string | null;
  collector_identity: string;
  provenance_metadata: Record<string, unknown>;
}

export interface EnrichmentSupport {
  field: string;
  value: string;
  excerpt: string;
  evidence_id: string;
}

export interface EnrichmentMetadata {
  provider: string;
  model: string;
  prompt_schema_version: string;
  provider_request_id: string | null;
  model_version: string | null;
  usage_metadata: Record<string, unknown>;
  enrichment_timestamp: string;
  model_confidence: number;
}

export interface HiringEnrichment {
  job_id: string;
  evidence_id: string;
  capability_classifications: string[];
  skills: string[];
  technologies: string[];
  seniority_level: string;
  is_leadership: boolean;
  business_unit: string | null;
  hiring_themes: string[];
  confidence: number;
  field_confidences: Record<string, number>;
  field_support: EnrichmentSupport[];
  limitations: string[];
  model_metadata: EnrichmentMetadata;
}

export interface JobDetail {
  job: JobPosting;
  evidence: Evidence;
  enrichment: HiringEnrichment | null;
}

export interface JobListResponse {
  items: JobPosting[];
  total: number;
  limit: number;
  offset: number;
  returned_count: number;
}

export interface CollectionRun {
  run_id: string;
  collector_id: string;
  source_id: string;
  organization: string;
  started_at: string;
  completed_at: string;
  status: "completed" | "partial" | "failed";
  pages_attempted: number;
  records_encountered: number;
  records_collected: number;
  records_skipped: number;
  issue_count: number;
  resume_cursor: string | null;
  source_metadata: Record<string, unknown>;
}

export interface GeographicGroup {
  value: string;
  job_count: number;
  percentage_of_total: number;
  contributing_records: RecordReference[];
}

export interface GeographicConcentration {
  organization: string;
  total_jobs: number;
  by_country: GeographicGroup[];
  by_state_region: GeographicGroup[];
  by_city: GeographicGroup[];
  contributing_records: RecordReference[];
}

export interface CapabilityGroup {
  capability: string;
  job_count: number;
  percentage_of_classified_jobs: number;
  contributing_records: RecordReference[];
}

export interface CapabilityConcentration {
  organization: string;
  classified_job_count: number;
  capabilities: CapabilityGroup[];
  contributing_records: RecordReference[];
}

export interface SeniorityGroup {
  seniority_level: SeniorityLevel;
  job_count: number;
  percentage_of_jobs_with_seniority: number;
  contributing_records: RecordReference[];
}

export interface SenioritySummary {
  organization: string;
  total_jobs: number;
  jobs_with_seniority: number;
  distribution: SeniorityGroup[];
  leadership_job_count: number;
  leadership_percentage: number;
  leadership_contributing_records: RecordReference[];
  contributing_records: RecordReference[];
}

export interface TrendBucket {
  bucket_start: string;
  job_count: number;
  contributing_records: RecordReference[];
}

export interface TrendSummary {
  organization: string;
  granularity: "daily" | "weekly";
  observation_start: string | null;
  observation_end: string | null;
  buckets: TrendBucket[];
  contributing_records: RecordReference[];
}

export interface HiringSnapshot {
  organization: string;
  total_active_jobs: number;
  jobs_with_capability_classification: number;
  jobs_with_seniority: number;
  jobs_with_location: number;
  generated_at: string;
  observation_start: string | null;
  observation_end: string | null;
  contributing_records: RecordReference[];
}

export interface HiringAnalytics {
  snapshot: HiringSnapshot;
  geographic: GeographicConcentration;
  capability: CapabilityConcentration;
  seniority: SenioritySummary;
  daily_trend: TrendSummary;
  weekly_trend: TrendSummary;
}

export interface OrganizationSummary {
  organization: string;
  total_observed_jobs: number;
  jobs_with_evidence: number;
  evidence_coverage: number;
  observation_start: string | null;
  observation_end: string | null;
  latest_collection_run: CollectionRun | null;
  enriched_job_count: number;
  enrichment_coverage: number;
  signal_count: number;
  generated_at: string;
  geographic: GeographicConcentration;
  capability: CapabilityConcentration;
  seniority: SenioritySummary;
  trend: TrendSummary;
}

export interface IntelligenceSignal {
  signal_id: string;
  signal_type: string;
  organization: string;
  originating_capability: string;
  observation_period: { start_date: string; end_date: string };
  summary: string;
  confidence: number;
  supporting_evidence_ids: string[];
  limitations: string[];
}

export interface GeneratedSignal {
  title: string;
  signal: IntelligenceSignal;
  score: { strength: number; confidence: number; evidence_coverage: number };
}

export interface SignalsResponse {
  organization: string;
  generated_at: string;
  items: GeneratedSignal[];
  returned_count: number;
}

export interface JobFilters {
  location?: string;
  capability?: string;
  seniority?: SeniorityLevel | "";
  limit: number;
  offset: number;
}
