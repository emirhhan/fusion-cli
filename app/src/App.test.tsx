import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Uygulama } from "./App";
import { ProtocolClient } from "./protocol/client";

function fakeClient() {
  let listener: ((line: string) => void) | null = null;
  const written: string[] = [];
  const client = new ProtocolClient(
    (line) => written.push(line),
    (handler) => {
      listener = handler;
    },
  );
  return { client, written, receive: (line: string) => listener?.(line) };
}

afterEach(cleanup);

describe("Uygulama", () => {
  it("soru gelince onay diyaloğunu açar", async () => {
    const fake = fakeClient();
    render(<Uygulama istemci={fake.client} />);
    fake.receive(JSON.stringify({
      tip: "soru",
      id: "1",
      veri: { tur: "onay", arac: "write_file", argumanlar: {}, secenekler: [{ deger: "deny", etiket: "Reddet" }] },
    }));
    await waitFor(() => expect(screen.getByText(/izin verilsin mi/i)).toBeTruthy());
  });

  it("olayları konuşma akışında gösterir", async () => {
    const fake = fakeClient();
    render(<Uygulama istemci={fake.client} />);
    fake.receive(JSON.stringify({ tip: "olay", veri: { olay: "ToolExecuted", name: "write_file" } }));
    await waitFor(() => expect(screen.getByText(/write_file/)).toBeTruthy());
  });

  it("görevi tur.calistir isteğiyle gönderir", () => {
    const fake = fakeClient();
    render(<Uygulama istemci={fake.client} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "bir oyun yap" } });
    screen.getByRole("button", { name: "Gönder" }).click();
    const request = fake.written.map((line) => JSON.parse(line)).find((message) => message.ad === "tur.calistir");
    expect(request?.veri).toEqual({ gorev: "bir oyun yap" });
  });
});
