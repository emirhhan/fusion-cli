import { useCallback, useEffect, useState } from "react";
import { nativePermissionBridge } from "../platform/permissions";
import type { ProtocolClient } from "../protocol/client";
import { Button } from "../ui/Button";
import type { PermissionBridge } from "./types";
import "./permissions.css";

/**
 * Bu bilgisayar — Fusion'ın masaüstünü kullanabilmesi için gereken macOS izinleri (P-005).
 *
 * Durum ÇEKİRDEKTEN okunur (`izin.masaustu_durum`): masaüstü araçlarını koşturan süreç
 * sidecar'dır; Tauri sürecinin gördüğü durum değil, araçların göreceği durum gösterilir.
 * "İzin iste" sistem penceresini açar; Ekran Kaydı için macOS izin sonrası yeniden açılış ister.
 */

type Durum = "granted" | "denied" | "unsupported" | "unknown";

interface MasaustuIzinDurumu {
  accessibility: Durum;
  screen_recording: Durum;
  platform: string;
}

const SATIRLAR: { anahtar: keyof Omit<MasaustuIzinDurumu, "platform">; kind: "accessibility" | "screenRecording"; baslik: string; aciklama: string }[] = [
  { anahtar: "accessibility", kind: "accessibility", baslik: "Erişilebilirlik", aciklama: "Tıklama, yazma ve kaydırma için." },
  { anahtar: "screen_recording", kind: "screenRecording", baslik: "Ekran Kaydı", aciklama: "Ekranı görmek (ekran görüntüsü) için." },
];

const DURUM_METNI: Record<Durum, string> = {
  granted: "Verildi",
  denied: "Verilmedi",
  unsupported: "Bu sistemde yok",
  unknown: "Bilinmiyor",
};

function durumOku(value: unknown): Durum {
  return value === "granted" || value === "denied" || value === "unsupported" ? value : "unknown";
}

export function ComputerUse({
  client,
  permissionBridge = nativePermissionBridge,
}: {
  client: Pick<ProtocolClient, "request">;
  permissionBridge?: Pick<PermissionBridge, "openSettings">;
}) {
  const [durum, setDurum] = useState<MasaustuIzinDurumu | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const yenile = useCallback(async () => {
    try {
      const payload = await client.request("izin.masaustu_durum", {});
      if (payload.ok !== true) throw new Error(String(payload.metin ?? "İzin durumu alınamadı."));
      setDurum({
        accessibility: durumOku(payload.accessibility),
        screen_recording: durumOku(payload.screen_recording),
        platform: String(payload.platform ?? ""),
      });
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }, [client]);

  useEffect(() => {
    void yenile();
  }, [yenile]);

  const iste = async (tur: "accessibility" | "screen_recording") => {
    setBusy(tur);
    try {
      const payload = await client.request("izin.masaustu_iste", { tur });
      if (payload.ok !== true) throw new Error(String(payload.metin ?? "İzin istenemedi."));
      await yenile();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(null);
    }
  };

  const ayarAc = async (kind: "accessibility" | "screenRecording") => {
    try {
      await permissionBridge.openSettings(kind);
    } catch {
      setError("Sistem Ayarları açılamadı. Gizlilik ve Güvenlik bölümünü elle açın.");
    }
  };

  const desteklenmiyor = durum !== null && durum.platform !== "macos";

  return (
    <article className="settings__card" data-testid="computer-use">
      <div className="settings__card-head">
        <div>
          <h3>Bu bilgisayar</h3>
          <p className="settings__hint">
            Fusion'ın masaüstünü kullanması (ekranı görme, tıklama, yazma) için iki macOS izni gerekir.
            Her masaüstü eylemi yine onay kartından geçer.
          </p>
        </div>
        <Button onClick={() => void yenile()} variant="secondary">Durumu yenile</Button>
      </div>
      {error && <p className="settings__warning" role="alert">{error}</p>}
      {desteklenmiyor && <p className="settings__hint">Masaüstü kontrolü şu anda yalnız macOS'ta kullanılabilir.</p>}
      {!desteklenmiyor && (
        <dl className="computer-use__list">
          {SATIRLAR.map((satir) => {
            const deger = durum?.[satir.anahtar] ?? "unknown";
            return (
              <div className="computer-use__row" data-state={deger} key={satir.anahtar}>
                <dt>
                  <strong>{satir.baslik}</strong>
                  <small>{satir.aciklama}</small>
                </dt>
                <dd>
                  <span className="computer-use__state" role="status">{DURUM_METNI[deger]}</span>
                  {deger !== "granted" && (
                    <>
                      <Button disabled={busy !== null} onClick={() => void iste(satir.anahtar)} variant="primary">
                        {busy === satir.anahtar ? "İsteniyor…" : "İzin iste"}
                      </Button>
                      <Button onClick={() => void ayarAc(satir.kind)} variant="secondary">Sistem Ayarlarını Aç</Button>
                    </>
                  )}
                </dd>
              </div>
            );
          })}
        </dl>
      )}
      {durum?.screen_recording === "denied" && (
        <p className="settings__hint">Ekran Kaydı izni verdikten sonra Fusion'ı yeniden açman gerekebilir.</p>
      )}
    </article>
  );
}
