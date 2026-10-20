import { expect, it, vi } from "vitest";
import { syncWindowChrome } from "./windowChrome";
it("macOS trafik ışığı payını tam ekran değişiminde günceller ve dinleyiciyi kaldırır",async()=>{
 let full=false;let resize=()=>{};const unlisten=vi.fn();const root=document.createElement('div');
 const stop=await syncWindowChrome({isFullscreen:async()=>full,onResized:async(fn)=>{resize=fn;return unlisten;}},root);
 expect(root.dataset.fusionTitlebarInset).toBe('true');
 full=true;resize();await Promise.resolve();
 expect(root.dataset.fusionTitlebarInset).toBeUndefined();
 full=false;resize();await Promise.resolve();expect(root.dataset.fusionTitlebarInset).toBe('true');
 stop();expect(unlisten).toHaveBeenCalledOnce();
});
