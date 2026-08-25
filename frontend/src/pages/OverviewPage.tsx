import { useOrganization } from "../context/OrganizationContext";
import { CompanyReportBody } from "../features/report/CompanyReportBody";
import { HiringIntelligenceSummary } from "../features/hiring/HiringIntelligenceSummary";
import { GraphInsightsPanel } from "../features/insights/GraphInsightsPanel";

export function OverviewPage() {
  const { organization } = useOrganization();

  return <div className="page overview-page">
    <section className="executive-header">
      <div><span className="eyebrow">Executive intelligence workspace</span><h1>Account Growth Intelligence</h1></div>
    </section>

    <div className="intelligence-divider"><span>Hiring intelligence</span></div>
    <HiringIntelligenceSummary organization={organization} />

    <div className="intelligence-divider"><span>Company report</span></div>
    <CompanyReportBody organization={organization} />

    <div className="intelligence-divider"><span>Knowledge graph insights</span></div>
    <GraphInsightsPanel organization={organization} />
  </div>;
}
