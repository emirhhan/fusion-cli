import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { useProcesses } from "./useProcesses";

afterEach(cleanup);

describe("useProcesses", () => {
  it("ProcessOutput olay parçalarını snapshot aynı kalsa da monoton akışta korur", async () => {
    let eventListener: ((event: Record<string, unknown>) => void) | null = null;
    const client = {
      onEvent: vi.fn((listener: (event: Record<string, unknown>) => void) => {
        eventListener = listener;
        return () => { eventListener = null; };
      }),
      request: vi.fn(async () => ({ ok: true, surecler: [] })),
    } as unknown as ProtocolClient;

    function Probe() {
      const state = useProcesses(client);
      const stream = state.outputStreams.dev;
      return <output>{stream ? `${stream.total}:${stream.text}` : "boş"}</output>;
    }

    render(<Probe />);
    await waitFor(() => expect(client.request).toHaveBeenCalledWith("surec.listele", {}));
    act(() => {
      eventListener?.({ olay: "ProcessOutput", surec_id: "dev", metin: "xxx" });
      eventListener?.({ olay: "ProcessOutput", surec_id: "dev", metin: "xxx" });
    });

    expect(screen.getByText("6:xxxxxx")).toBeTruthy();
  });
});
