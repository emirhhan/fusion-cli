//! Sistem tepsisi / menü çubuğu simgesi (P-064).
//!
//! Simge menüsü: Fusion'ı göster, Yeni sohbet, Çıkış. Araç ipucu çalışan tur sayısını
//! yazar (`tepsi_durum`). Arayüzdeki tercih (Ayarlar › Genel) `tepsi_ayarla` ile
//! simgeyi kurar ya da kaldırır; varsayılan açık. Simge yalnız Dock/pencere dışı bir
//! giriş noktasıdır; kapanış kuralları değişmez (Çıkış yine onay sorar).

use std::sync::Mutex;

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{TrayIcon, TrayIconBuilder};
use tauri::{Emitter, Manager};

pub const TEPSI_KIMLIGI: &str = "fusion-tepsi";
pub const MENU_GOSTER: &str = "tepsi-goster";
pub const MENU_YENI_SOHBET: &str = "tepsi-yeni-sohbet";
pub const MENU_CIKIS: &str = "tepsi-cikis";
/// Tepsiden "Yeni sohbet" seçilince arayüzün dinlediği olay.
pub const OLAY_YENI_SOHBET: &str = "uygulama://yeni-sohbet";

#[derive(Default)]
pub struct TepsiDurumu {
    simge: Mutex<Option<TrayIcon>>,
}

/// Araç ipucu metni: çalışan tur sayısına göre.
pub fn ipucu(calisan: u32) -> String {
    match calisan {
        0 => "Fusion".to_string(),
        1 => "Fusion · 1 sohbet çalışıyor".to_string(),
        n => format!("Fusion · {n} sohbet çalışıyor"),
    }
}

fn kur(app: &tauri::AppHandle) -> tauri::Result<TrayIcon> {
    let goster = MenuItem::with_id(app, MENU_GOSTER, "Fusion'ı göster", true, None::<&str>)?;
    let yeni = MenuItem::with_id(app, MENU_YENI_SOHBET, "Yeni sohbet", true, None::<&str>)?;
    let cikis = MenuItem::with_id(app, MENU_CIKIS, "Çıkış", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&goster, &yeni, &cikis])?;
    let mut insa = TrayIconBuilder::with_id(TEPSI_KIMLIGI)
        .menu(&menu)
        .show_menu_on_left_click(true)
        .tooltip(ipucu(0));
    if let Some(simge) = app.default_window_icon() {
        insa = insa.icon(simge.clone());
    }
    insa.build(app)
}

/// Simgeyi aç ya da kapat. Zaten istenen durumdaysa dokunmaz.
pub fn ayarla(app: &tauri::AppHandle, acik: bool) -> Result<(), String> {
    let durum = app.state::<TepsiDurumu>();
    let mut simge = durum
        .simge
        .lock()
        .map_err(|_| "tepsi kilidi bozuk".to_string())?;
    match (acik, simge.as_ref()) {
        (true, None) => {
            *simge = Some(kur(app).map_err(|hata| format!("tepsi simgesi kurulamadı: {hata}"))?);
        }
        (false, Some(_)) => {
            // `TrayIcon` düşürülünce simge kaldırılır (Tauri sahipliği).
            *simge = None;
            let _ = app.remove_tray_by_id(TEPSI_KIMLIGI);
        }
        _ => {}
    }
    Ok(())
}

/// Çalışan tur sayısını araç ipucuna yaz; simge kapalıysa sessizce geçer.
pub fn durum(app: &tauri::AppHandle, calisan: u32) -> Result<(), String> {
    let durum = app.state::<TepsiDurumu>();
    let simge = durum
        .simge
        .lock()
        .map_err(|_| "tepsi kilidi bozuk".to_string())?;
    if let Some(simge) = simge.as_ref() {
        simge
            .set_tooltip(Some(ipucu(calisan)))
            .map_err(|hata| format!("tepsi ipucu yazılamadı: {hata}"))?;
    }
    Ok(())
}

/// Tepsi menüsü olaylarını işle; tepsiye ait değilse `false`.
/// Çıkış doğrudan kapatmaz: çağıran onay akışını (`kapatma_iste`) kendisi yürütür.
pub fn menu_olayi(app: &tauri::AppHandle, kimlik: &str) -> TepsiKarar {
    match kimlik {
        MENU_GOSTER => {
            ana_pencereyi_goster(app);
            TepsiKarar::Islendi
        }
        MENU_YENI_SOHBET => {
            ana_pencereyi_goster(app);
            if let Err(hata) = app.emit(OLAY_YENI_SOHBET, ()) {
                eprintln!("[fusion][tepsi] yeni sohbet olayı yayınlanamadı: {hata}");
            }
            TepsiKarar::Islendi
        }
        MENU_CIKIS => TepsiKarar::CikisIstendi,
        _ => TepsiKarar::TepsiyeAitDegil,
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TepsiKarar {
    Islendi,
    CikisIstendi,
    TepsiyeAitDegil,
}

fn ana_pencereyi_goster(app: &tauri::AppHandle) {
    if let Some(ana) = app.get_webview_window("main") {
        let _ = ana.unminimize();
        let _ = ana.show();
        let _ = ana.set_focus();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ipucu_calisan_sayisini_turkce_yazar() {
        assert_eq!(ipucu(0), "Fusion");
        assert_eq!(ipucu(1), "Fusion · 1 sohbet çalışıyor");
        assert_eq!(ipucu(3), "Fusion · 3 sohbet çalışıyor");
    }

    #[test]
    fn menu_kimlikleri_birbirinden_farklidir() {
        let kimlikler = [MENU_GOSTER, MENU_YENI_SOHBET, MENU_CIKIS];
        for (i, a) in kimlikler.iter().enumerate() {
            for b in &kimlikler[i + 1..] {
                assert_ne!(a, b);
            }
        }
    }
}
