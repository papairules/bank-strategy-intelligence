import { useOrganization } from "../context/OrganizationContext";
import { HiringIntelligenceSummary } from "../features/hiring/HiringIntelligenceSummary";

export function HiringIntelligencePage() {
  const { organization } = useOrganization();

  return (
    <div className="page">
      <div className="page-heading">
        <div><span className="eyebrow">Hiring Intelligence</span><h1>Workforce demand and capability signals</h1><p>Evidence-backed view of observed public hiring activity. Concentrations indicate hiring demand—not confirmed strategic investment.</p></div>
      </div>
      <HiringIntelligenceSummary organization={organization} />
    </div>
  );
}
