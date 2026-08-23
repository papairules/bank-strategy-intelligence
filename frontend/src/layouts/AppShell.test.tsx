import { useEffect, useState } from "react";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useOrganization } from "../context/OrganizationContext";
import { AVAILABLE_ORGANIZATIONS, ORGANIZATION_STORAGE_KEY } from "../config/organization";
import { AppShell } from "./AppShell";

function createMemoryStorage(): Storage {
  const store = new Map<string, string>();
  return {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    removeItem: (key: string) => void store.delete(key),
    clear: () => store.clear(),
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    get length() { return store.size; },
  };
}

afterEach(cleanup);
beforeEach(() => vi.stubGlobal("sessionStorage", createMemoryStorage()));

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

  render(<MemoryRouter><Routes><Route element={<AppShell />}><Route index element={<TestPage />} /><Route path="hiring" element={<TestPage />} /></Route></Routes></MemoryRouter>);
  return { apiRequest, agentRequest };
}

describe("AppShell organization selection", () => {
  it("shows a picker and requests nothing when no organization is stored", () => {
    const { apiRequest } = renderShell();

    expect(screen.getByRole("heading", { name: "Select a company" })).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Organization" })).not.toBeInTheDocument();
    const selector = screen.getByRole("combobox", { name: "Company" });
    expect(within(selector).getAllByRole("option").slice(1).map((item) => item.textContent)).toEqual([...AVAILABLE_ORGANIZATIONS]);
    expect(screen.getByRole("button", { name: "Enter Workspace" })).toBeDisabled();
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it("reveals the shell scoped to the picked bank and persists the choice", async () => {
    const user = userEvent.setup();
    const { apiRequest } = renderShell();

    await user.selectOptions(screen.getByRole("combobox", { name: "Company" }), "Wells Fargo");
    await user.click(screen.getByRole("button", { name: "Enter Workspace" }));

    expect(screen.queryByRole("heading", { name: "Select a company" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Organization" })).toHaveValue("Wells Fargo");
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("Wells Fargo"));
    expect(window.sessionStorage.getItem(ORGANIZATION_STORAGE_KEY)).toBe("Wells Fargo");
  });

  it("skips the picker when an organization is already stored", () => {
    window.sessionStorage.setItem(ORGANIZATION_STORAGE_KEY, "BNY");
    const { apiRequest } = renderShell();

    expect(screen.queryByRole("heading", { name: "Select a company" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Organization" })).toHaveValue("BNY");
    expect(apiRequest).toHaveBeenCalledWith("BNY");
  });

  it("changes API scope to BNY, persists it, and invokes no agent", async () => {
    window.sessionStorage.setItem(ORGANIZATION_STORAGE_KEY, "Wells Fargo");
    const user = userEvent.setup();
    const { apiRequest, agentRequest } = renderShell();
    const selector = screen.getByRole("combobox", { name: "Organization" });

    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("Wells Fargo"));

    await user.selectOptions(selector, "BNY");

    expect(selector).toHaveValue("BNY");
    await waitFor(() => expect(apiRequest).toHaveBeenCalledWith("BNY"));
    expect(window.sessionStorage.getItem(ORGANIZATION_STORAGE_KEY)).toBe("BNY");
    expect(agentRequest).not.toHaveBeenCalled();
  });

  it("clears page-local detail and agent-result state when organization changes", async () => {
    window.sessionStorage.setItem(ORGANIZATION_STORAGE_KEY, "Wells Fargo");
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

  it("keeps the selected company while navigating through the workspace", async () => {
    const user = userEvent.setup();
    renderShell();
    await user.selectOptions(screen.getByRole("combobox", { name: "Company" }), "Goldman Sachs");
    await user.click(screen.getByRole("button", { name: "Enter Workspace" }));
    expect(screen.getByText("Scoped to Goldman Sachs")).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: /Hiring Intelligence/ }));

    expect(screen.queryByRole("heading", { name: "Select a company" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Organization" })).toHaveValue("Goldman Sachs");
    expect(screen.getByText("Scoped to Goldman Sachs")).toBeInTheDocument();
  });
});
