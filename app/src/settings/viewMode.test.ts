import { afterEach, expect, it } from "vitest";
import { cycleViewMode, getViewMode, readViewMode, resetViewModeCache, VIEW_MODE_STORAGE_KEY } from "./viewMode";
import { runAppAction, type AppActionDeps } from "../shortcuts/appActions";
import { DEFAULT_BINDINGS, effectiveBindings } from "../shortcuts/keys";

afterEach(() => { localStorage.clear(); resetViewModeCache(); });

it("Ctrl+O görünüm kipini Normal → Ayrıntılı → Özet → Normal döndürür ve saklar (#444)", () => {
  expect(getViewMode()).toBe("normal");
  expect(cycleViewMode()).toBe("verbose");
  expect(localStorage.getItem(VIEW_MODE_STORAGE_KEY)).toBe("verbose");
  expect(cycleViewMode()).toBe("summary");
  expect(cycleViewMode()).toBe("normal");
  expect(readViewMode({ getItem: () => "bozuk" })).toBe("normal");
});

it("ctrl+o varsayılanı gorunum_kipi eylemini çalıştırır", () => {
  expect(DEFAULT_BINDINGS["ctrl+o"]).toBe("gorunum_kipi");
  expect(runAppAction("gorunum_kipi", {} as AppActionDeps)).toBe(true);
  expect(getViewMode()).toBe("verbose");
});

it("⌘⌃W macOS'ta bölmeden çıkar; Windows'ta Ctrl+W oturumu kapatmaya devam eder (#444)", () => {
  expect(DEFAULT_BINDINGS["mod+ctrl+w"]).toBe("bolmeyi_kapat");
  expect(effectiveBindings(DEFAULT_BINDINGS, true).get("mod+ctrl+w")).toBe("bolmeyi_kapat");
  expect(effectiveBindings(DEFAULT_BINDINGS, true).get("mod+w")).toBe("oturumu_kapat");
  expect(effectiveBindings(DEFAULT_BINDINGS, false).get("mod+w")).toBe("oturumu_kapat");
  // Kullanıcı yalnız ⌃-li bağ yazdıysa Windows'ta yine eşleşir.
  expect(effectiveBindings({ "mod+ctrl+k": "palet" }, false).get("mod+k")).toBe("palet");
});
