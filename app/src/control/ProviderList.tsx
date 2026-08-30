import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ProviderLogo, type ProviderId } from "../brand/ProviderLogo";
import type { ProtocolClient } from "../protocol/client";
import "./ProviderList.css";

/**
 * Sağlayıcı listesi.
 *
 * TEK ve KISA liste: her satırda yalnız ad ve bağlı olup olmadığı yazar.
 * Ayrıntı satıra tıklayınca açılır ve TÜRE GÖRE değişir — web sağlayıcısında
 * oturum açma, anahtarlı sağlayıcıda anahtar alanı. Eskiden her sağlayıcı için
 * ekranda açık duran uzun anahtar kutuları vardı; web sağlayıcıları anahtar
 * kullanmadığı için bu hem yanlış hem yer kaplıyordu.
 */

interface ProviderRow {
  ad: string;
  bagli: boolean;
  eylem: "oturum" | "anahtar";
  hesap?: string;
  id: string;
  ortam?: string;
  tur: "web" | "anahtar";
}

const YOKLAMA_MS = 1500;

export function ProviderList({ client }: { client: ProtocolClient }) {
  const [rows, setRows] = useState<ProviderRow[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const timers = useRef<number[]>([]);

  const load = useCallback(async () => {
    try {
      const veri = (await client.request("saglayici.katalog", {})) as {
        ok?: boolean;
        saglayicilar?: ProviderRow[];
      };
      if (!veri?.ok) {
        setNotice("Sağlayıcılar okunamadı.");
        return;
      }
      setRows(veri.saglayicilar ?? []);
    } catch {
      setNotice("Sağlayıcılar okunamadı.");
    }
  }, [client]);

  useEffect(() => {
    void load();
    const running = timers.current;
    return () => running.forEach((id) => window.clearTimeout(id));
  }, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLocaleLowerCase("tr");
    if (!q) return rows;
    return rows.filter((row) => row.ad.toLocaleLowerCase("tr").includes(q));
  }, [query, rows]);

  /** Web girişini aç ve pencere kapanınca listeyi tazele. */
  const login = async (row: ProviderRow) => {
    setBusy(row.id);
    setNotice(null);
    const acilis = (await client.request("web.giris", {
      saglayici: row.id,
      hesap: row.hesap ?? "main",
    })) as { ok?: boolean; metin?: string; pid?: number };
    if (!acilis?.ok || !acilis.pid) {
      setNotice(acilis?.metin ?? "Giriş penceresi açılamadı.");
      setBusy(null);
      return;
    }
    const poll = async () => {
      const durum = (await client.request("web.giris_durumu", { pid: acilis.pid })) as {
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
  };

  const saveKey = async (row: ProviderRow) => {
    if (!secret.trim()) return;
    setBusy(row.id);
    const sonuc = (await client.request("kontrol.anahtar_kaydet", {
      saglayici: row.id,
      deger: secret,
    })) as { ok?: boolean; metin?: string };
    setBusy(null);
    setSecret("");
    if (!sonuc?.ok) {
      setNotice(sonuc?.metin ?? "Anahtar kaydedilemedi.");
      return;
    }
    setNotice(`${row.ad} anahtarı kaydedildi.`);
    await load();
  };

  const dropKey = async (row: ProviderRow) => {
    setBusy(row.id);
    const sonuc = (await client.request("kontrol.anahtar_sil", { saglayici: row.id })) as {
      ok?: boolean;
      metin?: string;
    };
    setBusy(null);
    if (!sonuc?.ok) {
      setNotice(sonuc?.metin ?? "Anahtar silinemedi.");
      return;
    }
    setNotice(`${row.ad} anahtarı silindi.`);
    await load();
  };

  return (
    <section aria-label="Sağlayıcılar" className="provider-list">
      <header className="provider-list__head">
        <div>
          <span>BAĞLANTILAR</span>
          <h3>Sağlayıcılar</h3>
        </div>
        <input
          aria-label="Sağlayıcı ara"
          className="provider-list__search"
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Ara"
          type="search"
          value={query}
        />
      </header>

      {notice && <p className="provider-list__notice" role="status">{notice}</p>}

      <ul className="provider-list__rows">
        {filtered.map((row) => (
          <li key={row.id}>
            <button
              aria-expanded={open === row.id}
              className="provider-list__row"
              data-bagli={row.bagli}
              onClick={() => {
                setOpen((current) => (current === row.id ? null : row.id));
                setSecret("");
              }}
              type="button"
            >
              <span className="provider-list__mark">
                {row.tur === "web" ? (
                  <ProviderLogo id={row.id as ProviderId} size={18} />
                ) : (
                  <span aria-hidden="true">{row.ad.slice(0, 1)}</span>
                )}
              </span>
              <span className="provider-list__name">{row.ad}</span>
              <span className="provider-list__state">{row.bagli ? "bağlı" : "bağlı değil"}</span>
            </button>

            {open === row.id && (
              <div className="provider-list__detail">
                {row.eylem === "oturum" ? (
                  <>
                    <p>
                      Kendi aboneliğinle çalışır; anahtar gerekmez. Giriş ayrı bir pencerede
                      yapılır ve oturum bu bilgisayarda kalır.
                    </p>
                    <button
                      className="provider-list__action"
                      disabled={busy === row.id}
                      onClick={() => void login(row)}
                      type="button"
                    >
                      {busy === row.id ? "Pencere açık…" : row.bagli ? "Yeniden bağlan" : "Oturum aç"}
                    </button>
                  </>
                ) : (
                  <>
                    <label htmlFor={`key-${row.id}`}>API anahtarı</label>
                    <input
                      id={`key-${row.id}`}
                      onChange={(event) => setSecret(event.target.value)}
                      placeholder={row.ortam ?? ""}
                      type="password"
                      value={secret}
                    />
                    <button
                      className="provider-list__action"
                      disabled={busy === row.id || !secret.trim()}
                      onClick={() => void saveKey(row)}
                      type="button"
                    >
                      Kaydet
                    </button>
                    {row.bagli && (
                      <button
                        className="provider-list__action"
                        disabled={busy === row.id}
                        onClick={() => void dropKey(row)}
                        type="button"
                      >
                        Kayıtlı anahtarı sil
                      </button>
                    )}
                    <small>Anahtar sistem anahtarlığında şifrelenir; arayüze geri okunmaz.</small>
                  </>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
