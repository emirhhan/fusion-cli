//! HTML dosya önizlemesi için AYRI kökenli sunum (U4-47).
//!
//! Ölçüldü (30 Ekim): önizleme `srcdoc` iframe'iydi; srcdoc belgesi ana pencerenin CSP'sini
//! (`script-src 'self'`) miras alır, bu yüzden paketli uygulamada önizlenen sayfanın satır içi
//! betikleri çalışmıyordu. Ana pencerenin CSP'sini gevşetmek tüm uygulamayı gevşetirdi.
//! Çözüm: seçilen dosya `fusion-preview://` özel şemasından, KENDİ (gevşek) CSP başlığıyla sunulur;
//! iframe ayrı kökenli olduğundan ana pencerenin CSP'si ona uygulanmaz ve ana pencere sıkı kalır.
//!
//! Yalnız arayüzün `onizleme_ayarla` ile bıraktığı TEK dosya içeriği sunulur (bellekte, tahmin
//! edilemez bir anahtarla); dosya sistemine erişim yoktur. Göreli kaynaklar (css, görsel) bu yüzden
//! yüklenmez: bilinen sınır.

use std::collections::VecDeque;
use std::sync::Mutex;

use tauri::http::{header, Method, Response, StatusCode};

/// Aynı anda bellekte tutulan önizleme sayısı; eskiler atılır.
const EN_COK_ONIZLEME: usize = 4;
/// Tek önizleme için üst sınır (sunulan HTML); büyük yığınlar belleği şişirmesin.
pub(crate) const EN_COK_BAYT: usize = 5 * 1024 * 1024;
pub(crate) const SEMA: &str = "fusion-preview";

/// Önizlenen sayfanın CSP'si: betikler (satır içi dahil) ve https kaynakları serbest, ama AĞ
/// bağlantısı (`connect-src`), form gönderimi, iç içe çerçeve ve eklenti YOK. Sayfa kendi içeriğini
/// ağa sızdıramaz; ana pencerenin CSP'siyle ilgisi yoktur.
pub(crate) const ONIZLEME_CSP: &str = "default-src 'none'; \
script-src 'unsafe-inline' 'unsafe-eval' data: blob: https:; \
style-src 'unsafe-inline' data: https:; \
img-src data: blob: https:; \
media-src data: blob: https:; \
font-src data: https:; \
connect-src 'none'; \
form-action 'none'; \
frame-src 'none'; \
object-src 'none'; \
base-uri 'none'";

struct Kayit {
    anahtar: String,
    icerik: Vec<u8>,
}

#[derive(Default)]
pub(crate) struct OnizlemeDeposu {
    kayitlar: Mutex<VecDeque<Kayit>>,
}

impl OnizlemeDeposu {
    /// İçeriği bırakır ve tahmin edilemez anahtarını döndürür.
    pub(crate) fn ekle(&self, icerik: String) -> Result<String, String> {
        if icerik.len() > EN_COK_BAYT {
            return Err(format!(
                "önizleme {} MiB sınırını aşıyor",
                EN_COK_BAYT / (1024 * 1024)
            ));
        }
        let mut rastgele = [0u8; 16];
        getrandom::fill(&mut rastgele)
            .map_err(|error| format!("önizleme anahtarı üretilemedi: {error}"))?;
        let anahtar = hex::encode(rastgele);
        let mut kayitlar = self
            .kayitlar
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        kayitlar.push_back(Kayit {
            anahtar: anahtar.clone(),
            icerik: icerik.into_bytes(),
        });
        while kayitlar.len() > EN_COK_ONIZLEME {
            kayitlar.pop_front();
        }
        Ok(anahtar)
    }

    fn getir(&self, anahtar: &str) -> Option<Vec<u8>> {
        self.kayitlar
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .iter()
            .find(|kayit| kayit.anahtar == anahtar)
            .map(|kayit| kayit.icerik.clone())
    }

    /// Özel şema isteğine yanıt: yalnız `GET /<anahtar>`; bilinmeyen her şey 404.
    pub(crate) fn yanit(&self, yontem: &Method, yol: &str) -> Response<Vec<u8>> {
        if yontem != Method::GET && yontem != Method::HEAD {
            return bos_yanit(StatusCode::METHOD_NOT_ALLOWED);
        }
        // Tek bir yol parçası (anahtar) beklenir; `..`, iç içe yol ve sorgu eşleşmez.
        let anahtar = yol.strip_prefix('/').unwrap_or(yol);
        let Some(icerik) = self.getir(anahtar) else {
            return bos_yanit(StatusCode::NOT_FOUND);
        };
        let govde = if yontem == Method::HEAD {
            Vec::new()
        } else {
            icerik
        };
        Response::builder()
            .status(StatusCode::OK)
            .header(header::CONTENT_TYPE, "text/html; charset=utf-8")
            .header(header::CONTENT_SECURITY_POLICY, ONIZLEME_CSP)
            .header(header::X_CONTENT_TYPE_OPTIONS, "nosniff")
            .header(header::REFERRER_POLICY, "no-referrer")
            .header(header::CACHE_CONTROL, "no-store")
            .body(govde)
            .unwrap_or_else(|_| bos_yanit(StatusCode::INTERNAL_SERVER_ERROR))
    }
}

