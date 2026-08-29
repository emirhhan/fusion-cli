import { Button } from "../ui/Button";
import type { ThemePreference } from "../theme/theme";
import "./AppHeader.css";

interface AppHeaderProps {
  inspectorOpen: boolean;
  onThemeChange?: (theme: ThemePreference) => void;
  onToggleInspector: () => void;
  onToggleSidebar: () => void;
  projectName?: string;
  sidebarCollapsed: boolean;
  status?: string;
  themePreference?: ThemePreference;
  title: string;
}

export function AppHeader({
  inspectorOpen,
  onThemeChange,
  onToggleInspector,
  onToggleSidebar,
  projectName,
  sidebarCollapsed,
  status = "Hazır",
  themePreference = "system",
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
        {onThemeChange && (
          <label className="app-header__theme">
            <span>Tema</span>
            <select
              aria-label="Tema"
              onChange={(event) => onThemeChange(event.target.value as ThemePreference)}
              value={themePreference}
            >
              <option value="system">Sistem</option>
              <option value="light">Açık</option>
              <option value="dark">Koyu</option>
            </select>
          </label>
        )}
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
