import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { ProtocolClient } from "../protocol/client";
import { ChangesPanel } from "./ChangesPanel";

afterEach(cleanup);

it("geri almayı ikinci açık onay gelmeden çalıştırmaz", async () => {
  let receive: ((line: string) => void) | null = null;
  const requests: string[] = [];
  const client = new ProtocolClient(
    (line) => {
      const request = JSON.parse(line) as { id: string; ad: string };
      requests.push(request.ad);
      const veri = request.ad === "proje.degisiklikler"
        ? {
            ok: true,
            degisiklikler: [{
              yol: "app.py",
              diff: "-old\n+new",
              added: 1,
              removed: 1,
              geri_alinabilir: true,
            }],
          }
        : { ok: true };
      queueMicrotask(() => receive?.(JSON.stringify({ tip: "sonuc", id: request.id, veri })));
    },
    (handler) => {
      receive = handler;
    },
  );

  render(<ChangesPanel client={client} revision={0} />);
  fireEvent.click(await screen.findByRole("button", { name: "Bu dosyayı geri al" }));
  expect(requests).not.toContain("proje.geri_al");

  fireEvent.click(screen.getByRole("button", { name: "Geri almayı onayla" }));
  await waitFor(() => expect(requests).toContain("proje.geri_al"));
});
