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

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;

use serde::Serialize;
use tauri::{Emitter, Manager};

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

/// Arayüz dinleyicisi kurulmadan gelen hedefin bekletildiği yer (soğuk açılış).
///
/// Ölçüldü (31 Ekim): uygulama kapalıyken tıklanan `fusion://sohbet/x` için macOS
/// `RunEvent::Opened`'ı arayüz yüklenmeden veriyor; `emit` o anda kimseye ulaşmıyor ve
/// Tauri olayı kuyruklamıyor — bağlantı sessizce kayboluyordu. Arayüz hazır olunca
/// `derin_baglanti_al` komutuyla bekleyen hedefi çeker; ondan sonrası yayınla gider.
#[derive(Default)]
pub struct Bekleyen {
    hazir: AtomicBool,
    hedef: Mutex<Option<DerinBaglanti>>,
}

/// `Bekleyen::yonlendir` kararı.
#[derive(Debug, PartialEq, Eq)]
pub enum Teslim {
    /// Arayüz dinliyor: olay yayınlanır.
    Yayinla,
    /// Arayüz henüz yok: hedef saklandı, `al` ile teslim edilecek.
    Beklet,
}

impl Bekleyen {
    pub fn yonlendir(&self, hedef: &DerinBaglanti) -> Teslim {
        if self.hazir.load(Ordering::SeqCst) {
            return Teslim::Yayinla;
        }
        // Son gelen kazanır: açılışta iki bağlantı tıklanırsa kullanıcı sonuncuyu bekler.
        *self.hedef.lock().unwrap_or_else(|zehir| zehir.into_inner()) = Some(hedef.clone());
        Teslim::Beklet
    }

    /// Arayüz hazır: bekleyen hedefi (varsa) ver ve bundan sonra yayınla yoluna geç.
    pub fn al(&self) -> Option<DerinBaglanti> {
        self.hazir.store(true, Ordering::SeqCst);
        self.hedef
            .lock()
            .unwrap_or_else(|zehir| zehir.into_inner())
            .take()
    }
}

/// Soğuk açılış (Windows/Linux): ilk örneğin kendi argümanındaki `fusion://` adresini beklet.
///
/// Ölçüldü (31 Ekim): Windows ve Linux'ta kapalı uygulamaya tıklanan bağlantı ilk sürecin
/// `argv[1]`'i olarak gelir; tek örnek eklentisi yalnız İKİNCİ sürecin argümanını iletir ve
/// `setup` ilk sürecin argümanına hiç bakmıyordu — bağlantı uygulamayı açıp hedefe gitmiyordu.
/// macOS adresi argümanla değil `RunEvent::Opened` ile verir; orada bu çağrı bir şey bulmaz.
pub fn acilista_beklet(bekleyen: &Bekleyen, args: &[String]) -> bool {
    match argumanlardan(args) {
        Some(hedef) => bekleyen.yonlendir(&hedef) == Teslim::Beklet,
        None => false,
    }
}

