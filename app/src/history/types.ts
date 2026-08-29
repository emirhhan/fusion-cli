import type { SessionSource } from "../sessions/types";

export type HistorySourceName = Exclude<SessionSource, "fusion">;

export interface HistorySourceRef {
  ad: HistorySourceName;
  komut: string;
}

export interface HistorySessionRef {
  kaynak: HistorySourceName;
  oturum_id: string;
  baslik: string;
  guncellendi: number | null;
  tur_sayisi: number | null;
  boyut: number;
}

export interface HistoryTurn {
  rol: "user" | "assistant" | "system" | "tool";
  metin: string;
  zaman: number | null;
}
