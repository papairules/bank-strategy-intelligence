import { useEffect, useState } from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useOrganization } from "../context/OrganizationContext";
import { AppShell } from "./AppShell";

afterEach(cleanup);

function renderShell(apiRequest = vi.fn(), agentRequest = vi.fn()) {
  function TestPage() {
    const { organization } = useOrganization();
    const [detailOpen, setDetailOpen] = useState(false);
    const [agentResult, setAgentResult] = useState(false);

    useEffect(() => apiRequest(organization), [organization]);

    return <div>
      <span>Scoped to {organization}</span>
      <button onClick={() => setDetailOpen(true)}>Open detail</button>
      <button onClick={() => { agentRequest(organization); setAgentResult(true); }}>Submit agent</button>
      {detailOpen && <span>Open record detail</span>}
      {agentResult && <span>Previous agent result</span>}
    </div>;
  }

  render(<MemoryRouter><Routes><Route element={<AppShell />}><Route index element={<TestPage />} /></Route></Routes></MemoryRouter>);
  return { apiRequest, agentRequest };
}

describe("AppShell organization selector", () => {
  it("defaults to Wells Fargo and changes API scope to BNY without invoking an agent", async () => {
    const user = userEvent.setup();
    const { apiRequest, agentRequest } = renderShell();
    const selector = screen.getByRole("combobox", { name: "Organization" });

    expect(selector).toHaveValue("Wells Fargo");
    expect(screen.getByRole("option", { name: "BNY" })).toBeInTheDocument();
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("Wells Fargo"));

    await user.selectOptions(selector, "BNY");

    expect(selector).toHaveValue("BNY");
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("BNY"));
    expect(agentRequest).not.toHaveBeenCalled();
  });

  it("clears page-local detail and agent-result state when organization changes", async () => {
    const user = userEvent.setup();
    const { agentRequest } = renderShell();

    await user.click(screen.getByRole("button", { name: "Open detail" }));
    await user.click(screen.getByRole("button", { name: "Submit agent" }));
    expect(screen.getByText("Open record detail")).toBeInTheDocument();
    expect(screen.getByText("Previous agent result")).toBeInTheDocument();
    expect(agentRequest).toHaveBeenCalledOnce();

    await user.selectOptions(screen.getByRole("combobox", { name: "Organization" }), "BNY");

    expect(screen.queryByText("Open record detail")).not.toBeInTheDocument();
    expect(screen.queryByText("Previous agent result")).not.toBeInTheDocument();
    expect(agentRequest).toHaveBeenCalledOnce();
  });
});
