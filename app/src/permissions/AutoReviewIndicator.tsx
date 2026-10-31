import { useCallback, useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import type { ApprovalMode } from "../screens/ApprovalModeMenu";
import "./permissions.css";

/** `oto.durum` cevabı (P-011); alanlar çekirdekteki `auto_review_rpc.status_payload` ile aynı. */
export interface AutoReviewStatus {
  ok?: boolean;
  metin?: string;
  mod?: string;
  ayar?: "off" | "ask_only" | "on";
  ayar_etiketi?: string;
  model?: string;
  ardisik?: number;
  toplam?: number;
  esik_ardisik?: number;
  esik_toplam?: number;
  dusus_sayisi?: number;
  dustu?: boolean;
  dusus_nedeni?: string;
  model_erisilemiyor?: boolean;
  son_kararlar?: AutoReviewDecision[];
}

export interface AutoReviewDecision {
  arac: string;
  karar: "guvenli" | "riskli";
  karar_etiketi: string;
  kaynak: string;
  ozet: string;
  gerekce: string;
}

/** Durumu yeniden okutan olaylar: denetçi kararı ve kip düşüşü. */
const DENETCI_OLAYLARI = new Set(["AutoReviewDecided", "AutoModeFellBack"]);

type AutoReviewClient = Pick<ProtocolClient, "request"> & Partial<Pick<ProtocolClient, "onEvent">>;

/** `oto.durum`'u okur ve denetçi olaylarında tazeler; bileşenler arasında ortak kanca. */
export function useAutoReviewStatus(client: AutoReviewClient | undefined) {
  const [status, setStatus] = useState<AutoReviewStatus | null>(null);
  const owner = useRef(0);

  const load = useCallback(async () => {
    if (!client) return;
    const generation = owner.current;
    try {
      const payload = (await client.request("oto.durum", {})) as AutoReviewStatus;
      if (generation === owner.current && payload?.ok !== false) setStatus(payload);
    } catch {
      // Eski çekirdek `oto.*` bilmeyebilir; gösterge sessizce gizli kalır.
    }
  }, [client]);

  useEffect(() => {
    const generation = ++owner.current;
    setStatus(null);
    void load();
    const off = client?.onEvent?.((veri) => {
      if (DENETCI_OLAYLARI.has(String(veri.olay))) void load();
    });
    return () => {
      owner.current = generation + 1;
      off?.();
    };
  }, [client, load]);

  const resume = useCallback(async (): Promise<AutoReviewStatus | null> => {
    if (!client) return null;
    try {
      const payload = (await client.request("oto.devam", {})) as AutoReviewStatus;
      if (payload?.ok === false) return null;
      setStatus(payload);
      return payload;
    } catch {
      return null;
    }
  }, [client]);

  return { status, reload: load, resume, setStatus };
}

/**
 * Composer'daki izin modu yanında denetçi göstergesi (P-011).
 *
 * Otomatik kipte denetçi açıksa sönük "Denetçi" rozeti (ipucunda model ve engel sayacı);
 * oturum engel eşiğini aşıp Manuel'e düştüyse uyarı ve "Otomatik'e dön" düğmesi.
 */
export function AutoReviewIndicator({
  client,
  approval,
  onResumed,
}: {
  client?: AutoReviewClient;
  approval: ApprovalMode;
  /** `oto.devam` başarılı: üst bileşen izin modunu "auto" olarak benimser. */
  onResumed?: () => void;
}) {
  const { status, resume } = useAutoReviewStatus(client);
  const [busy, setBusy] = useState(false);
  if (!status) return null;

  // Uyarı yalnız düşüşün bıraktığı Manuel kipte: kullanıcı Plan/İzinleri atla seçtiyse
  // "Manuel'e düştü" demek yanıltır (çekirdek de bayrağı o kiplerde kaldırır).
  if (status.dustu && approval === "security") {
    const back = async () => {
      setBusy(true);
      const result = await resume();
      setBusy(false);
      if (result?.mod === "auto") onResumed?.();
    };
    return (
      <span className="auto-review auto-review--fell-back" role="status">
        <span className="auto-review__text" title={status.dusus_nedeni}>
          Otomatik → Manuel'e düştü
        </span>
        <button className="auto-review__action" disabled={busy} onClick={() => void back()} type="button">
          Otomatik'e dön
        </button>
      </span>
    );
  }

  if (approval !== "auto" || !status.ayar || status.ayar === "off") return null;
  const sayac = `engel ${status.ardisik ?? 0}/${status.esik_ardisik ?? 3} üst üste, ${status.toplam ?? 0}/${status.esik_toplam ?? 20} toplam`;
  const ipucu = [
    `Otomatik kip denetçisi: ${status.ayar_etiketi ?? status.ayar}`,
    `Model: ${status.model ?? "hakem"}${status.model_erisilemiyor ? " (erişilemiyor, kurallar geçerli)" : ""}`,
    sayac,
  ].join("\n");
  return (
    <span
      aria-label={`Otomatik kip denetçisi açık; ${sayac}`}
      className="auto-review"
      data-offline={status.model_erisilemiyor ? "true" : undefined}
      title={ipucu}
    >
      Denetçi
    </span>
  );
}
