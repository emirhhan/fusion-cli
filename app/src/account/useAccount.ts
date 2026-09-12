import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import type { Hesap, HesapDurumu, KayitSonucu } from "./types";

/**
 * Hesap durumunu okuyan ve değiştiren kanca.
 *
 * Doğrulama ÇEKİRDEKTE yapılır; burada parola tutulmaz, yalnız uçlara iletilir.
 * Hata metni de çekirdekten gelir: iki yerde ayrı mesaj yazılsaydı biri
 * düzeltilirken öteki eskirdi.
 */

interface Yanit extends Record<string, unknown> {
  ok?: boolean;
  metin?: string;
}

function hataMetni(yanit: Yanit | null, yedek: string): string {
  return typeof yanit?.metin === "string" && yanit.metin ? yanit.metin : yedek;
}

export interface AccountController {
  durum: HesapDurumu | null;
  yukleniyor: boolean;
  hata: string | null;
  /** Kayıt başarılıysa kurtarma kodunu taşıyan sonucu döner, değilse null. */
  kayit: (girdi: {
    kullanici_adi: string;
    eposta: string;
    parola: string;
    avatar: string;
  }) => Promise<KayitSonucu | null>;
  giris: (kimlik: string, parola: string) => Promise<boolean>;
  cikis: () => Promise<void>;
  kurtar: (kimlik: string, kod: string, yeniParola: string) => Promise<boolean>;
  guncelle: (hesap: Hesap) => Promise<boolean>;
  sil: (kimlik: string) => Promise<boolean>;
  tazele: () => Promise<void>;
}

export function useAccount(client: ProtocolClient | null): AccountController {
  const [durum, setDurum] = useState<HesapDurumu | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [hata, setHata] = useState<string | null>(null);

  const tazele = useCallback(async () => {
    if (!client) return;
    try {
      const yanit = (await client.request("hesap.durum", {})) as Yanit & HesapDurumu;
      if (yanit?.ok !== true) throw new Error(hataMetni(yanit, "Hesap durumu okunamadı."));
      // Sözleşmenin GERÇEKTEN karşılandığı doğrulanır. Hesap uçlarını tanımayan
      // bir çekirdek (eski sürüm, sahte taşıma) `ok: true` dönebilir; o yanıtı
      // "hiç hesap yok" diye okumak kullanıcıyı giriş ekranında kilitlerdi.
      if (!Array.isArray(yanit.hesaplar) || typeof yanit.kurulum_gerekli !== "boolean") {
        setDurum(null);
        setHata(null);
        return;
      }
      setDurum({
        hesaplar: yanit.hesaplar,
        etkin: typeof yanit.etkin === "string" ? yanit.etkin : "",
        kurulum_gerekli: yanit.kurulum_gerekli,
      });
      setHata(null);
    } catch {
      setHata("Hesap bilgisi okunamadı. Fusion'ı kapatıp yeniden aç.");
    } finally {
      setYukleniyor(false);
    }
  }, [client]);

  useEffect(() => {
    void tazele();
  }, [tazele]);

  /** Ortak istek yolu: hata metnini çekirdekten alır, durumu tazeler. */
  const cagir = useCallback(
    async (ad: string, veri: Record<string, unknown>, yedek: string): Promise<Yanit | null> => {
      if (!client) return null;
      setHata(null);
      try {
        const yanit = (await client.request(ad, veri)) as Yanit;
        if (yanit?.ok !== true) {
          setHata(hataMetni(yanit, yedek));
          return null;
        }
        await tazele();
        return yanit;
      } catch {
        setHata(yedek);
        return null;
      }
    },
    [client, tazele],
  );

  return {
    durum,
    yukleniyor,
    hata,
    tazele,
    kayit: async (girdi) => {
      const yanit = await cagir("hesap.kayit", girdi, "Hesap açılamadı.");
      return yanit ? (yanit as unknown as KayitSonucu) : null;
    },
    giris: async (kimlik, parola) =>
      (await cagir("hesap.giris", { kimlik, parola }, "Giriş yapılamadı.")) !== null,
    cikis: async () => {
      await cagir("hesap.cikis", {}, "Çıkış yapılamadı.");
    },
    kurtar: async (kimlik, kurtarma_kodu, yeni_parola) =>
      (await cagir(
        "hesap.kurtar",
        { kimlik, kurtarma_kodu, yeni_parola },
        "Parola değiştirilemedi.",
      )) !== null,
    guncelle: async (hesap) =>
      (await cagir(
        "hesap.guncelle",
        {
          kimlik: hesap.kimlik,
          kullanici_adi: hesap.kullanici_adi,
          eposta: hesap.eposta,
          avatar: hesap.avatar,
        },
        "Hesap güncellenemedi.",
      )) !== null,
    sil: async (kimlik) =>
      (await cagir("hesap.sil", { kimlik }, "Hesap silinemedi.")) !== null,
  };
}
