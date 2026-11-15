export type WorkspaceEntryKind = "klasor" | "dosya";

export interface WorkspaceEntry {
  ad: string;
  yol: string;
  tur: WorkspaceEntryKind;
  boyut: number;
  degistirilme: number;
}

export interface WorkspaceFile {
  yol: string;
  tur: "metin" | "binary";
  mime: string;
  boyut: number;
  sha256: string;
  icerik: string | null;
  kesildi: boolean;
}

export interface WorkspaceState {
  directories: Record<string, WorkspaceEntry[]>;
  expanded: Set<string>;
  selected: WorkspaceFile | null;
  loading: boolean;
  /** Dizin listeleme/açma hatası; ağacı GİZLEMEZ (yalnız kök liste yoksa tek başına görünür). */
  error: string | null;
  /** Seçilen dosyanın okuma hatası; görüntüleyicide gösterilir, ağaç etkilenmez. */
  selectedError: string | null;
}
