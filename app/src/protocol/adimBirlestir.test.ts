import { describe, expect, it } from "vitest";
import type { Mesaj } from "../screens/Conversation";
import { adimiEkle, ayniAracCagrisi } from "./adimBirlestir";
import { olayEkle } from "./olayAkisi";
import { olayAdimi, type OlayAdimi } from "./olayMetni";

const owner = { session_id: "session", turn_id: "turn", attempt_id: "attempt" };
// Recorded name-pair shapes; owners, call IDs, summaries and receipts are synthetic.
const pairs = [
  ["chrome_action", "claude-in-chrome__tabs_create_mcp", { action: "new_tab" }],
  ["chrome_navigate", "claude-in-chrome__navigate", { url: "https://fixture.example/" }],
  ["chrome_page", "claude-in-chrome__read_page", { tree: "interactive" }],
  ["chrome_action", "claude-in-chrome__get_page_text", { action: "text" }],
] as const;
const steps = (messages: Mesaj[]) => messages.flatMap(message => message.adimlar ?? []);
const start = (callId = "call", extra = {}) => ({
  olay: "ToolStarted", ...owner, call_id: callId, name: "model_tool",
  metin: "Ölçülen başlangıç özeti", event_id: `${callId}:start`, ...extra,
});
const finish = (callId = "call", extra = {}) => ({
  olay: "ToolExecuted", ...owner, call_id: callId, name: "executed_tool",
  outcome: "ok", output: "Exact execution receipt", event_id: `${callId}:finish`, ...extra,
});
function step(event: Record<string, unknown>): OlayAdimi {
  const result = olayAdimi(event);
  if (!result) throw new Error("Expected tool step");
  return result;
}

describe("owned tool identity across execution name rewrites", () => {
  it("projects the recorded four Chrome name-rewrite shapes as four tools and one review", () => {
    let messages: Mesaj[] = [];
    pairs.forEach(([requested, executed, args], index) => {
      messages = olayEkle(messages, start(`call-${index}`, { name: requested, args }));
      messages = olayEkle(messages, finish(`call-${index}`, { name: executed, args }));
    });
    messages = olayEkle(messages, { olay: "SelfReviewFinished", completed: true, issue_found: false });
    const projected = steps(messages);
    expect(projected).toHaveLength(5);
    expect(projected.filter(item => item.arac)).toHaveLength(4);
    projected.slice(0, 4).forEach((item, index) => {
      expect(item).toMatchObject({ arac: pairs[index][1], metin: "Ölçülen başlangıç özeti", basladi: false, durum: "ok", cikti: "Exact execution receipt" });
    });
  });
  it("pairs renamed adjacent steps in the shared team/activity helper", () => {
    const result = adimiEkle([step(start())], step(finish("call", { outcome: "failed", output: "Real failure" })));
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({ arac: "executed_tool", durum: "failed", cikti: "Real failure", metin: "Ölçülen başlangıç özeti" });
  });
  it("pairs renamed concurrent calls in reverse order across narration", () => {
    let messages = olayEkle([], start("first"));
    messages = olayEkle(messages, start("second"));
    messages = olayEkle(messages, { olay: "NarrationPublished", text: "İki çağrı sürüyor" });
    messages = olayEkle(messages, finish("second", { output: "Second receipt" }));
    messages = olayEkle(messages, finish("first", { output: "First receipt" }));
    expect(steps(messages)).toHaveLength(2);
    expect(steps(messages).map(item => item.cikti)).toEqual(["First receipt", "Second receipt"]);
  });
  it.each(["session_id", "turn_id", "attempt_id", "call_id"])("does not merge a different %s despite rewritten names", field => {
    const original = step(start());
    const foreign = step(finish("call", { [field]: "foreign" }));
    expect(ayniAracCagrisi(original, foreign)).toBe(false);
    expect(adimiEkle([original], foreign)).toHaveLength(2);
  });
  it.each(["session_id", "turn_id", "attempt_id", "call_id"])("does not relax names when %s is missing", field => {
    const original = step(start("call", { [field]: undefined }));
    const terminal = step(finish("call", { [field]: undefined }));
    expect(ayniAracCagrisi(original, terminal)).toBe(false);
    expect(adimiEkle([original], terminal)).toHaveLength(2);
  });
  it.each(["session_id", "turn_id", "attempt_id", "call_id"])("does not use blank %s as full ownership", field => {
    expect(ayniAracCagrisi(step(start("call", { [field]: " " })), step(finish("call", { [field]: " " })))).toBe(false);
  });
  it("keeps matching partial legacy calls strict by name", () => {
    const original = step(start("legacy", { attempt_id: undefined }));
    const sameName = step(finish("legacy", { attempt_id: undefined, name: "model_tool" }));
    expect(adimiEkle([original], sameName)).toHaveLength(1);
  });
  it("keeps identityless adjacent legacy calls strict by name", () => {
    const original = step({ olay: "ToolStarted", name: "old_name" });
    expect(adimiEkle([original], step({ olay: "ToolExecuted", name: "new_name", outcome: "ok" }))).toHaveLength(2);
    expect(adimiEkle([original], step({ olay: "ToolExecuted", name: "old_name", outcome: "ok" }))).toHaveLength(1);
  });
  it("does not attach a stale renamed receipt to a current pending call", () => {
    let messages = olayEkle([], start("call", { turn_id: "new-turn", attempt_id: "new-attempt" }));
    messages = olayEkle(messages, finish());
    expect(steps(messages)).toHaveLength(2);
    expect(steps(messages)[0]).toMatchObject({ basladi: true, turnId: "new-turn", attemptId: "new-attempt" });
  });
  it("resolves only the owned terminal placeholder after a queued user message", () => {
    const pending = { ...step(start()), basladi: false, durum: "unknown", sonucAlinamadi: true };
    const messages: Mesaj[] = [{ rol: "olay", metin: pending.metin, adimlar: [pending] }, { rol: "kullanici", metin: "Next turn" }];
    const resolved = olayEkle(messages, finish());
    expect(steps(resolved)).toHaveLength(1);
    expect(steps(resolved)[0]).toMatchObject({ arac: "executed_tool", durum: "ok", cikti: "Exact execution receipt" });
  });
  it.each(["session_id", "turn_id", "attempt_id", "call_id"])("does not resolve a queued placeholder with foreign %s", field => {
    const pending = { ...step(start()), basladi: false, durum: "unknown", sonucAlinamadi: true };
    const messages: Mesaj[] = [{ rol: "olay", metin: pending.metin, adimlar: [pending] }, { rol: "kullanici", metin: "Next turn" }];
    const result = olayEkle(messages, finish("call", { [field]: "foreign" }));
    expect(steps(result)).toHaveLength(2);
    expect(steps(result)[0]).toEqual(pending);
  });

  it("does not treat a non-tool step as a rewritten tool using owner IDs alone", () => {
    expect(ayniAracCagrisi({ ...step(start()), arac: undefined }, step(finish()))).toBe(false);
  });

});
