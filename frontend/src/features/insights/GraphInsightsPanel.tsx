import { graphInsightsApi } from "../../api/graphInsights";
import { Panel } from "../../components/Panel";
import { RankedBars } from "../../components/RankedBars";
import { ErrorState, LoadingState } from "../../components/States";
import { useApi } from "../../hooks/useApi";
import type { GraphInsightStrategicTheme } from "../../types/graphInsights";
import { formatNumber, formatPercent, titleCase } from "../../utils/format";

export function GraphInsightsPanel({ organization }: { organization: string }) {
  const insights = useApi((signal) => graphInsightsApi.get(organization, signal), [organization]);

  return (
    <Panel
      title="Cross-domain graph insights"
      eyebrow="Hiring + strategy knowledge graph"
      action={insights.data ? <span className="panel-note">{formatNumber(insights.data.node_count)} nodes · {formatNumber(insights.data.edge_count)} edges</span> : undefined}
    >
      <p className="panel-intro">Combines persisted hiring evidence and cached Strategy Agent research from the same organization-scoped knowledge graph. Strategic themes require a prior Strategy Agent run to be available here.</p>
      {insights.loading && <LoadingState label="Loading graph insights…" />}
      {insights.error && <ErrorState message={insights.error} />}
      {insights.data && (
        <div className="graph-insights">
          <StrategicThemes themes={insights.data.strategic_themes} />
          <div className="graph-insights__grid">
            <div>
              <h3>Top capabilities</h3>
              <RankedBars
                emptyMessage="No capabilities are classified in the graph yet."
                items={insights.data.top_capabilities.map((item) => ({
                  label: item.name,
                  count: item.job_count,
                  percentage: insights.data!.jobs_read ? (item.job_count / insights.data!.jobs_read) * 100 : 0,
                }))}
              />
            </div>
            <div>
              <h3>Top technologies</h3>
              <RankedBars
                emptyMessage="No technologies are classified in the graph yet."
                items={insights.data.top_technologies.map((item) => ({
                  label: item.name,
                  count: item.job_count,
                  percentage: insights.data!.jobs_read ? (item.job_count / insights.data!.jobs_read) * 100 : 0,
                }))}
              />
            </div>
          </div>
          <p className="coverage-note">
            {formatNumber(insights.data.classified_jobs_used)} of {formatNumber(insights.data.jobs_read)} jobs carry a capability classification
            {insights.data.enriched_jobs_used > 0 && <> ({formatNumber(insights.data.enriched_jobs_used)} LLM-verified)</>}.
          </p>
        </div>
      )}
    </Panel>
  );
}

function StrategicThemes({ themes }: { themes: GraphInsightStrategicTheme[] }) {
  if (themes.length === 0) {
    return <div className="inline-empty">No Strategy Agent research is cached for this organization yet. Ask a question in Strategic Signals or generate a Company Report to populate this.</div>;
  }
  return (
    <div className="strategic-signals">
      {themes.map((theme) => (
        <article key={theme.name}>
          <h3>{theme.name}</h3>
          <div className="strategic-signal__meta">
            <span>{titleCase(theme.direction)}</span>
            {theme.time_horizon && <span>{theme.time_horizon}</span>}
            {theme.business_unit && <span>{theme.business_unit}</span>}
            <span>{formatPercent(theme.confidence * 100, 0)} confidence</span>
            <span>{theme.evidence_count} evidence record{theme.evidence_count === 1 ? "" : "s"}</span>
          </div>
        </article>
      ))}
    </div>
  );
}
