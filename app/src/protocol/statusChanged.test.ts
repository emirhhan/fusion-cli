import { createElement } from "react";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ActivityLine } from "../screens/ActivityLine";
import { olayEkle } from "./olayAkisi";
import { olayAdimi } from "./olayMetni";

afterEach(cleanup);

const RETRY = "Model geçici olarak sunucu hatası verdi; 2 sn sonra yeniden deneniyor · deneme 1/4";
const STARTED = { olay: "ModelCallStarted", role: "agent", model: "test-model" };

describe("StatusChanged — public progress", () => {
  it("shows the actual retry reason without inventing a tool or terminal result", () => {
    expect(olayAdimi({ olay: "StatusChanged", message: RETRY })).toEqual({ metin: RETRY });
  });

  it.each([undefined, null, 12, {}, [], "", " \n\t", "\u0000\r\n"])(
    "ignores an empty or malformed message: %j", message => {
      expect(olayAdimi({ olay: "StatusChanged", message })).toBeNull();
    },
  );

  it("normalizes multiline/control whitespace and masks secrets before display", () => {
    const step = olayAdimi({ olay: "StatusChanged", message: "  Yeniden\n\t deneniyor\u0000 token=abcdefghijklmnop  " });
    expect(step).toEqual({ metin: "Yeniden deneniyor [gizlendi]" });
  });

  it("bounds Unicode status text without splitting characters or leaking a cut secret", () => {
    const unicode = olayAdimi({ olay: "StatusChanged", message: "x".repeat(238) + "😀" + "z".repeat(500) });
    expect(unicode).not.toBeNull();
    expect(Array.from(unicode!.metin)).toHaveLength(240);
    expect(unicode!.metin).toBe("x".repeat(238) + "😀…");
    const secret = olayAdimi({ olay: "StatusChanged", message: "x".repeat(231) + " sk-abcdefghijklmnopqrstuvwx" });
    expect(secret!.metin).not.toContain("sk-");
    expect(secret!.metin).not.toContain("abcdefghijklmnop");
  });

  it.each(["ProviderCallDiagnostic", "McpDiscoveryDiagnostic", "AutomaticRecallDiagnostic"])(
    "keeps private diagnostics out of the activity flow: %s", olay => {
      expect(olayAdimi({ olay, message: RETRY })).toBeNull();
    },
  );

  it("renders retry progress and replaces it on the next real model call and completion", () => {
    let messages = olayEkle([{ rol: "kullanici", metin: "Merhaba" }], STARTED);
    messages = olayEkle(messages, { olay: "StatusChanged", message: RETRY });
    const { container, rerender } = render(createElement(ActivityLine, {
      adimlar: messages.at(-1)!.adimlar!,
    }));
    expect(container.querySelector(".activity__pulse")?.textContent).toBe(RETRY + "…");
    expect(container.querySelector("details")).toBeNull();
    expect(messages.map(message => message.rol)).toEqual(["kullanici", "olay"]);

    messages = olayEkle(messages, STARTED);
    rerender(createElement(ActivityLine, { adimlar: messages.at(-1)!.adimlar! }));
    expect(container.querySelector(".activity__pulse")?.textContent).toBe("Düşünüyor…");
    expect(container.textContent).not.toContain(RETRY);

    messages = olayEkle(messages, { olay: "ModelCallFinished", requested_model: "test-model", result: { ok: true } });
    rerender(createElement(ActivityLine, { adimlar: messages.at(-1)!.adimlar! }));
    expect(container.querySelector(".activity__pulse")?.textContent).toBe("Model yanıtladı…");

    messages = olayEkle(messages, { olay: "TurnOutcome", status: "completed" });
    rerender(createElement(ActivityLine, { adimlar: messages.at(-1)!.adimlar!, aktif: false }));
    expect(container.textContent).toBe("");
  });

  it("retains a genuine terminal failure instead of leaving a retry indicator", () => {
    let messages = olayEkle([], { olay: "StatusChanged", message: RETRY });
    messages = olayEkle(messages, { olay: "TurnOutcome", status: "failed" });
    const { container } = render(createElement(ActivityLine, { adimlar: messages.at(-1)!.adimlar!, aktif: false }));
    expect(container.querySelector(".activity__result")?.textContent).toBe("Tamamlanamadı");
    expect(container.textContent).not.toContain(RETRY);
  });
});
