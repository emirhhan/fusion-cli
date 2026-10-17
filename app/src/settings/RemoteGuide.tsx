import { useState } from "react";
import { Button } from "../ui/Button";
import { PanelGroup } from "./PanelParts";

/**
 * Telefon erişimi için kurulum rehberi.
 *
 * Kullanıcının terminalle işi olmasın diye her adımda NEREDEN ve NE yapılacağı yazar.
 * Tünel kipinde Tailscale kullanılır: telefona ve bilgisayara aynı hesapla kurulur,
 * HTTPS sertifikasını Tailscale üretir, Fusion'a bir kez `serve` komutu verilir.
 */

const TAILSCALE_DOWNLOAD = "tailscale.com/download";

/** Mac uygulamasıyla kurulan Tailscale'in komut satırı, PATH'te olmayabilir. */
const MAC_CLI = "/Applications/Tailscale.app/Contents/MacOS/Tailscale";

export function serveCommand(port: string): string {
  return `tailscale serve --bg --https=443 http://127.0.0.1:${port || "8791"}`;
}

function CopyLine({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      // Pano kullanılamıyorsa metin zaten seçilebilir durur.
      setCopied(false);
    }
  };
  return (
    <div className="px-code">
      <code>{text}</code>
      <Button onClick={() => void copy()}>{copied ? "Kopyalandı" : "Kopyala"}</Button>
    </div>
  );
}

export function TunnelGuide({ port }: { port: string }) {
  return (
    <PanelGroup
      note="Bir kez yapılır. Sonrasında telefonun ana ekranında Fusion simgesi olur."
      title="Telefon kurulum rehberi (Tailscale)"
    >
      <ol className="px-steps">
        <li className="px-step">
          <span className="px-step__title">Tailscale'i bilgisayara ve telefona kur</span>
          <p className="px-step__body">
            Bilgisayar için {TAILSCALE_DOWNLOAD} adresinden, telefon için App Store veya Google Play'den "Tailscale"
            uygulamasını indir. İkisinde de AYNI hesapla (Google, Microsoft veya Apple) giriş yap. Ücretsiz plan yeterli.
          </p>
        </li>
        <li className="px-step">
          <span className="px-step__title">HTTPS'i bir kez aç</span>
          <p className="px-step__body">
            login.tailscale.com/admin/dns sayfasında "MagicDNS" ve "HTTPS Certificates" seçeneklerini etkinleştir.
            Telefonun güvenli (https) bir adres alması için gerekli.
          </p>
        </li>
        <li className="px-step">
          <span className="px-step__title">Aşağıdan "Dinlemeyi başlat"a bas</span>
          <p className="px-step__body">Fusion bu bilgisayarda yalnız kendi içinden (127.0.0.1) dinler; dışarı açılmaz.</p>
        </li>
        <li className="px-step">
          <span className="px-step__title">Bu komutu terminalde bir kez çalıştır</span>
          <p className="px-step__body">
            Tailscale, Fusion'ı sadece senin cihazlarına şifreli olarak yayınlar.
          </p>
          <CopyLine text={serveCommand(port)} />
          <p className="px-step__body">
            "komut bulunamadı" derse Mac uygulaması için komutun başındaki <em>tailscale</em> yerine{" "}
            <code>{MAC_CLI}</code> yaz.
          </p>
        </li>
        <li className="px-step">
          <span className="px-step__title">Telefonda adresi aç</span>
          <p className="px-step__body">
            Terminalin yazdığı https adresini (ör. bilgisayar-adi.tailnet-xxxx.ts.net) telefonda aç, "Ana Ekrana Ekle"yi
            seç. Sonra aşağıdan eşleştirme kodu oluştur, telefona gir ve burada onayla.
          </p>
        </li>
      </ol>
    </PanelGroup>
  );
}
