import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./layouts/AppShell";
import { FuturePage } from "./pages/FuturePage";
import { HiringIntelligencePage } from "./pages/HiringIntelligencePage";
import { OverviewPage } from "./pages/OverviewPage";
import { TechnologyIntelligencePage } from "./pages/TechnologyIntelligencePage";
import { EvidencePage } from "./pages/EvidencePage";

export default function App() {
  return <BrowserRouter><Routes><Route element={<AppShell />}><Route index element={<OverviewPage />} /><Route path="hiring" element={<HiringIntelligencePage />} /><Route path="technology" element={<TechnologyIntelligencePage />} /><Route path="signals" element={<FuturePage title="Strategic Signals" />} /><Route path="evidence" element={<EvidencePage />} /></Route></Routes></BrowserRouter>;
}
