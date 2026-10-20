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

/** Arama sonucu: künyenin üstüne eşleşmenin nerede bulunduğu ve kanıtı. */
export interface HistorySearchMatch extends HistorySessionRef {
  /** Eşleşme başlıkta mı bulundu? Değilse konuşma içeriğinde bulunmuştur. */
  baslikta: boolean;
  /** Eşleşmenin geçtiği yerin maskelenmiş, kısaltılmış parçası. */
  parca: string;
}

export interface HistoryTurn {
  rol: "user" | "assistant" | "system" | "tool";
  metin: string;
  zaman: number | null;
}
