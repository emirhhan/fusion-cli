//! `fusion://` derin bağlantıları (P-064).
//!
//! Biçimler (Claude Code masaüstündeki `claude://` örneğinden):
//! - `fusion://sohbet/<id>` — kayıtlı sohbeti aç
//! - `fusion://yeni?kok=<yüzde-kodlu yol>` — yeni sohbet (isteğe bağlı klasörde)
//! - `fusion://ayarlar/<bolum>` — ayarların bir bölümünü aç
//!
//! Çözümleme saf ve testlidir; iletim yalnız ana pencereyi öne getirip olayı arayüze
//! yayınlar. Arayüz hedefi tekrar DOĞRULAR (kayıtlı sohbet var mı, bölüm tanınıyor mu):
//! dış kaynaktan gelen adres güvenilmez veri sayılır.

use serde::Serialize;
use tauri::Emitter;

/// Arayüzün dinlediği olay adı.
pub const OLAY: &str = "uygulama://derin-baglanti";
pub const SEMA: &str = "fusion";

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(tag = "hedef", rename_all = "snake_case")]
pub enum DerinBaglanti {
    Sohbet { id: String },
    Yeni { kok: Option<String> },
    Ayarlar { bolum: Option<String> },
}

/// `fusion://…` adresini çöz; tanınmayan biçimde `None`.
pub fn coz(adres: &str) -> Option<DerinBaglanti> {
    let kalan = adres.strip_prefix(&format!("{SEMA}://"))?;
    let (yol, sorgu) = kalan.split_once('?').unwrap_or((kalan, ""));
    let yol = yol.trim_end_matches('/');
    let (bas, kuyruk) = yol.split_once('/').unwrap_or((yol, ""));
    match bas {
        "sohbet" => {
            let id = yuzde_coz(kuyruk);
            // Kimlik yalnız harf/rakam/-/_ olabilir; yol ayracı ya da boşluk içeremez.
            let gecerli = !id.is_empty()
                && id.len() <= 128
                && id
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_'));
            gecerli.then_some(DerinBaglanti::Sohbet { id })
        }
        "yeni" => {
            let kok = sorgu
                .split('&')
                .filter_map(|parca| parca.split_once('='))
                .find(|(ad, _)| *ad == "kok")
                .map(|(_, deger)| yuzde_coz(deger))
                .filter(|deger| !deger.is_empty());
            Some(DerinBaglanti::Yeni { kok })
        }
        "ayarlar" => Some(DerinBaglanti::Ayarlar {
            bolum: (!kuyruk.is_empty()).then(|| yuzde_coz(kuyruk)),
        }),
        _ => None,
    }
}

/// Komut satırı argümanları içinden ilk `fusion://` adresini seç (Windows/Linux ikinci örnek).
pub fn argumanlardan(args: &[String]) -> Option<DerinBaglanti> {
    args.iter().find_map(|arg| coz(arg))
}

/// Ana pencereyi öne getir ve hedefi arayüze yayınla.
pub fn ilet(app: &tauri::AppHandle, hedef: &DerinBaglanti) {
    if let Some(ana) = app.get_webview_window_main() {
        let _ = ana.unminimize();
        let _ = ana.show();
        let _ = ana.set_focus();
    }
    if let Err(hata) = app.emit(OLAY, hedef) {
        eprintln!("[fusion][derin-baglanti] olay yayınlanamadı: {hata}");
    }
}

trait AnaPencere {
    fn get_webview_window_main(&self) -> Option<tauri::WebviewWindow>;
}

impl AnaPencere for tauri::AppHandle {
    fn get_webview_window_main(&self) -> Option<tauri::WebviewWindow> {
        tauri::Manager::get_webview_window(self, "main")
    }
}

fn yuzde_coz(metin: &str) -> String {
    let bayt = metin.as_bytes();
    let mut sonuc = Vec::with_capacity(bayt.len());
    let mut i = 0;
    while i < bayt.len() {
        if bayt[i] == b'%' && i + 2 < bayt.len() {
            if let Ok(deger) = u8::from_str_radix(&metin[i + 1..i + 3], 16) {
                sonuc.push(deger);
                i += 3;
                continue;
            }
        }
        sonuc.push(if bayt[i] == b'+' { b' ' } else { bayt[i] });
        i += 1;
    }
    String::from_utf8_lossy(&sonuc).into_owned()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sohbet_baglantisi_kimligi_cozer() {
        assert_eq!(
            coz("fusion://sohbet/abc-123_X/"),
            Some(DerinBaglanti::Sohbet {
                id: "abc-123_X".into()
            })
        );
    }

    #[test]
    fn sohbet_kimligi_yol_ayraci_ya_da_bosluk_iceremez() {
        assert_eq!(coz("fusion://sohbet/a/b"), None);
        assert_eq!(coz("fusion://sohbet/a%20b"), None);
        assert_eq!(coz("fusion://sohbet/"), None);
    }

    #[test]
    fn yeni_sohbet_koku_yuzde_kodundan_cozer() {
        assert_eq!(
            coz("fusion://yeni?kok=%2FUsers%2Fali%2FMasa%C3%BCst%C3%BC&x=1"),
            Some(DerinBaglanti::Yeni {
                kok: Some("/Users/ali/Masaüstü".into())
            })
        );
        assert_eq!(
            coz("fusion://yeni"),
            Some(DerinBaglanti::Yeni { kok: None })
        );
    }

    #[test]
    fn ayarlar_bolumu_istege_baglidir() {
        assert_eq!(
            coz("fusion://ayarlar/bildirimler"),
            Some(DerinBaglanti::Ayarlar {
                bolum: Some("bildirimler".into())
            })
        );
        assert_eq!(
            coz("fusion://ayarlar"),
            Some(DerinBaglanti::Ayarlar { bolum: None })
        );
    }

    #[test]
    fn baska_sema_ve_bilinmeyen_yol_reddedilir() {
        assert_eq!(coz("https://fusion/sohbet/x"), None);
        assert_eq!(coz("fusion://bilinmez/x"), None);
        assert_eq!(
            argumanlardan(&["fusion-desktop".into(), "--flag".into()]),
            None
        );
        assert_eq!(
            argumanlardan(&["fusion-desktop".into(), "fusion://sohbet/q1".into()]),
            Some(DerinBaglanti::Sohbet { id: "q1".into() })
        );
    }

    #[test]
    fn olay_yuku_hedef_etiketiyle_serilesir() {
        let yuk = serde_json::to_value(DerinBaglanti::Sohbet { id: "q".into() }).unwrap();
        assert_eq!(yuk["hedef"], "sohbet");
        assert_eq!(yuk["id"], "q");
    }
}
