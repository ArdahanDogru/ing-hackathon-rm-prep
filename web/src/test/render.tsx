// Render helpers for screen tests.
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { Lang, RunView } from "../api/types";
import { LangContext } from "../i18n";
import { Dashboard } from "../screens/Dashboard";

export function renderWith(ui: ReactElement, { lang = "TR" as Lang, path = "/" } = {}) {
  return render(
    <LangContext.Provider value={lang}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={ui} />
          <Route path="/meeting/:runId" element={<div data-testid="meeting-route" />} />
        </Routes>
      </MemoryRouter>
    </LangContext.Provider>,
  );
}

export function renderDashboard(view: RunView, onView: (v: RunView) => void = () => {}, lang: Lang = "TR") {
  return renderWith(<Dashboard view={view} onView={onView} />, { lang });
}
