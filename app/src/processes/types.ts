export type ProcessStatus = "calisiyor" | "bitti" | "hata" | "durduruldu";

export interface ProjectProcess {
  surec_id: string;
  komut: string;
  cwd: string;
  /** Süreç doğamadıysa çekirdek pid göndermeyebilir. */
  pid: number | null;
  durum: ProcessStatus;
  cikis_kodu: number | null;
  cikti: string;
  baslangic: number;
}
