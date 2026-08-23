import { useOrganization } from "../context/OrganizationContext";
import { AskStrategyPanel } from "../features/strategy/AskStrategyPanel";

export function StrategicSignalsPage() {
  const { organization } = useOrganization();

  return <div className="page">
    <div className="page-heading">
      <div>
        <span className="eyebrow">Strategic Signals</span>
        <h1>Evidence-grounded strategic research</h1>
        <p>Research strategic priorities, technology direction, business initiatives, and recent developments for {organization}.</p>
      </div>
    </div>
    <div id="ask-strategy"><AskStrategyPanel organization={organization} /></div>
  </div>;
}
