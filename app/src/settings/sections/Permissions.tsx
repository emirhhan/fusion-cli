import { Button } from "../../ui/Button";

/**
 * İzinler — Fusion'ın ne yapmasına izin verildiği.
 *
 * Eskiden üç satırlık bir tanım listesiydi ve hangisinin seçili olduğu ancak
 * metni okuyarak anlaşılıyordu. Mod artık SEÇİLİR; ne anlama geldiği seçeneğin
 * yanında yazar.
 */

export const PERMISSION_MODES = [
  {
    id: "security",
    etiket: "Her işlemde sor",
    aciklama: "Değiştiren her işlem için ayrı ayrı onay ister.",
  },
  {
    id: "auto",
    etiket: "Otomatik uygula",
    aciklama: "Fusion kendi ilerler; yıkıcı işlemde yine sorar.",
  },
  {
    id: "plan",
    etiket: "Yalnız planla",
    aciklama: "Hiçbir şeyi değiştirmez; sadece okur ve plan çıkarır.",
  },
] as const;

export function Permissions({
  mod,
  kok,
  kokleSinirli,
  onChangeRoot,
  onSelectMode,
}: {
  mod: string;
  kok: string;
  kokleSinirli: boolean;
  onChangeRoot?: () => void;
  onSelectMode?: (command: string) => void;
}) {
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
              disabled={!onSelectMode}
              key={secenek.id}
              onClick={() => onSelectMode?.(`/${secenek.id}`)}
              type="button"
            >
              <strong>{secenek.etiket}</strong>
              <small>{secenek.aciklama}</small>
            </button>
          ))}
        </div>
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
