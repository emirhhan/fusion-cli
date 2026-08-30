import { Button } from "../ui/Button";
import "./AppHeader.css";

interface AppHeaderProps {
  inspectorOpen: boolean;
  onToggleInspector: () => void;
  onToggleSidebar: () => void;
  projectName?: string;
  sidebarCollapsed: boolean;
  status?: string;
  title: string;
}

export function AppHeader({
  inspectorOpen,
  onToggleInspector,
  onToggleSidebar,
  projectName,
  sidebarCollapsed,
  status = "Hazır",
  title,
}: AppHeaderProps) {
  return (
    <div className="app-header">
      <Button
        aria-controls="fusion-sidebar"
        aria-expanded={!sidebarCollapsed}
        aria-label={sidebarCollapsed ? "Navigasyonu aç" : "Navigasyonu daralt"}
        icon="sidebar"
        iconOnly
        onClick={onToggleSidebar}
      />
      <div className="app-header__identity">
        <h1>{title}</h1>
        {projectName && <span className="app-header__project">{projectName}</span>}
      </div>
      <div className="app-header__actions">
        <span className="app-header__status"><span aria-hidden="true" />{status}</span>
        {/* Tema değiştirici başlıktan KALDIRILDI: tema bir tercihtir ve yeri
            Ayarlar'dır. Ana ekranda durması hem gereksiz yer kaplıyor hem
            günlük kullanımda yanlışlıkla değiştirilmesine yol açıyordu. */}
        <Button
          aria-controls="fusion-inspector"
          aria-expanded={inspectorOpen}
          aria-label={inspectorOpen ? "Denetçiyi kapat" : "Denetçiyi aç"}
          icon="panel"
          iconOnly
          onClick={onToggleInspector}
        />
      </div>
    </div>
  );
}
