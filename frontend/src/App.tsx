import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./layouts/AppShell";
import { HiringIntelligencePage } from "./pages/HiringIntelligencePage";
import { OverviewPage } from "./pages/OverviewPage";
import { TechnologyIntelligencePage } from "./pages/TechnologyIntelligencePage";
import { EvidencePage } from "./pages/EvidencePage";
import { StrategicSignalsPage } from "./pages/StrategicSignalsPage";

export default function App() {
  return <BrowserRouter><Routes><Route element={<AppShell />}><Route index element={<OverviewPage />} /><Route path="hiring" element={<HiringIntelligencePage />} /><Route path="technology" element={<TechnologyIntelligencePage />} /><Route path="signals" element={<StrategicSignalsPage />} /><Route path="evidence" element={<EvidencePage />} /></Route></Routes></BrowserRouter>;
}
