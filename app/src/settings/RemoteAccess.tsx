import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { errorMessage } from "../protocol/result";
import { Button } from "../ui/Button";

/**
 * Uzaktan Erişim — telefon (PWA) ve Telegram eşleştirme.
 *
 * Güvenlik kuralı: yüksek yetkili kapsamlar varsayılan KAPALI ve açıkça seçilir;
 * riskli işlemler uzaktan onaylanamaz, onay burada (masaüstünde) verilir.
 */

interface Device { deviceId: string; name: string; channel: string; scopes: string[]; revoked: boolean }
interface Pending { soruId: string; runId: string; baslik: string; hedef: string; onay: boolean }
interface Status {
  dinliyor: boolean; adres: string; telegram: boolean; telegramHata: string; cihazSayisi: number;
  port: number; agAdresleri: string[];
}

type Mode = "local" | "tunnel" | "lan";

const ELEVATED = [
  { id: "project.write", etiket: "Proje dosyalarını değiştirme" },
  { id: "desktop.control", etiket: "Masaüstünü kontrol etme" },
  { id: "production.deploy", etiket: "Üretime yayın" },
];

export function RemoteAccess({ client }: { client: ProtocolClient }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [pending, setPending] = useState<Pending[]>([]);
  const [code, setCode] = useState<{ kod: string; kanal: string } | null>(null);
  const [extra, setExtra] = useState<string[]>([]);
  const [token, setToken] = useState("");
  const [mode, setMode] = useState<Mode>("tunnel");
  const [port, setPort] = useState("8791");
  const [lanAddress, setLanAddress] = useState("");
  const [certificate, setCertificate] = useState("");
  const [keyFile, setKeyFile] = useState("");
  const [message, setMessage] = useState("");

  const call = useCallback(
    async (name: string, data: Record<string, unknown> = {}) => {
      const result = await client.request(name, data);
      if (result.ok !== true) throw new Error(String(result.metin ?? "İşlem başarısız."));
      return result;
    },
    [client],
  );

  const reload = useCallback(async () => {
    try {
      setStatus((await call("uzak.durum")) as unknown as Status);
      setDevices(((await call("uzak.cihazlar")).cihazlar ?? []) as Device[]);
      setPending(((await call("uzak.bekleyen")).sorular ?? []) as Pending[]);
    } catch (reason) {
      setMessage(errorMessage(reason));
    }
  }, [call]);

  useEffect(() => {
    void reload();
    const timer = window.setInterval(() => void reload(), 4000);
    return () => window.clearInterval(timer);
  }, [reload]);

  const act = async (work: () => Promise<void>) => {
    try {
      setMessage("");
      await work();
      await reload();
    } catch (reason) {
      setMessage(errorMessage(reason));
    }
  };

  const begin = (kanal: "pwa" | "telegram") =>
    act(async () => {
      const base = ["project.read", "agent.run", "agent.cancel"];
      const result = await call("uzak.eslestir_baslat", { kanal, kapsamlar: [...base, ...extra] });
      setCode({ kod: String(result.kod), kanal });
    });

  return (
    <section aria-labelledby="remote-title" className="settings__panel">
      <h3 id="remote-title">Uzaktan Erişim</h3>
      <p className="settings__hint">
        Görevler bu bilgisayarda çalışır; uyku, kilit veya kapalı bilgisayarda ilerlemez. Riskli işlemler
        (masaüstü kontrolü, dış servis yazma, silme) yalnız burada onaylanır.
      </p>
      {message && <p role="alert">{message}</p>}

      <h4>Telefon (PWA)</h4>
      <p>{status?.dinliyor ? `Dinleniyor: ${status.adres}` : "Kapalı (yalnız bu bilgisayardan erişim)."}</p>
      <fieldset>
        <legend>Erişim türü</legend>
        <label style={{ display: "block" }}>
          <input type="radio" name="remote-mode" checked={mode === "local"} onChange={() => setMode("local")} /> Yalnız bu
          bilgisayar (127.0.0.1)
        </label>
        <label style={{ display: "block" }}>
          <input type="radio" name="remote-mode" checked={mode === "tunnel"} onChange={() => setMode("tunnel")} /> Özel tünel
          (Tailscale / Cloudflare) — önerilen, HTTPS’i tünel sağlar
        </label>
        <label style={{ display: "block" }}>
          <input type="radio" name="remote-mode" checked={mode === "lan"} onChange={() => setMode("lan")} /> Yerel ağ (Wi‑Fi),
          kendi HTTPS sertifikanla
        </label>
      </fieldset>
      <label htmlFor="remote-port">Port</label>
      <input id="remote-port" inputMode="numeric" value={port} onChange={(event) => setPort(event.target.value)} />
      {mode === "lan" && (
        <>
          <label htmlFor="remote-lan">Bu bilgisayarın yerel ağ adresi</label>
          <select id="remote-lan" value={lanAddress} onChange={(event) => setLanAddress(event.target.value)}>
            <option value="">Seç…</option>
            {(status?.agAdresleri ?? []).map((address) => (
              <option key={address} value={address}>{address}</option>
            ))}
          </select>
          <label htmlFor="remote-cert">Sertifika dosyası (.pem)</label>
          <input id="remote-cert" value={certificate} onChange={(event) => setCertificate(event.target.value)} />
          <label htmlFor="remote-key">Anahtar dosyası (.pem)</label>
          <input id="remote-key" value={keyFile} onChange={(event) => setKeyFile(event.target.value)} />
          <p className="settings__hint">
            Şifresiz yerel ağ dinlemesi kapalıdır. Telefonun güvendiği bir sertifika gerekir (ör. mkcert ile üretilip
            telefona kurulmuş).
          </p>
        </>
      )}
      <Button
        disabled={status?.dinliyor || (mode === "lan" && (!lanAddress || !certificate || !keyFile))}
        onClick={() =>
          act(async () => {
            const base: Record<string, unknown> = { port: Number(port) };
            if (mode === "tunnel") base.guvenilirTunel = true;
            if (mode === "lan") {
              Object.assign(base, { adres: lanAddress, yerelAg: true, sertifika: certificate, anahtar: keyFile });
            }
            await call("uzak.baslat", base);
          })
        }
      >
        Dinlemeyi başlat
      </Button>{" "}
      <Button onClick={() => act(async () => { await call("uzak.durdur"); })} disabled={!status?.dinliyor}>
        Durdur
      </Button>
      {mode === "tunnel" && (
        <div role="note">
          <p className="settings__hint">Tailscale ile (telefona da Tailscale kur), terminalde bir kez çalıştır:</p>
          <code>{`tailscale serve --bg --https=443 http://127.0.0.1:${port || "8791"}`}</code>
          <p className="settings__hint">Sonra telefonda Tailscale’in verdiği https adresini aç ve “Ana Ekrana Ekle”yi seç.</p>
        </div>
      )}

      <fieldset>
        <legend>Ek yetkiler (varsayılan kapalı)</legend>
        {ELEVATED.map((item) => (
          <label key={item.id} style={{ display: "block" }}>
            <input
              type="checkbox"
              checked={extra.includes(item.id)}
              onChange={(event) =>
                setExtra(event.target.checked ? [...extra, item.id] : extra.filter((id) => id !== item.id))
              }
            />{" "}
            {item.etiket}
          </label>
        ))}
      </fieldset>
      <Button onClick={() => begin("pwa")}>Telefon için eşleştirme kodu oluştur</Button>{" "}
      <Button onClick={() => begin("telegram")}>Telegram için kod oluştur</Button>
      {code && (
        <div role="status">
          <p>
            Kod: <strong>{code.kod}</strong> (2 dakika geçerli). Cihaz kodu girdikten sonra onayla.
          </p>
          <Button onClick={() => act(async () => { await call("uzak.eslestir_onayla", { kod: code.kod }); setCode(null); })}>
            Cihazı onayla
          </Button>{" "}
          <Button onClick={() => act(async () => { await call("uzak.eslestir_reddet", { kod: code.kod }); setCode(null); })}>
            Reddet
          </Button>
        </div>
      )}

      <h4>Telegram botu</h4>
      <p>{status?.telegram ? "Bağlı (dışarı bağlantı; port açılmaz)." : "Bağlı değil."}</p>
      {status?.telegramHata && <p role="alert">{status.telegramHata}</p>}
      <p className="settings__hint">
        Telegram bot sohbeti uçtan uca şifreli değildir. Parola veya anahtar yazma. Belirteç sistem anahtarlığında saklanır.
      </p>
      <label htmlFor="tg-token">Bot belirteci (BotFather)</label>
      <input id="tg-token" type="password" autoComplete="off" value={token} onChange={(event) => setToken(event.target.value)} />
      <Button onClick={() => act(async () => { await call("uzak.telegram_baglan", { belirtec: token }); setToken(""); })}>
        Bağlan
      </Button>{" "}
      <Button onClick={() => act(async () => { await call("uzak.telegram_kes"); })}>Bağlantıyı kes ve sil</Button>

      <h4>Bekleyen onaylar</h4>
      {pending.length === 0 && <p>Bekleyen onay yok.</p>}
      {pending.map((item) => (
        <div key={item.soruId} className="settings__card">
          <p>{item.baslik || "Onay gerekiyor"}</p>
          {item.hedef && <p className="settings__hint">{item.hedef}</p>}
          {item.onay ? (
            <>
              <Button onClick={() => act(async () => { await call("uzak.onay_cevapla", { soruId: item.soruId, secim: "once" }); })}>
                Bir kez izin ver
              </Button>{" "}
              <Button onClick={() => act(async () => { await call("uzak.onay_cevapla", { soruId: item.soruId, secim: "deny" }); })}>
                Reddet
              </Button>
            </>
          ) : (
            <p className="settings__hint">Bu soru uzaktaki cihazdan yanıtlanır.</p>
          )}
        </div>
      ))}

      <h4>Eşleşmiş cihazlar</h4>
      {devices.length === 0 && <p>Cihaz yok.</p>}
      <ul>
        {devices.map((device) => (
          <li key={device.deviceId}>
            {device.name} — {device.channel === "telegram" ? "Telegram" : "PWA"} — {device.revoked ? "iptal" : "aktif"}
            {!device.revoked && (
              <>
                {" "}
                <Button onClick={() => act(async () => { await call("uzak.cihaz_iptal", { cihazId: device.deviceId }); })}>
                  Erişimi iptal et
                </Button>
              </>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
