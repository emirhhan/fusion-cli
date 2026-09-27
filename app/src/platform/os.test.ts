import { afterEach, describe, expect, it, vi } from "vitest";
import { isMacOS } from "./os";

const originalPlatform = navigator.platform;
const originalUserAgent = navigator.userAgent;

function stubNavigator(platform: string, userAgent = platform) {
  vi.stubGlobal("navigator", { ...navigator, platform, userAgent });
}

afterEach(() => {
  vi.unstubAllGlobals();
  stubNavigator(originalPlatform, originalUserAgent);
});

describe("isMacOS", () => {
  it("navigator.platform MacIntel içeriyorsa doğru döner", () => {
    stubNavigator("MacIntel");
    expect(isMacOS()).toBe(true);
  });

  it("Windows platformunda yanlış döner", () => {
    stubNavigator("Win32");
    expect(isMacOS()).toBe(false);
  });

  it("Linux platformunda yanlış döner", () => {
    stubNavigator("Linux x86_64");
    expect(isMacOS()).toBe(false);
  });

  it("userAgentData.platform varsa onu tercih eder", () => {
    vi.stubGlobal("navigator", { ...navigator, platform: "", userAgent: "", userAgentData: { platform: "macOS" } });
    expect(isMacOS()).toBe(true);
  });
});
