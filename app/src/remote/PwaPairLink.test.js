import { expect, it } from "vitest";
import { pairingCodeFromSearch, stripPairingCode } from "../../../src/fusion_cli/remote/pwa/pair-link.js";

// Ölçüldü (31 Ekim): PWA eşleştirme kodunu yalnız elle alıyordu; terminal QR'ındaki `?kod=` okunmuyordu.
it("adresteki ?kod= büyük harfe çevrilip doğrulanır, bozuk değer yok sayılır", () => {
  expect(pairingCodeFromSearch("?kod=abcd2345")).toBe("ABCD2345");
  expect(pairingCodeFromSearch("?x=1&kod=ABCD2345")).toBe("ABCD2345");
  expect(pairingCodeFromSearch("?kod=abc")).toBe("");
  expect(pairingCodeFromSearch("?kod=<script>")).toBe("");
  expect(pairingCodeFromSearch("")).toBe("");
});

it("kod adresten silinir ki geçmişte ve paylaşımda kalmasın", () => {
  expect(stripPairingCode("https://mac.ts.net/?kod=ABCD2345")).toBe("https://mac.ts.net/");
  expect(stripPairingCode("https://mac.ts.net/?a=1&kod=ABCD2345")).toBe("https://mac.ts.net/?a=1");
});
