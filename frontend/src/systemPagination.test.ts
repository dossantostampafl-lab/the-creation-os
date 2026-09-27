import { describe, expect, it } from "vitest";
import { systemPageCount } from "./systemPagination";

describe("systemPageCount", () => {
  it("uses the largest independently paged collection", () => {
    expect(systemPageCount({ missions: 4, tasks: 51, universes: 12, agents: 130 }, 25)).toBe(3);
  });

  it("always exposes at least one page", () => {
    expect(systemPageCount({ missions: 0, tasks: 0, universes: 0, agents: 0 }, 25)).toBe(1);
  });
});
