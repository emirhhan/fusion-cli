import { describe, expect, it } from "vitest";
import fixture from "./fixtures/task-contract.json";
import {
  OPERATION_OUTCOMES,
  RUN_STATUSES,
  TASK_SCHEMA_VERSION,
  TERMINAL_STATUSES,
  hasSequenceGap,
  isRunStatus,
  parseRunEvent,
  type RunEvent,
} from "./taskContract";

describe("görev sözleşmesi", () => {
  it("Python ile ortak fixture'a uyar", () => {
    expect(fixture.schema_version).toBe(TASK_SCHEMA_VERSION);
    expect([...RUN_STATUSES]).toEqual(fixture.run_statuses);
    expect([...TERMINAL_STATUSES].sort()).toEqual([...fixture.terminal_statuses].sort());
    expect([...OPERATION_OUTCOMES]).toEqual(fixture.operation_outcomes);
    expect(parseRunEvent(fixture.event_example)).not.toBeNull();
  });

  it("bilinmeyen durum ve bozuk olay kabul edilmez", () => {
    expect(isRunStatus("done")).toBe(false);
    expect(isRunStatus("needs_reconciliation")).toBe(true);
    expect(parseRunEvent({ ...fixture.event_example, seq: 0 })).toBeNull();
    expect(parseRunEvent({ ...fixture.event_example, schema_version: 2 })).toBeNull();
    expect(parseRunEvent({ ...fixture.event_example, payload: [] })).toBeNull();
  });

  it("tekrar eden olayı atlar, sıra boşluğunu bildirir", () => {
    const olay = (seq: number) => ({ ...fixture.event_example, seq }) as RunEvent;
    expect(hasSequenceGap(2, [olay(2), olay(3), olay(4)])).toBe(false);
    expect(hasSequenceGap(2, [olay(3), olay(5)])).toBe(true);
  });
});
