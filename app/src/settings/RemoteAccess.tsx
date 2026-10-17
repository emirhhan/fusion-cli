import { useCallback, useEffect, useState, type ReactNode } from "react";
import type { ProtocolClient } from "../protocol/client";
import { errorMessage } from "../protocol/result";
import { Button } from "../ui/Button";
import { ChoiceCards, Field, PanelGroup, PanelIntro, StatusPill, ToggleRow } from "./PanelParts";
import { TunnelGuide } from "./RemoteGuide";

/**
 * Uzaktan Erişim — telefon (PWA) ve Telegram eşleştirme.
 *
 * Güvenlik kuralı: yüksek yetkili kapsamlar varsayılan KAPALI ve açıkça seçilir;
 * riskli işlemler uzaktan onaylanamaz, onay burada (masaüstünde) verilir.
 */

interface Device { deviceId: string; name: string; channel: string; scopes: string[]; revoked: boolean }
interface ScreenDevice { cihazId: string; ad: string }
interface Pending { soruId: string; runId: string; baslik: string; hedef: string; onay: boolean }
interface Status {
  dinliyor: boolean; adres: string; telegram: boolean; telegramHata: string; cihazSayisi: number;
  port: number; agAdresleri: string[];
}

type Mode = "local" | "tunnel" | "lan";

const ELEVATED = [
  { id: "project.write", etiket: "Proje dosyalarını değiştirme" },
  { id: "desktop.observe", etiket: "Ekranı görme (telefonda canlı ekran)" },
  { id: "desktop.control", etiket: "Masaüstünü kontrol etme" },
  { id: "production.deploy", etiket: "Üretime yayın" },
];

