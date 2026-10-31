import { Button } from "../ui/Button";
import { PageHeader } from "../ui/PageHeader";
import { AccountProfile, type AccountProfileProps } from "./AccountProfile";
import "./account.css";

/**
 * Hesabım sayfası — tam sayfa kabuğu. İçerik `AccountProfile`dadır; Ayarlar › Hesap
 * aynı bileşeni gösterir.
 */
export function AccountScreen({
  onClose,
  ...profile
}: Omit<AccountProfileProps, "layout"> & { onClose: () => void }) {
  const durum = profile.account.durum;
  const etkin = durum?.hesaplar.find((item) => item.kimlik === durum.etkin) ?? null;

  if (!etkin) {
    return (
      <main className="account-screen">
        <PageHeader
          actions={<Button onClick={onClose} variant="secondary">Kapat</Button>}
          description="Hesap bilgisi okunamadı."
          eyebrow="Hesap"
          title="Hesabım"
        />
      </main>
    );
  }

  return (
    <main className="account-screen">
      <div className="account-screen__toolbar">
        <Button onClick={onClose} variant="secondary">Kapat</Button>
      </div>
      <AccountProfile {...profile} layout="page" />
    </main>
  );
}
