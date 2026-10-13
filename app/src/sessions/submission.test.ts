import { expect, it } from "vitest";
import { normalizeSubmissionReceipt, submissionAccepted } from "./submission";

it("receipt object truthiness reddedilmiş gönderimi kabul saymaz", () => {
  const receipt = normalizeSubmissionReceipt({gonderim_id: "r", oturum_id: "s", tur_id: "r:1", durum: "failed", hata_kodu: "executor_failed", gelecekteki_alan: true});
  expect(receipt).not.toBeNull();
  expect(submissionAccepted(receipt!)).toBe(false);
  expect(normalizeSubmissionReceipt({gonderim_id: "r", oturum_id: "s", durum: "bilinmeyen_kritik_durum"})).toBeNull();
  expect(submissionAccepted(undefined)).toBe(true);
});
