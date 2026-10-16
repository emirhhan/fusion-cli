import { describe, expect, it } from "vitest";
import { localVoiceReply } from "./localVoice";
import { routeWakeSpeech } from "./wake";
describe("yerel ses niyeti", () => {
 it.each(["Merhaba Füzyon!", "Fusion merhaba", "Selam", "Nasılsın füzyon?", "Beni duyuyor musun?"])("hazır yanıt %s", text => expect(localVoiceReply(text)).toBeTruthy());
 it.each(["Merhaba füzyon projeyi aç", "teşekkürler ama devam et", "evet", "hayır", "merhaba dosyasını sil"])("görevi yutmaz %s", text => expect(localVoiceReply(text)).toBeNull());
 it("merhaba füzyon beklemeden uyanır ve mesaj kaybolmaz", () => expect(routeWakeSpeech("Merhaba Füzyon", false).message).toBe("Merhaba Füzyon"));
 it("hitaplı gerçek isteği model için korur", () => expect(routeWakeSpeech("Merhaba Füzyon projeyi aç", false).message).toBe("projeyi aç"));
});
