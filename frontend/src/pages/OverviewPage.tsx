import { useOrganization } from "../context/OrganizationContext";
import { CompanyReportBody } from "../features/report/CompanyReportBody";
import { HiringIntelligenceSummary } from "../features/hiring/HiringIntelligenceSummary";
import { GraphInsightsPanel } from "../features/insights/GraphInsightsPanel";

export function OverviewPage() {
  const { organization } = useOrganization();

  return <div className="page overview-page">
    <section className="executive-header">
      <div><span className="eyebrow">Executive intelligence workspace</span><h1>Account Growth Intelligence</h1><p>Observed hiring evidence, deterministic intelligence, and governed interpretation for <strong>{organization}</strong>.</p></div>
      <div className="executive-header__scope"><span>Evidence scope</span><strong>Public hiring records</strong><small>Observed evidence—not enterprise-wide disclosure</small></div>
    </section>

    <div className="intelligence-divider"><span>Hiring intelligence</span></div>
    <HiringIntelligenceSummary organization={organization} />

    <div className="intelligence-divider"><span>Company report</span></div>
    <CompanyReportBody organization={organization} />

    <div className="intelligence-divider"><span>Knowledge graph insights</span></div>
    <GraphInsightsPanel organization={organization} />
  </div>;
}