/// Ana pencereyi öne getir ve hedefi arayüze ilet (dinleyici yoksa beklet).
pub fn ilet(app: &tauri::AppHandle, hedef: &DerinBaglanti) {
    if let Some(ana) = app.get_webview_window_main() {
        let _ = ana.unminimize();
        let _ = ana.show();
        let _ = ana.set_focus();
    }
    if app.state::<Bekleyen>().yonlendir(hedef) == Teslim::Beklet {
        return;
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

/// Yüzde kodunu çöz (`%2F` → `/`, `+` → boşluk); bozuk `%` dizisi olduğu gibi kalır.
///
/// Yalnız BAYT düzeyinde çalışır: iki onaltılık basamak `is_ascii_hexdigit` ile denetlenir,
/// metin hiç dilimlenmez. Ölçüldü (31 Ekim): `&metin[i+1..i+3]` dilimi `%aé` gibi girdide
/// çok baytlı karakterin ortasına düşüp panik atıyor; dış kaynaklı adres uygulamayı
/// kapatıyordu.
fn yuzde_coz(metin: &str) -> String {
    let bayt = metin.as_bytes();
    let mut sonuc = Vec::with_capacity(bayt.len());
    let mut i = 0;
    while i < bayt.len() {
        if bayt[i] == b'%' {
            if let Some(deger) = onaltilik_cift(bayt.get(i + 1), bayt.get(i + 2)) {
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

fn onaltilik_cift(ust: Option<&u8>, alt: Option<&u8>) -> Option<u8> {
    // ASCII dışı bayt `char`'a dönüşünce `to_digit` None verir; dilimleme yok.
    let ust = (*ust? as char).to_digit(16)?;
    let alt = (*alt? as char).to_digit(16)?;
    Some((ust * 16 + alt) as u8)
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
    fn yuzde_kodu_cok_baytli_karakterin_ortasina_dusunce_panik_atmaz() {
        // Ölçüldü (31 Ekim): `%a` ardından 'é' gelince `&metin[i+1..i+3]` char sınırı
        // dışında kalıyor ve dışarıdan gelen adres uygulamayı çökertiyordu.
        assert_eq!(yuzde_coz("%aé"), "%aé");
        assert_eq!(yuzde_coz("%é"), "%é");
        assert_eq!(yuzde_coz("%a"), "%a");
        assert_eq!(yuzde_coz("%"), "%");
        assert_eq!(yuzde_coz("%zz"), "%zz");
        assert_eq!(yuzde_coz("a+b%20c"), "a b c");
        assert_eq!(
            coz("fusion://yeni?kok=%aé"),
            Some(DerinBaglanti::Yeni {
                kok: Some("%aé".into())
            })
        );
        assert_eq!(coz("fusion://sohbet/%aé"), None);
        assert_eq!(
            coz("fusion://ayarlar/%aé"),
            Some(DerinBaglanti::Ayarlar {
                bolum: Some("%aé".into())
            })
        );
    }

    #[test]
    fn arayuz_hazir_olmadan_gelen_hedef_bekletilir_ve_bir_kez_teslim_edilir() {
        let bekleyen = Bekleyen::default();
        let ilk = DerinBaglanti::Sohbet { id: "a".into() };
        let son = DerinBaglanti::Ayarlar { bolum: None };
        assert_eq!(bekleyen.yonlendir(&ilk), Teslim::Beklet);
        assert_eq!(bekleyen.yonlendir(&son), Teslim::Beklet);
        // Arayüz hazır: son gelen teslim edilir, ikinci çekiş boş döner.
        assert_eq!(bekleyen.al(), Some(son));
        assert_eq!(bekleyen.al(), None);
        // Bundan sonra gelen yayınlanır, bekletilmez.
        assert_eq!(bekleyen.yonlendir(&ilk), Teslim::Yayinla);
        assert_eq!(bekleyen.al(), None);
    }

    #[test]
    fn soguk_acilista_ilk_surecin_argumani_bekletilir() {
        let bekleyen = Bekleyen::default();
        let args = vec![
            "C:\\Program Files\\Fusion\\Fusion.exe".to_string(),
            "fusion://sohbet/k9".to_string(),
        ];
        assert!(acilista_beklet(&bekleyen, &args));
        assert_eq!(
            bekleyen.al(),
            Some(DerinBaglanti::Sohbet { id: "k9".into() })
        );
        // macOS'ta argüman yoktur; hiçbir şey bekletilmez.
        let bos = Bekleyen::default();
        assert!(!acilista_beklet(
            &bos,
            &["/Applications/Fusion.app".to_string()]
        ));
        assert_eq!(bos.al(), None);
    }

    #[test]
    fn sema_kaydi_windows_ve_linux_paketleyicisine_verilir() {
        // Paketleyici (tauri-bundler) `plugins > deep-link > desktop > schemes` alanından NSIS
        // kayıt defteri girdilerini ve Linux `.desktop` MimeType'ını üretir; çalışma anında eklenti
        // gerekmez (adres argüman olarak gelir).
        let yapilandirma: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
        assert_eq!(
            yapilandirma["plugins"]["deep-link"]["desktop"]["schemes"][0],
            SEMA
        );
        assert!(include_str!("../Info.plist").contains("<string>fusion</string>"));
    }

    #[test]
    fn olay_yuku_hedef_etiketiyle_serilesir() {
        let yuk = serde_json::to_value(DerinBaglanti::Sohbet { id: "q".into() }).unwrap();
        assert_eq!(yuk["hedef"], "sohbet");
        assert_eq!(yuk["id"], "q");
    }
}
