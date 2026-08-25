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

export interface LOBOpportunityRow {
  line_of_business: string;
  emerging_ai_theme: string;
  likely_use_cases: string[];
  signal_strength: string;
  relevant_hiring_jobs?: number | null;
  narrative: string;
  supporting_reference_ids: string[];
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
    lob_opportunities: LOBOpportunityRow[];
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
    lob_opportunities: LOBOpportunityRow[];
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
