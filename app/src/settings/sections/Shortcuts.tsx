import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../../protocol/client";
import { KEYMAP_CHANGED_EVENT, SHORTCUT_CAPTURE_ATTRIBUTE } from "../../shortcuts/useAppShortcuts";
import {
  DEFAULT_BINDINGS, actionLabel, eventToKey, formatKey, isMacPlatform, keyProblem, keymapFromPayload, keysForAction,
  type Keymap,
} from "../../shortcuts/keys";
import "./Shortcuts.css";

/**
 * Ayarlar › Kısayollar (P-046): masaüstü tuş bağlarını listele, yeniden bağla, kaldır, sıfırla.
 *
 * Kayıt terminalle aynı `keybindings.json` dosyasının `masaustu` bağlamıdır (Claude Code
 * `keybindings.json` modeli); yazma çekirdekte yapılır (`kisayol.ata|kaldir|sifirla`), dosya
 * elle de düzenlenebilir. Dolu bir tuş sorulmadan devralınmaz.
 */

/** Dolu tuş: `retry` aynı isteğin `zorla: true` ile tekrarıdır (bağlama ya da varsayılana dönme). */
interface Conflict { key: string; holder: string; retry: { name: string; data: Record<string, unknown> } }

const MAC = isMacPlatform();

function sameKeys(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((key) => b.includes(key));
}

export function Shortcuts({ client }: { client: ProtocolClient }) {
  const [keymap, setKeymap] = useState<Keymap | null>(null);
  const [recording, setRecording] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<Conflict | null>(null);

  const accept = useCallback((payload: unknown) => {
    const next = keymapFromPayload(payload);
    if (!next) return false;
    setKeymap(next);
    window.dispatchEvent(new CustomEvent(KEYMAP_CHANGED_EVENT, { detail: payload }));
    return true;
  }, []);

  useEffect(() => {
    let alive = true;
    void client.request("kisayol.liste", {}).then((payload) => {
      const next = keymapFromPayload(payload);
      if (!alive) return;
      if (next) setKeymap(next);
      else setError("Kısayollar okunamadı. Çekirdek bu sürümde kısayol düzenlemeyi desteklemiyor olabilir.");
    }).catch(() => { if (alive) setError("Kısayollar okunamadı."); });
    return () => { alive = false; };
  }, [client]);

  const send = async (name: string, data: Record<string, unknown>) => {
    setBusy(true); setError(null);
    try {
      const payload = (await client.request(name, data)) as Record<string, unknown>;
      if (accept(payload)) { setConflict(null); return; }
      const key = typeof payload.tus === "string" ? payload.tus : data.tus;
      if (typeof payload.cakisma === "string" && typeof key === "string") {
        setConflict({ key, holder: payload.cakisma, retry: { name, data: { ...data, zorla: true } } });
        return;
      }
      setError(typeof payload.metin === "string" ? payload.metin : "Kısayol kaydedilemedi.");
    } catch (reason) {
      setError(`Kısayol kaydedilemedi: ${reason instanceof Error ? reason.message : String(reason)}`);
    } finally {
      setBusy(false);
    }
  };

  const onRecordKey = (action: string, event: React.KeyboardEvent) => {
    event.preventDefault();
    event.stopPropagation();
    if (event.key === "Escape") { setRecording(null); return; }
    const key = eventToKey(event.nativeEvent, MAC);
    if (!key) return; // Yalnız değiştiriciye basıldı: asıl tuşu bekle.
    const problem = keyProblem(key);
    if (problem) { setError(problem); return; }
    setRecording(null);
    void send("kisayol.ata", { eylem: action, tus: key });
  };

  if (!keymap) {
    return <article className="settings__card" id="settings-shortcuts">{error ? <p role="alert">{error}</p> : <p role="status">Kısayollar yükleniyor…</p>}</article>;
  }
  const customCommands = Object.values(keymap.baglar).filter((action) => !(action in keymap.etiketler));
  const actions = [...Object.keys(keymap.etiketler), ...new Set(customCommands)];

  return (
    <article className="settings__card" id="settings-shortcuts">
      <h3>Uygulama kısayolları</h3>
      <p className="settings__hint">
        ⌘K komut paletini açar; paletten her eylem, sohbet, dosya ve ayar aranabilir. Bağlar terminalle aynı dosyada
        durur{keymap.yol ? <> (<code>{keymap.yol}</code>, <code>masaustu</code> bölümü)</> : null}; dosyayı elle
        düzenlersen pencereye döndüğünde uygulanır. <code>komut:&lt;ad&gt;</code> ile bir slash komutu da bağlanabilir.
      </p>
      {error && <p className="settings__error" role="alert">{error}</p>}
      {conflict && (
        <div className="shortcuts__conflict" role="alertdialog" aria-label="Kısayol çakışması">
          <p>{formatKey(conflict.key, MAC)} zaten “{actionLabel(conflict.holder, keymap.etiketler)}” eylemine bağlı. Bu eyleme taşınsın mı?</p>
          <div className="settings__actions">
            <button disabled={busy} onClick={() => void send(conflict.retry.name, conflict.retry.data)} type="button">Taşı</button>
            <button onClick={() => setConflict(null)} type="button">Vazgeç</button>
          </div>
        </div>
      )}
      <table className="shortcuts__table">
        <thead><tr><th scope="col">Eylem</th><th scope="col">Tuş</th><th scope="col"><span className="settings__sr-only">Düzenle</span></th></tr></thead>
        <tbody>
          {actions.map((action) => {
            const keys = keysForAction(keymap.baglar, action);
            const isDefault = sameKeys(keys, keysForAction({ ...DEFAULT_BINDINGS }, action));
            const label = actionLabel(action, keymap.etiketler);
            return (
              <tr key={action}>
                <th scope="row">{label}</th>
                <td>{keys.length ? keys.map((key) => <kbd key={key}>{formatKey(key, MAC)}</kbd>) : <span className="shortcuts__unset">Atanmadı</span>}</td>
                <td className="shortcuts__row-actions">
                  {recording === action ? (
                    <button
                      {...{ [SHORTCUT_CAPTURE_ATTRIBUTE]: "" }}
                      aria-label={`${label} için yeni tuşa bas; Esc vazgeçer`}
                      autoFocus
                      onBlur={() => setRecording(null)}
                      onKeyDown={(event) => onRecordKey(action, event)}
                      type="button"
                    >
                      Tuşa bas…
                    </button>
                  ) : (
                    <button aria-label={`${label} kısayolunu değiştir`} disabled={busy} onClick={() => { setError(null); setRecording(action); }} type="button">Değiştir</button>
                  )}
                  {keys.length > 0 && <button aria-label={`${label} kısayolunu kaldır`} disabled={busy} onClick={() => void send("kisayol.kaldir", { eylem: action })} type="button">Kaldır</button>}
                  {!isDefault && action in keymap.etiketler && <button aria-label={`${label} kısayolunu varsayılana döndür`} disabled={busy} onClick={() => void send("kisayol.sifirla", { eylem: action })} type="button">Varsayılan</button>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {keymap.uyarilar.length > 0 && (
        <ul className="shortcuts__warnings" aria-label="Kısayol dosyası uyarıları">
          {keymap.uyarilar.map((warning) => <li key={warning}>{warning}</li>)}
        </ul>
      )}
      <div className="settings__actions">
        <button disabled={busy} onClick={() => void send("kisayol.sifirla", {})} type="button">Tümünü varsayılana döndür</button>
      </div>
    </article>
  );
}
