import { useState } from "react";
import { APPROVAL_MODES } from "../../screens/ApprovalModeMenu";
import { Button } from "../../ui/Button";

/**
 * İzinler — Fusion'ın ne yapmasına izin verildiği.
 *
 * Eskiden üç satırlık bir tanım listesiydi ve hangisinin seçili olduğu ancak
 * metni okuyarak anlaşılıyordu. Mod artık SEÇİLİR; ne anlama geldiği seçeneğin
 * yanında yazar.
 */

export const PERMISSION_MODES = APPROVAL_MODES.map((mod) => ({
  id: mod.id,
  etiket: mod.label,
  aciklama: mod.hint,
}));

export function Permissions({
  mod,
  pending = false,
  kok,
  kokleSinirli,
  onChangeRoot,
  onSelectMode,
}: {
  mod: string;
  pending?: boolean;
  kok: string;
  kokleSinirli: boolean;
  onChangeRoot?: () => void;
  onSelectMode?: (command: string) => void;
}) {
  // "İzinleri atla" hiçbir şey sormaz; tek tıkla açılmasın, önce açık onay istenir (U2-51).
  const [confirmBypass, setConfirmBypass] = useState(false);
  return (
    <>
      <article className="settings__card">
        <h3>Çalışma modu</h3>
        <div className="settings__choices" role="group">
          {PERMISSION_MODES.map((secenek) => (
            <button
              aria-pressed={secenek.id === mod}
              className="settings__choice"
              data-active={secenek.id === mod}
              disabled={!onSelectMode || pending}
              key={secenek.id}
              onClick={() => {
                if (secenek.id === "bypass" && mod !== "bypass") { setConfirmBypass(true); return; }
                setConfirmBypass(false);
                onSelectMode?.(`/${secenek.id}`);
              }}
              type="button"
            >
              <strong>{secenek.etiket}</strong>
              <small>{secenek.aciklama}</small>
            </button>
          ))}
        </div>
        {confirmBypass && (
          <div className="settings__warning" role="alert">
            <p>
              <strong>İzinleri atla</strong> modunda Fusion dosya yazma ve komut çalıştırma dahil hiçbir
              işlem için sormaz. Yalnız güvendiğin bir projede aç.
            </p>
            <div className="settings__actions">
              <Button disabled={pending} onClick={() => { setConfirmBypass(false); onSelectMode?.("/bypass"); }} variant="secondary">
                Evet, izinleri atla
              </Button>
              <Button onClick={() => setConfirmBypass(false)} variant="secondary">Vazgeç</Button>
            </div>
          </div>
        )}
        <p className="settings__hint">
          Sohbet ekranında Shift+Tab ile de değiştirebilirsin.
        </p>
      </article>

      <article className="settings__card">
        <h3>Proje klasörü</h3>
        <p className="settings__stat">{kok || "—"}</p>
        <p className="settings__hint">
          {kokleSinirli
            ? "Fusion yalnız bu klasörün içinde çalışır."
            : "Fusion bu klasörün dışına da onayınla çıkabilir."}
        </p>
        {onChangeRoot && (
          <div className="settings__actions">
            <Button onClick={onChangeRoot} variant="secondary">
              Klasörü değiştir
            </Button>
          </div>
        )}
      </article>
    </>
  );
}
