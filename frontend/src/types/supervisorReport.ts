export interface SupervisorReportRequest {
  organization: string;
  question?: string;
}

export interface ReportQuestionReference {
  reference_id: string;
  reference_type: string;
  label: string;
  source_url?: string | null;
  hiring_job_count?: number | null;
}

export interface ReportFinding {
  title: string;
  narrative: string;
  supporting_reference_ids: string[];
}

export interface ReportReference {
  reference_id: string;
  domain: string;
  evidence_ids: string[];
  job_ids: string[];
  source_url?: string | null;
}

export interface IntelligenceOutlookRow {
  opportunity_theme: string;
  supervisor_priority: string;
  opportunity_titles: string[];
  relevant_hiring_jobs?: number | null;
  supporting_evidence_count: number;
  supporting_job_ids: string[];
  supporting_evidence_ids: string[];
  strategy_evidence_ids: string[];
  hiring_evidence_ids: string[];
  hiring_signal_ids: string[];
  kg_concept_references: string[];
  horizon_30?: string | null;
  horizon_60?: string | null;
  horizon_90?: string | null;
  horizon_180?: string | null;
  horizon_360?: string | null;
  confidence: number;
  score: number;
  limitations: string[];
}

export interface SupervisorReportAnswer {
  organization: string;
  strategy_signal_count: number;
  hiring_signal_count: number;
  coverage: {
    total_jobs: number;
    enriched_jobs: number;
    enrichment_coverage_percentage: number;
    kg_enriched_job_count: number;
    limitations: string[];
  };
  report: {
    organization: string;
    total_hiring_jobs: number;
    executive_summary: string;
    strategic_priorities: ReportFinding[];
    hiring_intelligence: ReportFinding[];
    cross_domain_alignment: ReportFinding[];
    business_areas_to_watch: ReportFinding[];
    opportunity_horizons: {
      horizon_days: number;
      meaning: string;
      opportunity_titles: string[];
    }[];
    intelligence_outlook_rows: IntelligenceOutlookRow[];
    evidence_traceability: ReportReference[];
    limitations: string[];
  };
  provider: string;
  model: string;
}

export interface ReportQuestionRequest {
  organization: string;
  question: string;
  report: {
    organization: string;
    total_hiring_jobs: number;
    executive_summary: string;
    intelligence_outlook_rows: IntelligenceOutlookRow[];
    strategic_priorities: ReportFinding[];
    cross_domain_alignment: ReportFinding[];
    evidence_traceability: ReportReference[];
    limitations: string[];
  };
}

export interface ReportQuestionAnswer {
  organization: string;
  question: string;
  answer: string;
  supporting_references: ReportQuestionReference[];
  evidence_sufficient: boolean;
  limitations: string[];
  provider: string;
  model: string;
}
