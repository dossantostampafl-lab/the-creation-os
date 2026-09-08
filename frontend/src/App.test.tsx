import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import App from "./App";

describe("Creator Interface", () => {
  beforeEach(() => sessionStorage.clear());

  it("starts at the sovereign authentication surface without invented telemetry", () => {
    render(<App />);
    expect(screen.getByText("Creator Interface")).toBeInTheDocument();
    expect(screen.getByText(/Nenhuma telemetria é simulada/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ENTRAR" })).toBeInTheDocument();
    expect(screen.queryByText("LIVING CORE VISUALIZATION")).not.toBeInTheDocument();
  });
});
