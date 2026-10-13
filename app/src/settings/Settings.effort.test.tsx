import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { Settings } from "./Settings";

const snapshot = (effort: string, verified = true) => ({
  ok: true,
  model: { agent: "offline/model", hakem: "", adaylar: [], saglayici: "offline",
    yogunluk: effort, desteklenen_yogunluklar: ["high", "low"], yogunluk_dogrulandi: verified },
});
const mount = (client: ProtocolClient, onRunCommand: (command: string) => Promise<{ok:boolean;message?:string} | void>) =>
  render(<Settings client={client} initialSection="modeller" onClose={vi.fn()} onThemeChange={vi.fn()} themePreference="light" onRunCommand={onRunCommand} />);
afterEach(cleanup);

describe("Settings: effort lifecycle", () => {
  it("waits for a successful command and refreshes the authoritative value", async () => {
    let effort = "auto";
    const client = { request: vi.fn(async () => snapshot(effort)) } as unknown as ProtocolClient;
    const run = vi.fn(async (command: string) => {
      expect(command).toBe("/effort high"); effort = "high"; return {ok:true};
    });
    mount(client, run);
    const select = await screen.findByRole("combobox", { name: "Düşünme yoğunluğu" });
    fireEvent.change(select, {target: {value:"high"}});
    await waitFor(() => expect((select as HTMLSelectElement).value).toBe("high"));
    expect(client.request).toHaveBeenCalledTimes(2);
    expect(run).toHaveBeenCalledTimes(1);
  });
  it("retains the old value and displays a retry after failure", async () => {
    const client = { request: vi.fn(async () => snapshot("auto")) } as unknown as ProtocolClient;
    const run = vi.fn(async () => ({ok:false,message:"Yetki reddedildi"}));
    mount(client, run);
    const select = await screen.findByRole("combobox", {name:"Düşünme yoğunluğu"});
    fireEvent.change(select, {target:{value:"high"}});
    await screen.findByText("Yetki reddedildi");
    expect((select as HTMLSelectElement).value).toBe("auto");
    fireEvent.click(screen.getByRole("button",{name:"Yeniden dene"}));
    await waitFor(() => expect(run).toHaveBeenCalledTimes(2));
  });
  it("prevents another request while pending", async () => {
    const client = {request:vi.fn(async () => snapshot("auto"))} as unknown as ProtocolClient;
    const run = vi.fn(() => new Promise<void>(()=>undefined));
    mount(client, run);
    const select = await screen.findByRole("combobox",{name:"Düşünme yoğunluğu"});
    fireEvent.change(select,{target:{value:"high"}});
    await waitFor(() => expect((select as HTMLSelectElement).disabled).toBe(true));
    fireEvent.change(select,{target:{value:"low"}});
    expect(run).toHaveBeenCalledTimes(1);
  });
  it("does not offer unverified model effort choices", async () => {
    const client={request:vi.fn(async()=>snapshot("auto",false))} as unknown as ProtocolClient;
    mount(client,vi.fn());
    await screen.findByText(/Model desteği doğrulanmadı/);
    expect(screen.queryByRole("combobox",{name:"Düşünme yoğunluğu"})).toBeNull();
  });
});
