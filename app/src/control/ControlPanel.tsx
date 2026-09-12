import { useCallback, useEffect, useState } from "react";
import { PermissionPrompt } from "../permissions/PermissionPrompt";
import { usePermissions } from "../permissions/usePermissions";
import type { PermissionBridge } from "../permissions/types";
import { nativePermissionBridge } from "../platform/permissions";
import type { ProtocolClient } from "../protocol/client";
import { Button } from "../ui/Button";
import { PageHeader } from "../ui/PageHeader";
import { ProviderList } from "./ProviderList";
import "./ControlPanel.css";

/**
 * Kontrol Paneli — SAĞLAYICI bağlantılarının yönetildiği yer.
 *
 * Panel eskiden altı bölüm taşıyordu: modeller, izinler, sağlayıcılar, gateway,
 * MCP ve güncellemeler. Kullanıcının ölçülmüş tepkisi buydu — "kontrol
 * panelindeki mcp alanı ne işe yarıyor", "güncellemeler neden kontrol
 * panelinde", "gateway nedir ben bile bilmiyorum".
 *
 * Bölümler ait oldukları yerlere taşındı: modeller, izinler, güncellemeler ve
 * yerel API ucu Ayarlar'a; MCP kendi ekranına. Burada YALNIZ sağlayıcılar
 * kaldı — anahtar girmek, web oturumu açmak ve bağlantıyı sınamak. Panelin
 * gerçek işi zaten buydu.
 */

interface ControlPanelProps {
  client: ProtocolClient;
  /** Sayfa başlığı; panel farklı bir kapıdan açıldığında değişir. */
  title?: string;
  onClose: () => void;
  permissionBridge?: PermissionBridge;
  /** Değeri değişince sağlayıcı listesi yeniden okunur. */
  revision?: number;
  onProvidersChanged?: () => void;
}

export function ControlPanel({
  client,
  onClose,
  onProvidersChanged,
  permissionBridge = nativePermissionBridge,
  revision = 0,
  title = "Kontrol Paneli",
}: ControlPanelProps) {
  const permissions = usePermissions(permissionBridge);
  const [secretError, setSecretError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const payload = await client.request("kontrol.durum", {});
      if (payload.ok !== true) throw new Error(String(payload.metin ?? "Durum alınamadı."));
      const uyari = payload.sir_deposu_hatasi;
      setSecretError(typeof uyari === "string" && uyari ? uyari : null);
      setError(null);
    } catch (reason) {
      setError(String(reason));
    }
  }, [client]);

  useEffect(() => {
    void reload();
  }, [reload, revision]);

  return (
    <main className="control-panel">
      <PageHeader
        actions={<Button onClick={onClose} variant="secondary">Kapat</Button>}
        description="Model sağlayıcılarına bağlan: anahtar gir ya da web oturumu aç."
        title={title}
      />
      {error && <p className="control-panel__notice" data-error="true" role="alert">{error}</p>}

      <div className="control-panel__layout">
        <section className="control-panel__section control-panel__section--wide">
          {/* Anahtarlık çalışmıyorsa kullanıcı bunu anahtar girmeden ÖNCE
              bilmeli: yazdığı anahtar kaydedilemeyecek. */}
          {secretError && (
            <p className="control-panel__warning" role="status">{secretError}</p>
          )}
          <ProviderList client={client} onChanged={onProvidersChanged} />
        </section>
      </div>

      {permissions.activeKind && (
        <PermissionPrompt
          canOpenSettings={permissions.activeKind === "microphone" || permissions.activeKind === "speech"}
          error={permissions.error}
          isRequesting={permissions.isRequesting}
          kind={permissions.activeKind}
          phase={permissions.phase}
          onContinue={() => void permissions.continue()}
          onContinueToNext={permissions.hasQueuedPermission ? permissions.continueToNext : undefined}
          onDismiss={permissions.dismiss}
          onOpenSettings={() => void permissions.openSettings(permissions.activeKind!)}
          onRetry={() => void permissions.retry()}
        />
      )}
    </main>
  );
}
