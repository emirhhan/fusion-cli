import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { GuideTour } from "./GuideTour";
import { readSeen } from "./progress";
import { ONBOARDING_TOPICS } from "./topics";

const client = { request: vi.fn(async () => ({ ok: true, araclar: [] })) } as unknown as ProtocolClient;
beforeEach(() => window.localStorage.clear());
afterEach(cleanup);

it("ilk konuyu görseliyle gösterir ve Sonraki konu ile ilerler", () => {
  render(<GuideTour client={client} />);
  const first = ONBOARDING_TOPICS[0];
  expect(screen.getByRole("heading", { name: first.title, level: 3 })).toBeTruthy();
  expect(screen.getByRole("img", { name: first.imageAlt }).getAttribute("src")).toBe(`/guide/${first.image}.webp`);
  fireEvent.click(screen.getByRole("button", { name: "Sonraki konu" }));
  expect(screen.getByRole("heading", { name: ONBOARDING_TOPICS[1].title, level: 3 })).toBeTruthy();
  expect(readSeen().has(first.id)).toBe(true);
});

it("konu sekmesine tıklamak görülmüş saymaz; atlanan konu bekleyen kalır", () => {
  render(<GuideTour client={client} />);
  fireEvent.click(screen.getByRole("button", { name: "Chrome eklentisi" }));
  expect(screen.getByText(/Erişilebilirlik/)).toBeTruthy();
  expect(readSeen().size).toBe(0);
  expect(screen.getByText(new RegExp(`${ONBOARDING_TOPICS.length} konu bakılmadı`))).toBeTruthy();
});

it("Gördüm düğmesi konuyu kaydeder", () => {
  render(<GuideTour client={client} />);
  fireEvent.click(screen.getByRole("button", { name: "Gördüm" }));
  expect(readSeen().has(ONBOARDING_TOPICS[0].id)).toBe(true);
});
