export type RuntimeState =
  | "denetleniyor"
  | "kuruluyor"
  | "hazir"
  | "onarilabilir"
  | "hata";

export interface RuntimeProgress {
  stage: string;
  completed: number;
  total: number;
  message: string;
}

export interface RuntimeBackendStatus {
  state: "eksik" | "hazir" | "onarilabilir" | "hata";
  version?: string;
  message: string;
  can_repair: boolean;
}

export interface RuntimeView {
  state: RuntimeState;
  progress: number;
  message: string;
  version?: string;
}

export interface RuntimeTransport {
  status(): Promise<RuntimeBackendStatus>;
  prepare(): Promise<RuntimeBackendStatus>;
  repair(): Promise<RuntimeBackendStatus>;
  listenProgress(listener: (progress: RuntimeProgress) => void): Promise<() => void>;
}
