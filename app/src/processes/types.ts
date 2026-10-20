export type ProcessStatus = "calisiyor" | "bitti" | "hata" | "durduruldu";

export interface ProjectProcess {
  surec_id: string;
  komut: string;
  cwd: string;
  pid: number;
  durum: ProcessStatus;
  cikis_kodu: number | null;
  cikti: string;
  baslangic: number;
}
