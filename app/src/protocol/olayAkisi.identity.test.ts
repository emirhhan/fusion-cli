import { expect, it } from "vitest";
import { olayEkle } from "./olayAkisi";
it("akan ara anlatım persistent kimliğini araç projection sırasında korur", () => {
  const messages = olayEkle([{ id: "persistent-answer", rol: "asistan", metin: "İnceliyorum", akan: true }], { olay: "ToolStarted", tool_name: "read_file" });
  expect(messages.find((message) => message.ara)?.id).toBe("persistent-answer");
  expect(messages.find((message) => message.ara)?.akan).toBeUndefined();
});