fn bos_yanit(durum: StatusCode) -> Response<Vec<u8>> {
    Response::builder()
        .status(durum)
        .header(header::CONTENT_TYPE, "text/plain; charset=utf-8")
        .header(header::X_CONTENT_TYPE_OPTIONS, "nosniff")
        .body(Vec::new())
        .expect("sabit başlıklarla yanıt kurulabilir")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn csp_yonergesi<'a>(csp: &'a str, ad: &str) -> Option<&'a str> {
        csp.split(';')
            .map(str::trim)
            .find(|parca| parca.split_whitespace().next() == Some(ad))
    }

    #[test]
    fn eklenen_icerik_kendi_gevsek_csp_ile_sunulur() {
        let depo = OnizlemeDeposu::default();
        let anahtar = depo.ekle("<script>alert(1)</script>".into()).unwrap();

        let yanit = depo.yanit(&Method::GET, &format!("/{anahtar}"));

        assert_eq!(yanit.status(), StatusCode::OK);
        assert_eq!(yanit.body(), b"<script>alert(1)</script>");
        let csp = yanit.headers()[header::CONTENT_SECURITY_POLICY]
            .to_str()
            .unwrap();
        assert!(csp_yonergesi(csp, "script-src")
            .unwrap()
            .contains("'unsafe-inline'"));
        assert_eq!(
            csp_yonergesi(csp, "connect-src"),
            Some("connect-src 'none'")
        );
        assert_eq!(csp_yonergesi(csp, "frame-src"), Some("frame-src 'none'"));
        assert_eq!(yanit.headers()[header::X_CONTENT_TYPE_OPTIONS], "nosniff");
    }

    #[test]
    fn bilinmeyen_anahtar_ve_yol_gezinmesi_404_verir() {
        let depo = OnizlemeDeposu::default();
        let anahtar = depo.ekle("x".into()).unwrap();

        for yol in [
            "/yok",
            "/",
            "",
            "/../etc/passwd",
            &format!("/{anahtar}/ek"),
            &format!("/{anahtar}?a=1"),
            &format!("//{anahtar}"),
        ] {
            assert_eq!(
                depo.yanit(&Method::GET, yol).status(),
                StatusCode::NOT_FOUND,
                "{yol} sunulmamalı"
            );
        }
    }

    #[test]
    fn yalniz_get_ve_head_kabul_edilir() {
        let depo = OnizlemeDeposu::default();
        let anahtar = depo.ekle("govde".into()).unwrap();
        let yol = format!("/{anahtar}");

        assert_eq!(
            depo.yanit(&Method::POST, &yol).status(),
            StatusCode::METHOD_NOT_ALLOWED
        );
        let head = depo.yanit(&Method::HEAD, &yol);
        assert_eq!(head.status(), StatusCode::OK);
        assert!(head.body().is_empty());
    }

    #[test]
    fn en_eski_onizleme_sinir_asilinca_atilir() {
        let depo = OnizlemeDeposu::default();
        let ilk = depo.ekle("ilk".into()).unwrap();
        for sira in 0..EN_COK_ONIZLEME {
            depo.ekle(format!("sonraki {sira}")).unwrap();
        }

        assert_eq!(
            depo.yanit(&Method::GET, &format!("/{ilk}")).status(),
            StatusCode::NOT_FOUND
        );
    }

    #[test]
    fn anahtarlar_tahmin_edilemez_ve_benzersizdir() {
        let depo = OnizlemeDeposu::default();
        let a = depo.ekle("a".into()).unwrap();
        let b = depo.ekle("a".into()).unwrap();
        assert_ne!(a, b);
        assert_eq!(a.len(), 32);
        assert!(a.chars().all(|harf| harf.is_ascii_hexdigit()));
    }

    #[test]
    fn boyut_siniri_asilirsa_reddedilir() {
        let depo = OnizlemeDeposu::default();
        assert!(depo.ekle("a".repeat(EN_COK_BAYT + 1)).is_err());
        assert!(depo.ekle("a".repeat(EN_COK_BAYT)).is_ok());
    }

    /// Ana pencerenin CSP'si ÖNİZLEME yüzünden gevşemez: betik kaynağı 'self' kalır, satır içi/eval yok
    /// ve yalnız önizleme kökeni çerçevelenebilir (U4-47).
    #[test]
    fn ana_pencere_csp_gevsemez_yalniz_onizleme_cercevesi_eklenir() {
        let yapilandirma: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
        let guvenlik = &yapilandirma["app"]["security"];
        for ad in ["csp", "devCsp"] {
            let script = guvenlik[ad]["script-src"].as_str().unwrap();
            assert!(
                !script.contains("'unsafe-eval'"),
                "{ad}: script-src gevşemiş"
            );
            let frame = guvenlik[ad]["frame-src"].as_str().unwrap();
            assert!(
                frame.contains("fusion-preview:"),
                "{ad}: frame-src önizleme şemasını içermeli"
            );
            assert!(
                frame.contains("http://fusion-preview.localhost"),
                "{ad}: Windows kökeni eksik"
            );
        }
        let script = guvenlik["csp"]["script-src"].as_str().unwrap();
        assert_eq!(
            script, "'self'",
            "paketli CSP'de satır içi betik açılmamalı"
        );
    }
}
