import { useOrganization } from "../context/OrganizationContext";
import { CompanyReportBody } from "../features/report/CompanyReportBody";

export function CompanyReportPage() {
  const { organization } = useOrganization();

  return <div className="page">
    <div className="page-heading"><div><span className="eyebrow">Combined intelligence</span><h1>Company Report</h1><p>Evidence-aware Strategy, Hiring, and Hiring KG synthesis for {organization}.</p></div></div>
    <CompanyReportBody organization={organization} />
  </div>;
}
