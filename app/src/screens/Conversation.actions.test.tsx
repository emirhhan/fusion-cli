import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Conversation } from "./Conversation";
afterEach(cleanup);
const answer = { id: "answer", rol: "asistan" as const, metin: "Yanıt" };
it("passes answer and history index to real actions", async () => {
  const onReadAloud = vi.fn(); const onContinueInNewChat = vi.fn();
  render(<Conversation mesajlar={[{ id: "user", rol: "kullanici", metin: "Soru" }, answer]} onReadAloud={onReadAloud} onContinueInNewChat={onContinueInNewChat} />);
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Sesli oku" })));
  expect(onReadAloud).toHaveBeenCalledWith("Yanıt");
  fireEvent.click(screen.getByRole("button", { name: "Yeni sohbette devam et" }));
  expect(onContinueInNewChat).toHaveBeenCalledWith(1);
});
it("acknowledges evaluation after success and exposes errors", async () => {
  let resolve!: () => void;
  const onEvaluate = vi.fn(() => new Promise<void>((done) => { resolve = done; }));
  render(<Conversation mesajlar={[answer]} onEvaluate={onEvaluate} onReadAloud={vi.fn().mockRejectedValue(new Error("Ses kullanılamıyor"))} />);
  fireEvent.click(screen.getByRole("button", { name: "Yanıtı değerlendir" }));
  fireEvent.click(screen.getByRole("button", { name: "Olumlu değerlendir" }));
  expect(onEvaluate).toHaveBeenCalledWith("Yanıt", "positive");
  expect(screen.queryByText("Değerlendirmen kaydedildi")).toBeNull();
  await act(async () => resolve());
  expect(screen.getByText("Değerlendirmen kaydedildi")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Sesli oku" }));
  expect((await screen.findByRole("alert")).textContent).toBe("Ses kullanılamıyor");
});
it("hides actions for streaming and narration", () => {
  render(<Conversation mesajlar={[{ ...answer, akan: true }, { ...answer, id: "narration", ara: true }]} onReadAloud={vi.fn()} onEvaluate={vi.fn()} onContinueInNewChat={vi.fn()} />);
  expect(screen.queryByRole("button")).toBeNull();
});
it("keeps rejected evaluations unselected and allows a retry", async () => {
  const onEvaluate = vi.fn().mockRejectedValueOnce(new Error("Kaydedilemedi")).mockResolvedValue(undefined);
  render(<Conversation mesajlar={[answer]} onEvaluate={onEvaluate} />);
  fireEvent.click(screen.getByRole("button", { name: "Yanıtı değerlendir" }));
  fireEvent.click(screen.getByRole("button", { name: "Olumsuz değerlendir" }));
  expect((await screen.findByRole("alert")).textContent).toBe("Kaydedilemedi");
  expect(screen.getByRole("button", { name: "Olumsuz değerlendir" }).getAttribute("aria-pressed")).toBe("false");
  fireEvent.click(screen.getByRole("button", { name: "Olumsuz değerlendir" }));
  expect(await screen.findByText("Değerlendirmen kaydedildi")).toBeTruthy();
  expect(onEvaluate).toHaveBeenCalledTimes(2);
});
