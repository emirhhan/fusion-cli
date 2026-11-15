import { afterEach, describe, expect, it } from "vitest";
import { SPLIT_STORAGE_KEY, readSplitId, resolveSplitId, saveSplitId } from "./splitView";

afterEach(() => localStorage.clear());

describe("bölünmüş görünüm (P-064)", () => {
  it("saklı kimlik okunur; bozuk değer yok sayılır", () => {
    saveSplitId("abc-1");
    expect(readSplitId()).toBe("abc-1");
    localStorage.setItem(SPLIT_STORAGE_KEY, "../x y");
    expect(readSplitId()).toBeNull();
    saveSplitId(null);
    expect(localStorage.getItem(SPLIT_STORAGE_KEY)).toBeNull();
  });

  it("aktif sohbet ikinci bölmeye alınmaz; açık olmayan sohbet gösterilmez", () => {
    const acik = new Set(["a", "b"]);
    expect(resolveSplitId("b", "a", acik)).toBe("b");
    expect(resolveSplitId("a", "a", acik)).toBeNull();
    expect(resolveSplitId("c", "a", acik)).toBeNull();
    expect(resolveSplitId(null, "a", acik)).toBeNull();
  });
});
