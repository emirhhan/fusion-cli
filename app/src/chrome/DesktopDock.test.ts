import { afterEach, expect, it, vi } from "vitest";
import { chromeKit } from "./extensionTestKit";
// @ts-expect-error Eklenti modülü düz JavaScript olarak dağıtılır.
import { execute, getSelected } from "../../../chrome-extension/core.js";

afterEach(() => vi.unstubAllGlobals());

it("dock odağı sekmeyi ve penceresini açar, ajan bağını değiştirmez", async () => {
  const { chromeMock } = chromeKit();
  const update = vi.fn(async () => ({}));
  Object.assign(chromeMock, { windows: { update } });
  await execute({ islem: "tab_select", veri: { id: 7 } });
  await execute({ islem: "tab_focus", veri: { id: 8 } });
  expect(chromeMock.tabs.update).toHaveBeenCalledWith(8, { active: true });
  expect(update).toHaveBeenCalledWith(1, { focused: true });
  expect((await getSelected()).id).toBe(7);
});

it("kapanan sekme için başka pencereye odaklanmaz", async () => {
  const { chromeMock } = chromeKit();
  const update = vi.fn();
  Object.assign(chromeMock, { windows: { update } });
  await expect(execute({ islem: "tab_focus", veri: { id: 999 } })).rejects.toThrow();
  expect(chromeMock.tabs.update).not.toHaveBeenCalled();
  expect(update).not.toHaveBeenCalled();
});
