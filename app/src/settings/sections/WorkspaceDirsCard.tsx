import { useCallback, useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../../protocol/client";
import { errorMessage } from "../../protocol/result";
import { Button } from "../../ui/Button";

interface DirsPayload {
  ok?: boolean;
  metin?: string;
  kok?: string;
  dizinler?: string[];
  degisti?: boolean;
}

/**
 * Ayarlar › İzinler › Çalışma dizinleri — Claude `/permissions` Workspace sekmesi (#83).
 *
 * Birincil kök + bu oturumda `/add-dir` ile açılan dizinler. Ekle/kaldır çekirdekte
 * `/add-dir` ile aynı kurallardan geçer (ev dizini, disk kökü, proje üstü eklenemez);
 * erişim oturumluktur, diske yazılmaz.
 */
export function WorkspaceDirsCard({ client }: { client: Pick<ProtocolClient, "request"> }) {
  const [payload, setPayload] = useState<DirsPayload | null>(null);
  const [yol, setYol] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const owner = useRef(0);

  const call = useCallback(async (name: string, data: Record<string, unknown>) => {
    const generation = owner.current;
    try {
      const result = (await client.request(name, data)) as DirsPayload;
      if (generation !== owner.current) return null;
      if (Array.isArray(result?.dizinler)) setPayload(result);
      if (result?.ok === false) { setError(result.metin || "Çalışma dizinleri okunamadı."); return null; }
      setError(null);
      return result;
    } catch (reason) {
      if (generation === owner.current) setError(`Çalışma dizinleri okunamadı: ${errorMessage(reason)}`);
      return null;
    }
  }, [client]);

  useEffect(() => {
    const generation = ++owner.current;
    void call("izin.dizinler", {});
    return () => { owner.current = generation + 1; };
  }, [call]);

  const change = async (name: "izin.dizin_ekle" | "izin.dizin_kaldir", hedef: string) => {
    if (busy || !hedef.trim()) return;
    setBusy(true); setNotice(null);
    const result = await call(name, { yol: hedef.trim() });
    setBusy(false);
    if (!result) return;
    setNotice(result.metin ?? null);
    if (name === "izin.dizin_ekle" && result.degisti) setYol("");
  };

  if (!payload && !error) return null;
  const dizinler = payload?.dizinler ?? [];
  return (
    <article className="settings__card" id="settings-workspace-dirs">
      <h3>Çalışma dizinleri</h3>
      <p className="settings__hint">
        Birincil: <code>{payload?.kok ?? "—"}</code>. Eklenen dizinler yalnız bu oturum içindir
        (<code>/add-dir</code> ile aynı); ev dizini, disk kökü ve projenin üst klasörü eklenemez.
      </p>
      {dizinler.length > 0 && (
        <ul aria-label="Eklenen dizinler" className="permissions__dirs">
          {dizinler.map((dizin) => (
            <li key={dizin}>
              <code>{dizin}</code>
              <Button
                aria-label={`${dizin} dizinini kaldır`}
                disabled={busy}
                icon="close"
                iconOnly
                onClick={() => void change("izin.dizin_kaldir", dizin)}
              />
            </li>
          ))}
        </ul>
      )}
      <form className="permissions__add permissions__add--dir" onSubmit={(event) => { event.preventDefault(); void change("izin.dizin_ekle", yol); }}>
        <input
          aria-label="Eklenecek dizin"
          disabled={busy}
          onChange={(event) => setYol(event.target.value)}
          placeholder="/Users/sen/baska-proje"
          spellCheck={false}
          value={yol}
        />
        <Button disabled={busy || !yol.trim()} type="submit" variant="secondary">Dizin ekle</Button>
      </form>
      {notice && <p className="settings__hint" role="status">{notice}</p>}
      {error && <p className="settings__hint" role="alert">{error}</p>}
    </article>
  );
}
