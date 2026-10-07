import { describe, expect, it } from "vitest";
import { fallbackNotice } from "./CreatorConsole";

describe("fallbackNotice", () => {
  it("names the reserve that answered and why the ChatGPT plan did not", () => {
    expect(fallbackNotice({
      provider: "freellmapi",
      fallback_from: "chatgpt",
      fallback_reason: "subscription_sharing_usage_limit_exceeded",
    })).toBe("Respondido por FreeLLM · plano ChatGPT (limite de uso atingido)");
  });

  it("still discloses the switch when the reason is unknown", () => {
    expect(fallbackNotice({ provider: "freellmapi", fallback_from: "chatgpt", fallback_reason: "something_new" }))
      .toBe("Respondido por FreeLLM · plano ChatGPT indisponível");
  });

  it("says nothing for a reply from the configured provider", () => {
    expect(fallbackNotice({ provider: "chatgpt" })).toBeNull();
    expect(fallbackNotice({})).toBeNull();
  });
});
