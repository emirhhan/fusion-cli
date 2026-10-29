import { expect, it } from "vitest";
import { nextAttemptTurnId, normalizeSubmissionReceipt, submissionAccepted } from "./submission";

it("receipt object truthiness reddedilmiş gönderimi kabul saymaz", () => {
  const receipt = normalizeSubmissionReceipt({gonderim_id: "r", oturum_id: "s", tur_id: "r:1", durum: "failed", hata_kodu: "executor_failed", gelecekteki_alan: true});
  expect(receipt).not.toBeNull();
  expect(submissionAccepted(receipt!)).toBe(false);
  expect(normalizeSubmissionReceipt({gonderim_id: "r", oturum_id: "s", durum: "bilinmeyen_kritik_durum"})).toBeNull();
  expect(submissionAccepted(undefined)).toBe(true);
});

// U4-05
it("yeniden deneme tur kimliği yalnız sayısal sonekten türer", () => {
  expect(nextAttemptTurnId("r", "r:1")).toBe("r:2");
  expect(nextAttemptTurnId("r", "r:41")).toBe("r:42");
  for (const bozuk of ["r:abc", "r:", "r", "başka:1", "r:1.5", "r:-1", "r:99999999999999999999", undefined]) {
    expect(nextAttemptTurnId("r", bozuk)).toBeUndefined();
  }
});
