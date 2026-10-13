import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Composer } from "./Composer";

afterEach(cleanup);
const receipt = (state: string) => ({ requestId: "istek", sessionId: "oturum", turnId: null, state, error: state === "failed" ? "reddedildi" : null });

describe("Composer gönderim makbuzu", () => {
  it("başarısız makbuz taslağı ve ekleri korur", () => {
    render(<Composer onSend={() => receipt("failed")} attachments={[{ kind: "file", name: "not.md", path: "/tmp/not.md" }]} />);
    const textbox = screen.getByLabelText("Mesaj");
    fireEvent.change(textbox, { target: { value: "yeniden gönder" } });
    fireEvent.keyDown(textbox, { key: "Enter" });
    expect(textbox).toHaveProperty("value", "yeniden gönder");
    expect(screen.getByText("not.md")).toBeTruthy();
  });

  it("bekleyen kabul taslağı temizlemez ve iki Enter tek callback çağırır", () => {
    const onSend = vi.fn(() => new Promise(() => undefined));
    render(<Composer onSend={onSend} />);
    const textbox = screen.getByLabelText("Mesaj");
    fireEvent.change(textbox, { target: { value: "tek gönderim" } });
    fireEvent.keyDown(textbox, { key: "Enter" });
    expect(textbox).toHaveProperty("value", "tek gönderim");
    fireEvent.keyDown(textbox, { key: "Enter" });
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it("eski kabul sırasında yazılmış yeni taslağı korur", async () => {
    let accept!: (value: ReturnType<typeof receipt>) => void;
    render(<Composer onSend={() => new Promise<ReturnType<typeof receipt>>((resolve) => { accept = resolve; })} />);
    const textbox = screen.getByLabelText("Mesaj");
    fireEvent.change(textbox, { target: { value: "ilk görev" } });
    fireEvent.keyDown(textbox, { key: "Enter" });
    fireEvent.change(textbox, { target: { value: "yeni taslak" } });
    await act(async () => { accept(receipt("accepted")); });
    expect(textbox).toHaveProperty("value", "yeni taslak");
  });
});

it("legacy void callback kabulü taslağı temizler", () => {
  const onSend = vi.fn(() => undefined);
  render(<Composer onSend={onSend} />);
  const textbox = screen.getByLabelText("Mesaj");
  fireEvent.change(textbox, { target: { value: "eski callback" } });
  fireEvent.keyDown(textbox, { key: "Enter" });
  expect(onSend).toHaveBeenCalledExactlyOnceWith("eski callback");
  expect(textbox).toHaveProperty("value", "");
});

it("promise reject taslağı ve ekleri korur", async () => {
  render(<Composer onSend={() => Promise.reject(new Error("test reddi"))}
    attachments={[{ kind: "file", name: "not.md", path: "/tmp/not.md" }]} />);
  const textbox = screen.getByLabelText("Mesaj");
  fireEvent.change(textbox, { target: { value: "yeniden gönder" } });
  await act(async () => { fireEvent.keyDown(textbox, { key: "Enter" }); });
  expect(textbox).toHaveProperty("value", "yeniden gönder");
  expect(screen.getByText("not.md")).toBeTruthy();
});

it("A bekleyen kabul B sohbetinin gönderimini kilitlemez ve A kabulü B taslağını temizlemez", async () => {
  let accept!: (value: ReturnType<typeof receipt>) => void;
  const sendA = vi.fn(() => new Promise<ReturnType<typeof receipt>>((resolve) => { accept = resolve; }));
  const sendB = vi.fn(() => new Promise(() => undefined));
  const view = render(<Composer key="A" onSend={sendA} />);
  fireEvent.change(screen.getByLabelText("Mesaj"), { target: { value: "A görevi" } });
  fireEvent.keyDown(screen.getByLabelText("Mesaj"), { key: "Enter" });
  view.rerender(<Composer key="B" onSend={sendB} />);
  const textbox = screen.getByLabelText("Mesaj");
  fireEvent.change(textbox, { target: { value: "B görevi" } });
  fireEvent.keyDown(textbox, { key: "Enter" });
  expect(sendB).toHaveBeenCalledExactlyOnceWith("B görevi");
  await act(async () => { accept(receipt("accepted")); });
  expect(textbox).toHaveProperty("value", "B görevi");
});
