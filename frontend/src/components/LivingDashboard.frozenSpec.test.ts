import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const componentPath = fileURLToPath(new URL("./LivingDashboard.tsx", import.meta.url));
const stylePath = fileURLToPath(new URL("../styles/living-dashboard.css", import.meta.url));
const componentSource = readFileSync(componentPath, "utf-8");
const styleSource = readFileSync(stylePath, "utf-8");

// docs/CREATOR_INTERFACE_FROZEN_SPEC.md forbids reintroducing a "corporate
// dashboard" pattern (sidebar, permanent menu, fixed administrative panels)
// on the initial Creator Interface screen. This project has no jsdom/
// testing-library set up (vitest runs with environment: "node"), so a full
// component render test isn't available cheaply — this is a literal-token
// guard over the real source files instead. It is intentionally simple: it
// exists to catch someone typing "sidebar" or wiring up a permanent
// dashboard-style container again, the exact class of regression behind the
// "restore functional living universe" / "restore frozen living universe
// experience" revert cycle visible in git history for this file.
const FORBIDDEN_TOKENS = [
  "sidebar",
  "corporate-dashboard",
  "dashboard-grid",
  "admin-panel",
  "nav-menu",
  "permanent-panel",
  "fixed-panel",
];

describe("Creator Interface frozen spec — no corporate dashboard pattern", () => {
  for (const token of FORBIDDEN_TOKENS) {
    it(`LivingDashboard.tsx never references "${token}"`, () => {
      expect(componentSource.toLowerCase()).not.toContain(token);
    });

    it(`living-dashboard.css never defines a "${token}" rule`, () => {
      expect(styleSource.toLowerCase()).not.toContain(token);
    });
  }

  it("never renders a <nav> permanent navigation element", () => {
    expect(componentSource).not.toMatch(/<nav[\s>]/);
  });

  it("the on-demand overlay only renders demandPanel, never an always-on panel", () => {
    expect(componentSource).toMatch(/<section className="on-demand-overlay-host"[^>]*>\s*\{demandPanel\}/);
  });
});
