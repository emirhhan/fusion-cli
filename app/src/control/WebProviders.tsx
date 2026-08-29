import { useCallback, useEffect, useRef, useState } from "react";
import { ProviderLogo, type ProviderId } from "../brand/ProviderLogo";
import type { ProtocolClient } from "../protocol/client";
import "./WebProviders.css";

/**
 * Web sağlayıcı bağlantıları — projenin ana taşı.
 *
 * Bu dört sağlayıcı (ChatGPT, Claude, Gemini, Copilot) kullanıcının KENDİ
 * aboneliğiyle çalışır ve API anahtarı KULLANMAZ. Bu yüzden burada anahtar
 * kutusu yoktur: "Giriş yap" ayrı bir tarayıcı penceresi açar, kullanıcı orada
 * normal şekilde giriş yapar, çerez izole profilde kalır ve Fusion çerez
 * değerine hiç dokunmaz. Pencere kapandığı anda liste kendiliğinden tazelenir.
 */

interface ProviderCard {
  ad: string;
  anahtar_gerekir: boolean;
  arac_destegi: string;
  bagli: boolean;
  etkin: boolean;
  hesap: string;
  id: string;
  model?: string | null;
  olcum_gecti: boolean;
}

/** Giriş penceresi yoklama aralığı. Kısa olması gerekmez: kullanıcı orada. */
const YOKLAMA_MS = 1500;

export function WebProviders({ client }: { client: ProtocolClient }) {
  const [cards, setCards] = useState<ProviderCard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const timers = useRef<number[]>([]);

  const load = useCallback(async () => {
    try {
      const veri = (await client.request("web.saglayicilar", {})) as {
        ok?: boolean;
        metin?: string;
        saglayicilar?: ProviderCard[];
      };
      if (!veri?.ok) {
        setError(veri?.metin ?? "Sağlayıcılar okunamadı.");
        return;
      }
      setError(null);
      setCards(veri.saglayicilar ?? []);
    } catch {
      setError("Sağlayıcılar okunamadı.");
    }
  }, [client]);

  useEffect(() => {
    void load();
    const running = timers.current;
    return () => running.forEach((id) => window.clearTimeout(id));
  }, [load]);

  /** Giriş penceresini aç, kapanmasını bekle, sonra listeyi tazele. */
  const login = async (card: ProviderCard) => {
    setBusy(card.id);
    try {
      const acilis = (await client.request("web.giris", {
        saglayici: card.id,
        hesap: card.hesap,
      })) as { ok?: boolean; metin?: string; pid?: number };
      if (!acilis?.ok || !acilis.pid) {
        setError(acilis?.metin ?? "Giriş tarayıcısı açılamadı.");
        setBusy(null);
        return;
      }
      const pid = acilis.pid;
      const poll = async () => {
        const durum = (await client.request("web.giris_durumu", { pid })) as {
          acik?: boolean;
        };
        if (durum?.acik) {
          timers.current.push(window.setTimeout(() => void poll(), YOKLAMA_MS));
          return;
        }
        setBusy(null);
        await load();
      };
      await poll();
    } catch {
      setError("Giriş tarayıcısı açılamadı.");
      setBusy(null);
    }
  };

  return (
    <section aria-label="Web sağlayıcıları" className="web-providers">
      <header className="web-providers__head">
        <div>
          <span>BAĞLANTILAR</span>
          <h3>Web sağlayıcıları</h3>
          <p>
            Kendi aboneliğinle çalışır; API anahtarı gerekmez. Giriş ayrı bir pencerede
            yapılır ve oturum bu bilgisayarda kalır.
          </p>
        </div>
      </header>
      {error && <p className="web-providers__error" role="status">{error}</p>}
      <ul className="web-providers__list">
        {cards.map((card) => (
          <li className="web-providers__card" data-bagli={card.bagli} key={card.id}>
            <span className="web-providers__mark">
              <ProviderLogo id={card.id as ProviderId} size={22} />
            </span>
            <span className="web-providers__body">
              <strong>{card.ad}</strong>
              <small>
                {card.bagli
                  ? `bağlı · ${card.hesap}`
                  : "bağlı değil — giriş yapıldığında burada görünür"}
              </small>
              {card.bagli && card.arac_destegi === "emulated" && (
                <small className="web-providers__gate">
                  {card.olcum_gecti
                    ? "araç ölçümü geçti · dosya değiştirebilir"
                    : "araç ölçümü yapılmadı · yalnız okuma"}
                </small>
              )}
            </span>
            <button
              className="web-providers__action"
              disabled={busy === card.id}
              onClick={() => void login(card)}
              type="button"
            >
              {busy === card.id
                ? "Pencere açık…"
                : card.bagli
                  ? "Bağlantıyı yenile"
                  : "Giriş yap"}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