export function RemoteAccess({ client }: { client: ProtocolClient }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [pending, setPending] = useState<Pending[]>([]);
  const [screenAsks, setScreenAsks] = useState<ScreenDevice[]>([]);
  const [screenLive, setScreenLive] = useState<ScreenDevice[]>([]);
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
      const screen = await call("uzak.ekran_bekleyen");
      setScreenAsks((screen.bekleyen ?? []) as ScreenDevice[]);
      setScreenLive((screen.etkin ?? []) as ScreenDevice[]);
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

  const listening = Boolean(status?.dinliyor);
  const rows = (title: string, empty: string, items: unknown[], body: ReactNode) => (
    <PanelGroup title={title}>{items.length === 0 ? <p className="px-empty">{empty}</p> : body}</PanelGroup>
  );
  return (
    <article className="settings__card" id="settings-remote">
      <PanelIntro title="Uzaktan Erişim">
        Görevler bu bilgisayarda çalışır; uyku, kilit veya kapalı bilgisayarda ilerlemez. Riskli işlemler
        (masaüstü kontrolü, dış servis yazma, silme) yalnız burada onaylanır.
      </PanelIntro>
      {message && <p className="px-error" role="alert">{message}</p>}

      <PanelGroup title="Telefon (PWA)">
        <div className="px-item">
          <div className="px-item__text">
            <span className="px-item__title">{listening ? "Dinleniyor" : "Kapalı"}</span>
            <p className="px-item__hint">
              {listening ? status?.adres : "Yalnız bu bilgisayardan erişim var."}
            </p>
          </div>
          <StatusPill tone={listening ? "on" : "off"}>{listening ? "Açık" : "Kapalı"}</StatusPill>
        </div>
      </PanelGroup>

      <ChoiceCards
        legend="Erişim türü"
        name="remote-mode"
        onChange={(value) => setMode(value as Mode)}
        options={[
          { value: "local", title: "Yalnız bu bilgisayar (127.0.0.1)", description: "Dışarıdan erişim yok." },
          {
            value: "tunnel",
            title: "Özel tünel (Tailscale / Cloudflare) — önerilen",
            description: "HTTPS'i tünel sağlar; kimseye açık adres vermezsin.",
          },
          {
            value: "lan",
            title: "Yerel ağ (Wi‑Fi), kendi HTTPS sertifikanla",
            description: "Aynı Wi‑Fi'daki cihazlar; sertifika gerekir.",
          },
        ]}
        value={mode}
      />

      <Field label="Port">
        {(id) => <input id={id} inputMode="numeric" onChange={(event) => setPort(event.target.value)} value={port} />}
      </Field>
      {mode === "lan" && (
        <>
          <Field label="Bu bilgisayarın yerel ağ adresi">
            {(id) => (
              <select id={id} onChange={(event) => setLanAddress(event.target.value)} value={lanAddress}>
                <option value="">Seç…</option>
                {(status?.agAdresleri ?? []).map((address) => (
                  <option key={address} value={address}>{address}</option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Sertifika dosyası (.pem)">
            {(id) => <input id={id} onChange={(event) => setCertificate(event.target.value)} value={certificate} />}
          </Field>
          <Field
            hint="Şifresiz yerel ağ dinlemesi kapalıdır. Telefonun güvendiği bir sertifika gerekir (ör. mkcert ile üretilip telefona kurulmuş)."
            label="Anahtar dosyası (.pem)"
          >
            {(id) => <input id={id} onChange={(event) => setKeyFile(event.target.value)} value={keyFile} />}
          </Field>
        </>
      )}
      <div className="px-actions">
        <Button
          disabled={listening || (mode === "lan" && (!lanAddress || !certificate || !keyFile))}
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
        </Button>
        <Button disabled={!listening} onClick={() => act(async () => { await call("uzak.durdur"); })}>
          Durdur
        </Button>
      </div>

      {mode === "tunnel" && <TunnelGuide port={port} />}

      <PanelGroup note="Varsayılan kapalı. Yalnız ihtiyacın olanı aç." title="Ek yetkiler">
        {ELEVATED.map((item) => (
          <ToggleRow
            checked={extra.includes(item.id)}
            key={item.id}
            onChange={(checked) => setExtra(checked ? [...extra, item.id] : extra.filter((id) => id !== item.id))}
            title={item.etiket}
          />
        ))}
      </PanelGroup>
      <div className="px-actions">
        <Button onClick={() => begin("pwa")}>Telefon için eşleştirme kodu oluştur</Button>
        <Button onClick={() => begin("telegram")}>Telegram için kod oluştur</Button>
      </div>
      {code && (
        <div className="px-pairing" role="status">
          <p className="px-note">Eşleştirme kodu (2 dakika geçerli)</p>
          <strong className="px-pairing__code">{code.kod}</strong>
          <p className="px-note">Cihaz kodu girdikten sonra onayla.</p>
          <div className="px-actions" style={{ justifyContent: "center" }}>
            <Button onClick={() => act(async () => { await call("uzak.eslestir_onayla", { kod: code.kod }); setCode(null); })}>
              Cihazı onayla
            </Button>
            <Button onClick={() => act(async () => { await call("uzak.eslestir_reddet", { kod: code.kod }); setCode(null); })}>
              Reddet
            </Button>
          </div>
        </div>
      )}

      <PanelGroup
        note="Telegram bot sohbeti uçtan uca şifreli değildir. Parola veya anahtar yazma. Belirteç sistem anahtarlığında saklanır."
        title="Telegram botu"
      >
        <div className="px-item">
          <div className="px-item__text">
            <span className="px-item__title">{status?.telegram ? "Bağlı" : "Bağlı değil"}</span>
            <p className="px-item__hint">
              {status?.telegram ? "Dışarı bağlantı kurar; port açılmaz." : "BotFather'dan aldığın belirteci gir."}
            </p>
          </div>
          <StatusPill tone={status?.telegram ? "on" : "off"}>{status?.telegram ? "Açık" : "Kapalı"}</StatusPill>
        </div>
      </PanelGroup>
      {status?.telegramHata && <p className="px-error" role="alert">{status.telegramHata}</p>}
      <Field label="Bot belirteci (BotFather)">
        {(id) => (
          <input autoComplete="off" id={id} onChange={(event) => setToken(event.target.value)} type="password" value={token} />
        )}
      </Field>
      <div className="px-actions">
        <Button onClick={() => act(async () => { await call("uzak.telegram_baglan", { belirtec: token }); setToken(""); })}>
          Bağlan
        </Button>
        <Button onClick={() => act(async () => { await call("uzak.telegram_kes"); })}>Bağlantıyı kes ve sil</Button>
      </div>

      {rows(
        "Bekleyen onaylar",
        "Bekleyen onay yok.",
        pending,
        pending.map((item) => (
          <div className="px-item" key={item.soruId}>
            <div className="px-item__text">
              <span className="px-item__title">{item.baslik || "Onay gerekiyor"}</span>
              {item.hedef && <p className="px-item__hint">{item.hedef}</p>}
              {!item.onay && <p className="px-item__hint">Bu soru uzaktaki cihazdan yanıtlanır.</p>}
            </div>
            {item.onay && (
              <div className="px-item__actions">
                <Button onClick={() => act(async () => { await call("uzak.onay_cevapla", { soruId: item.soruId, secim: "once" }); })}>
                  Bir kez izin ver
                </Button>
                <Button onClick={() => act(async () => { await call("uzak.onay_cevapla", { soruId: item.soruId, secim: "deny" }); })}>
                  Reddet
                </Button>
              </div>
            )}
          </div>
        )),
      )}

      {rows(
        "Ekran paylaşımı",
        "Ekran isteği yok.",
        [...screenAsks, ...screenLive],
        <>
          {screenAsks.map((item) => (
            <div className="px-item" key={item.cihazId}>
              <div className="px-item__text">
                <span className="px-item__title">{item.ad} ekranını görmek istiyor</span>
                <p className="px-item__hint">5 dakika, saniyede ~2 kare.</p>
              </div>
              <div className="px-item__actions">
                <Button onClick={() => act(async () => { await call("uzak.ekran_onayla", { cihazId: item.cihazId }); })}>
                  Ekranı göstermeye izin ver
                </Button>
                <Button onClick={() => act(async () => { await call("uzak.ekran_kes", { cihazId: item.cihazId }); })}>
                  Reddet
                </Button>
              </div>
            </div>
          ))}
          {screenLive.map((item) => (
            <div className="px-item" key={item.cihazId} role="status">
              <div className="px-item__text">
                <span className="px-item__title">{item.ad}</span>
                <p className="px-item__hint">şu an ekranını görüyor.</p>
              </div>
              <Button onClick={() => act(async () => { await call("uzak.ekran_kes", { cihazId: item.cihazId }); })}>
                Paylaşımı kes
              </Button>
            </div>
          ))}
        </>,
      )}

      {rows(
        "Eşleşmiş cihazlar",
        "Cihaz yok.",
        devices,
        devices.map((device) => (
          <div className="px-item" key={device.deviceId}>
            <div className="px-item__text">
              <span className="px-item__title">{device.name}</span>
              <p className="px-item__hint">{device.channel === "telegram" ? "Telegram" : "PWA"}</p>
            </div>
            <div className="px-item__actions">
              <StatusPill tone={device.revoked ? "off" : "on"}>{device.revoked ? "iptal" : "aktif"}</StatusPill>
              {!device.revoked && (
                <Button onClick={() => act(async () => { await call("uzak.cihaz_iptal", { cihazId: device.deviceId }); })}>
                  Erişimi iptal et
                </Button>
              )}
            </div>
          </div>
        )),
      )}
    </article>
  );
}
