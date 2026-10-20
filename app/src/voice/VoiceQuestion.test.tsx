import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { VoiceQuestion } from "./VoiceQuestion";
afterEach(cleanup);
const ask = { acik: true, questionId: "q1", metin: "Dosya değişikliği uygulansın mı?\n\nTam ayrıntı: iki dosya değişecek.\nÜçüncü satır.", secenekler: [{ deger: "evet", etiket: "Onayla" }] };
it("tek paragraf özetini açmak cevap göndermez; tamamı ve kararlar açılınca görünür", () => {
 const onAnswer = vi.fn();
 render(<VoiceQuestion ask={ask} onAnswer={onAnswer} />);
 expect(screen.queryByText(/Tam ayrıntı/)).toBeNull();
 expect(screen.queryByRole("button", { name: "Onayla" })).toBeNull();
 fireEvent.click(screen.getByRole("button", { name: /Sorunun tamamını oku/ }));
 expect(screen.getByText(/Tam ayrıntı/)).toBeTruthy();
 expect(onAnswer).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole("button", { name: "Onayla" }));
 expect(onAnswer).toHaveBeenCalledWith("evet");
});
it("Escape ayrıntıyı kapatır ve özete odaklanır", () => {
 render(<VoiceQuestion ask={ask} onAnswer={vi.fn()} />);
 const summary=screen.getByRole("button", { name: /Sorunun tamamını oku/ });fireEvent.click(summary);
 fireEvent.keyDown(screen.getByText(/Tam ayrıntı/), { key: "Escape" });
 expect(screen.queryByText(/Tam ayrıntı/)).toBeNull();expect(document.activeElement).toBe(summary);
});
it("bekleyen yanıt sırasında karar düğmesi kilitlidir", () => {
 render(<VoiceQuestion ask={ask} onAnswer={vi.fn()} answerPending />);
 fireEvent.click(screen.getByRole("button", { name: /Sorunun tamamını oku/ }));
 expect((screen.getByRole("button", { name: "Onayla" }) as HTMLButtonElement).disabled).toBe(true);
});
