import { Button } from "../ui/Button";
import "./AppHeader.css";

/** Üst bileşen ile başlık arasındaki tek sözleşme metni; iki yerde ayrı yazılınca biri değişince uyarı kayboluyordu (U1-61). */
export const BAGLANTI_KESILDI_DURUMU = "Bağlantı kesildi";

/** Başlıktaki "Uzaktan kontrol" anahtarı (P-066): durum + Ayarlar › Uzaktan Erişim kısayolu. */
export interface RemoteHeaderState {
  listening: boolean;
  deviceCount: number;
  pendingApprovals: number;
  onOpen: () => void;
}

/** Anahtarın erişilebilir adı; test ve üst bileşen aynı metni kullanır. */
export const UZAKTAN_KONTROL_ETIKETI = "Uzaktan kontrol";

function remoteSummary(remote: RemoteHeaderState): string {
  if (!remote.listening) return "kapalı";
  const parts = [remote.deviceCount === 1 ? "1 cihaz" : `${remote.deviceCount} cihaz`];
  if (remote.pendingApprovals > 0) parts.push(`${remote.pendingApprovals} onay bekliyor`);
  return parts.join(" · ");
}

interface AppHeaderProps {
  canNavigateBack?: boolean;
  canNavigateForward?: boolean;
  inspectorAvailable?: boolean;
  inspectorOpen: boolean;
  onNavigateBack?: () => void;
  onNavigateForward?: () => void;
  onToggleInspector: () => void;
  onToggleSidebar: () => void;
  onShare?: () => void;
  projectName?: string;
  /** Verilmezse anahtar çizilmez (ör. hesap kapısı, kurulum). */
  remote?: RemoteHeaderState;
  sidebarCollapsed: boolean;
  sidebarAvailable?: boolean;
  status?: string;
  title: string;
}

export function AppHeader({
  canNavigateBack = false,
  canNavigateForward = false,
  inspectorAvailable = true,
  inspectorOpen,
  onNavigateBack,
  onNavigateForward,
  onToggleInspector,
  onToggleSidebar,
  onShare,
  projectName,
  remote,
  sidebarCollapsed,
  sidebarAvailable = true,
  status = "Hazır",
  title,
}: AppHeaderProps) {
  return (
    <div className="app-header">
      <div className="app-header__nav">
        {(onNavigateBack || onNavigateForward) && (
          <span className="app-header__history">
            <Button
              aria-label="Geri git"
              className="app-header__nav-back"
              disabled={!canNavigateBack}
              icon="chevron"
              iconOnly
              onClick={onNavigateBack}
            />
            <Button
              aria-label="İleri git"
              icon="chevron"
              iconOnly
              disabled={!canNavigateForward}
              onClick={onNavigateForward}
            />
          </span>
        )}
        {sidebarAvailable && (<Button
          aria-controls="fusion-sidebar"
          aria-expanded={!sidebarCollapsed}
          aria-label={sidebarCollapsed ? "Navigasyonu aç" : "Navigasyonu daralt"}
          icon="sidebar"
          iconOnly
          onClick={onToggleSidebar}
        />)}
      </div>
      {/* Kimlik alanının boş kısmı pencereyi sürükletir: ayrı bir boş başlık
          şeridi çizmek yerine üst çubuğun kendisi başlık çubuğuyla kaynaşır. */}
      <div className="app-header__identity" data-tauri-drag-region>
        <h1>{title}</h1>
        {projectName && <span className="app-header__project">{projectName}</span>}
      </div>
      <div className="app-header__actions">
        {status === BAGLANTI_KESILDI_DURUMU && <span className="app-header__status" role="alert">{status}</span>}
        {remote && (
          /* Claude Code'un başlıktaki Remote Control göstergesi: açık/kapalı nokta + kısa özet;
             tıklanınca Ayarlar › Uzaktan Erişim (eşleştirme kodu, cihazlar, onaylar) açılır. */
          <button
            aria-label={`${UZAKTAN_KONTROL_ETIKETI}: ${remoteSummary(remote)}`}
            aria-pressed={remote.listening}
            className={`app-header__remote${remote.listening ? " app-header__remote--on" : ""}${remote.pendingApprovals > 0 ? " app-header__remote--pending" : ""}`}
            onClick={remote.onOpen}
            title="Telefondan sürme ve uzaktan onay ayarları"
            type="button"
          >
            <span aria-hidden="true" className="app-header__remote-dot" />
            <span className="app-header__remote-label">{UZAKTAN_KONTROL_ETIKETI}</span>
            <span className="app-header__remote-summary">{remoteSummary(remote)}</span>
          </button>
        )}
        {onShare && <Button aria-label="Sohbeti paylaş" icon="share" iconOnly onClick={onShare} />}
        {/* Tema değiştirici başlıktan KALDIRILDI: tema bir tercihtir ve yeri
            Ayarlar'dır. Ana ekranda durması hem gereksiz yer kaplıyor hem
            günlük kullanımda yanlışlıkla değiştirilmesine yol açıyordu. */}
        {inspectorAvailable && <Button
          aria-controls="fusion-inspector"
          aria-expanded={inspectorOpen}
          aria-label={inspectorOpen ? "Denetçiyi kapat" : "Denetçiyi aç"}
          icon="panel"
          iconOnly
          onClick={onToggleInspector}
        />}
      </div>
    </div>
  );
}
