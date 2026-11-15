/**
 * Uygulama içi modal açıkken global kısayollar çalışmaz (P-046).
 *
 * Ölçüldü (31 Ekim): geri bildirim, bağlayıcı, kit gönderme, proje, paylaş, kapatma ve derin
 * bağlantı onayı diyalogları açıkken ⌘K palet açıyor, ⌘N/⌘1-9 arkada sohbet değiştiriyordu;
 * paletin Esc'i alttaki diyaloğu da kapatıp yazılan metni siliyordu.
 *
 * İstisnalar kısayolların bilerek çalıştığı "modal" yüzeylerdir: paletin kendisi, Ayarlar (⌘K ve
 * ⌘, orada da açılır) ve dar ekranda modal olan denetçi (⌘J terminali kapatır).
 */
const MODAL_SELECTOR = '[aria-modal="true"]';
const SHORTCUT_FRIENDLY = ".command-palette__panel, .settings__dialog, #fusion-inspector";

export function blockingModalOpen(root: ParentNode = document): boolean {
  for (const node of root.querySelectorAll(MODAL_SELECTOR)) {
    if (!node.matches(SHORTCUT_FRIENDLY) && !node.closest("[hidden]")) return true;
  }
  return false;
}
