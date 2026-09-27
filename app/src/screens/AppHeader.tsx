import { Button } from "../ui/Button";
import "./AppHeader.css";

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
  sidebarCollapsed: boolean;
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
  sidebarCollapsed,
  status = "Hazır",
  title,
}: AppHeaderProps) {
  return (
    <div className="app-header">
      <div className="app-header__nav">
        <Button
          aria-controls="fusion-sidebar"
          aria-expanded={!sidebarCollapsed}
          aria-label={sidebarCollapsed ? "Navigasyonu aç" : "Navigasyonu daralt"}
          icon="sidebar"
          iconOnly
          onClick={onToggleSidebar}
        />
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
      </div>
      {/* Kimlik alanının boş kısmı pencereyi sürükletir: ayrı bir boş başlık
          şeridi çizmek yerine üst çubuğun kendisi başlık çubuğuyla kaynaşır. */}
      <div className="app-header__identity" data-tauri-drag-region>
        <h1>{title}</h1>
        {projectName && <span className="app-header__project">{projectName}</span>}
      </div>
      <div className="app-header__actions">
        {status === "Bağlantı kesildi" && <span className="app-header__status" role="alert">{status}</span>}
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
