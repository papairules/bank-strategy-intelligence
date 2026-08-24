export interface GraphInsightConcept {
  name: string;
  job_count: number;
}

export interface GraphInsightStrategicTheme {
  name: string;
  direction: string;
  confidence: number;
  time_horizon: string | null;
  business_unit: string | null;
  evidence_count: number;
}

export interface GraphInsightsSnapshot {
  organization: string;
  node_count: number;
  edge_count: number;
  jobs_read: number;
  classified_jobs_used: number;
  enriched_jobs_used: number;
  hiring_signals_used: number;
  strategic_themes_used: number;
  top_capabilities: GraphInsightConcept[];
  top_technologies: GraphInsightConcept[];
  top_locations: GraphInsightConcept[];
  strategic_themes: GraphInsightStrategicTheme[];
}
