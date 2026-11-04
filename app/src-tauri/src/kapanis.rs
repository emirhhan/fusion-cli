//! Kapanış isteğinin durumu ve zaman aşımı kararları (R2-14).
//!
//! Ana pencerenin yerel kapatma düğmesi kapanışı doğrudan başlatır. Cmd+Q menüsü ve
//! `ExitRequested` için Rust kapatmayı durdurup onayı arayüze sordurur. Ölçüldü
//! (30 Ekim): arayüz yanıt vermiyorsa (donmuş
//! web görünümü, çöken sayfa) bu bekleme sonsuzdu; kullanıcı uygulamayı yalnız süreci öldürerek
//! kapatabiliyordu. Burada iki sınır vardır:
//!
//! - Soru açıkken arayüz `kapatma_nabzi` ile canlı olduğunu bildirir; `NABIZ_ZAMAN_ASIMI` boyunca
//!   nabız gelmezse arayüz ölü sayılır ve kapanış ONAYSIZ sürdürülür.
//! - Onaydan (ya da zorunlu karardan) sonra temizlik en çok `TEMIZLIK_UST_SINIRI` sürer; aşılırsa
//!   süreç sonlandırılır.
//!
//! Burası saf karar mantığıdır (saat dışarıdan verilir); pencere/olay bağlantısı `lib.rs`'te.

use std::sync::Mutex;
use std::time::{Duration, Instant};

/// Soru açıkken arayüzden bu kadar süre nabız gelmezse arayüz yanıtsız sayılır.
pub(crate) const NABIZ_ZAMAN_ASIMI: Duration = Duration::from_secs(10);
/// Onaydan sonra temizlik + çıkış için tanınan en uzun süre.
pub(crate) const TEMIZLIK_UST_SINIRI: Duration = Duration::from_secs(10);
/// Bekçi iş parçacığının kontrol aralığı.
pub(crate) const BEKCI_ARALIGI: Duration = Duration::from_millis(500);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Asama {
    /// Kapanış istenmedi (ya da kullanıcı vazgeçti).
    Bosta,
    /// Arayüze soruldu; yanıt bekleniyor.
    Soruluyor { son_nabiz: Instant },
    /// Kapanış kararlaştırıldı (kullanıcı onayı ya da arayüz yanıtsız); temizlik sürüyor.
    Onaylandi { baslangic: Instant },
}

/// Bekçinin her turda aldığı karar.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Karar {
    /// Bekleyen kapanış yok; bekçi biter.
    Bosta,
    /// Süre dolmadı.
    Bekle,
    /// Arayüz nabzı kesildi: kapanışı onaysız sürdür (temizlik + çıkış).
    ArayuzYanitsiz,
    /// Onaydan sonra temizlik süresi aştı: süreci sonlandır.
    TemizlikAsildi,
}

pub(crate) struct KapanisDurumu {
    asama: Mutex<Asama>,
}

impl KapanisDurumu {
    pub(crate) fn new() -> Self {
        Self {
            asama: Mutex::new(Asama::Bosta),
        }
    }

    fn kilit(&self) -> std::sync::MutexGuard<'_, Asama> {
        self.asama
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
    }

    /// Kapanış istendi. Dönüş `true` ise bu İLK istektir ve bekçi başlatılmalıdır; zaten
    /// soruluyorsa nabız yenilenir (ikinci Cmd+Q aynı soruyu tekrar gösterir, ikinci bekçi açmaz).
    /// Onaylanmış kapanış geri alınmaz.
    pub(crate) fn iste(&self, simdi: Instant) -> bool {
        let mut asama = self.kilit();
        match *asama {
            Asama::Bosta => {
                *asama = Asama::Soruluyor { son_nabiz: simdi };
                true
            }
            Asama::Soruluyor { .. } => {
                *asama = Asama::Soruluyor { son_nabiz: simdi };
                false
            }
            Asama::Onaylandi { .. } => false,
        }
    }

    /// Arayüz canlı. Yalnız soru açıkken anlamlıdır; onaydan sonra gelen nabız süreyi UZATMAZ.
    pub(crate) fn nabiz(&self, simdi: Instant) {
        let mut asama = self.kilit();
        if let Asama::Soruluyor { .. } = *asama {
            *asama = Asama::Soruluyor { son_nabiz: simdi };
        }
    }

    /// Kullanıcı vazgeçti ("İptal"). Onaylanmış kapanış geri alınamaz.
    pub(crate) fn vazgec(&self) {
        let mut asama = self.kilit();
        if let Asama::Soruluyor { .. } = *asama {
            *asama = Asama::Bosta;
        }
    }

    /// Kapanış kararlaştırıldı. Dönüş `true` ise bu geçişi BU çağrı yaptı (ilk onay); bekçi
    /// zaten çalışıyor olabilir, bu yüzden bekçi başlatma kararı `iste`/`onayla` dönüşlerinin
    /// birleşiminden verilir (bkz. `bekci_gerekli`).
    pub(crate) fn onayla(&self, simdi: Instant) -> OnayDonusu {
        let mut asama = self.kilit();
        match *asama {
            Asama::Bosta => {
                *asama = Asama::Onaylandi { baslangic: simdi };
                OnayDonusu::YeniVeBekciYok
            }
            Asama::Soruluyor { .. } => {
                *asama = Asama::Onaylandi { baslangic: simdi };
                OnayDonusu::Yeni
            }
            Asama::Onaylandi { .. } => OnayDonusu::ZatenOnayli,
        }
    }

    pub(crate) fn onayli_mi(&self) -> bool {
        matches!(*self.kilit(), Asama::Onaylandi { .. })
    }

    pub(crate) fn karar(&self, simdi: Instant) -> Karar {
        match *self.kilit() {
            Asama::Bosta => Karar::Bosta,
            Asama::Soruluyor { son_nabiz } => {
                if simdi.saturating_duration_since(son_nabiz) >= NABIZ_ZAMAN_ASIMI {
                    Karar::ArayuzYanitsiz
                } else {
                    Karar::Bekle
                }
            }
            Asama::Onaylandi { baslangic } => {
                if simdi.saturating_duration_since(baslangic) >= TEMIZLIK_UST_SINIRI {
                    Karar::TemizlikAsildi
                } else {
                    Karar::Bekle
                }
            }
        }
    }
}

/// `onayla`nın sonucu: bekçinin gerekip gerekmediğini söyler.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum OnayDonusu {
    /// Soru açıktı; bekçi zaten çalışıyor.
    Yeni,
    /// Soru hiç açılmadan onaylandı (doğrudan `kapatmayi_onayla`); temizlik sınırı için bekçi gerekir.
    YeniVeBekciYok,
    /// Zaten onaylıydı.
    ZatenOnayli,
}

impl OnayDonusu {
    pub(crate) fn bekci_gerekli(self) -> bool {
        self == Self::YeniVeBekciYok
    }
}

/// Tam kapanışı yalnız bir çağrı sahiplenir. Yerel gizleme temizlik işinden önce
/// istenir; temizlik ayrı iş parçacığında başlatılır. Arayüz onayı/nabzı gerekmez.
/// Bekçi önce başlatılır: gizleme veya temizlikteki bir sorun süre sınırını kaldıramaz.
pub(crate) fn baslat_tam_kapanis(
    durum: &KapanisDurumu,
    simdi: Instant,
    bekci_baslat: impl FnOnce(),
    gizle: impl FnOnce(),
    temizlik_baslat: impl FnOnce(),
) -> bool {
    let donus = durum.onayla(simdi);
    if donus == OnayDonusu::ZatenOnayli {
        return false;
    }
    if donus.bekci_gerekli() {
        bekci_baslat();
    }
    gizle();
    temizlik_baslat();
    true
}

/// `ExitRequested` olayında kapanış arayüze sorulmalı mı?
///
/// Yalnız KULLANICI kaynaklı çıkış (`code == None`) sorulur; `app.exit(kod)` ve yeniden başlatma
/// (kodlu) programatik olduğundan sorulmadan sürer. Ana pencere yoksa (son pencere kapanmış) soracak
/// kimse yoktur; onaylanmış kapanış da yeniden sorulmaz.
pub(crate) fn cikis_sorulmali(code: Option<i32>, ana_pencere_var: bool, onayli: bool) -> bool {
    code.is_none() && ana_pencere_var && !onayli
}

#[cfg(test)]
mod tests {
    use super::*;

    fn t(saniye: u64, taban: Instant) -> Instant {
        taban + Duration::from_secs(saniye)
    }

    #[test]
    fn ilk_istek_bekci_baslatir_ikincisi_baslatmaz() {
        let taban = Instant::now();
        let durum = KapanisDurumu::new();
        assert!(durum.iste(taban));
        assert!(!durum.iste(t(1, taban)));
    }

    #[test]
    fn nabiz_geldikce_arayuz_yanitsiz_sayilmaz() {
        let taban = Instant::now();
        let durum = KapanisDurumu::new();
        durum.iste(taban);
        for saniye in 1..=30 {
            durum.nabiz(t(saniye, taban));
            assert_eq!(durum.karar(t(saniye, taban)), Karar::Bekle);
        }
    }

    /// Ölçüldü (30 Ekim): nabız denetimi yoktu; yanıtsız arayüzde kapanış sonsuza dek bekliyordu.
    #[test]
    fn nabiz_kesilince_sure_dolunca_arayuz_yanitsiz_sayilir() {
        let taban = Instant::now();
        let durum = KapanisDurumu::new();
        durum.iste(taban);
        durum.nabiz(t(3, taban));
        assert_eq!(durum.karar(t(12, taban)), Karar::Bekle);
        assert_eq!(durum.karar(t(13, taban)), Karar::ArayuzYanitsiz);
    }

    #[test]
    fn hic_nabiz_gelmezse_istekten_sayilir() {
        let taban = Instant::now();
        let durum = KapanisDurumu::new();
        durum.iste(taban);
        assert_eq!(durum.karar(t(9, taban)), Karar::Bekle);
        assert_eq!(durum.karar(t(10, taban)), Karar::ArayuzYanitsiz);
    }

    #[test]
    fn vazgecmek_bekciyi_bitirir_ve_yeni_istek_yeniden_baslatir() {
        let taban = Instant::now();
        let durum = KapanisDurumu::new();
        durum.iste(taban);
        durum.vazgec();
        assert_eq!(durum.karar(t(60, taban)), Karar::Bosta);
        assert!(durum.iste(t(61, taban)));
    }

    #[test]
    fn onaydan_sonra_temizlik_siniri_asilirsa_surec_sonlandirilir() {
        let taban = Instant::now();
        let durum = KapanisDurumu::new();
        durum.iste(taban);
        assert_eq!(durum.onayla(t(2, taban)), OnayDonusu::Yeni);
        assert_eq!(durum.karar(t(11, taban)), Karar::Bekle);
        assert_eq!(durum.karar(t(12, taban)), Karar::TemizlikAsildi);
    }

    #[test]
    fn onaydan_sonra_gelen_nabiz_ve_vazgec_onayi_geri_almaz() {
        let taban = Instant::now();
        let durum = KapanisDurumu::new();
        durum.iste(taban);
        durum.onayla(taban);
        durum.nabiz(t(5, taban));
        durum.vazgec();
        assert!(durum.onayli_mi());
        // Nabız süreyi uzatmaz: sınır onay anından sayılır.
        assert_eq!(durum.karar(t(10, taban)), Karar::TemizlikAsildi);
    }

    #[test]
    fn soru_acilmadan_onay_bekci_ister() {
        let durum = KapanisDurumu::new();
        let sonuc = durum.onayla(Instant::now());
        assert_eq!(sonuc, OnayDonusu::YeniVeBekciYok);
        assert!(sonuc.bekci_gerekli());
        assert_eq!(durum.onayla(Instant::now()), OnayDonusu::ZatenOnayli);
        assert!(!OnayDonusu::Yeni.bekci_gerekli());
    }

    #[test]
    fn cikis_yalniz_kullanici_kaynakliysa_ve_pencere_varsa_sorulur() {
        // Kullanıcı kaynaklı (kodsuz) çıkış: sor.
        assert!(cikis_sorulmali(None, true, false));
        // app.exit(0) / yeniden başlatma: programatik, sorma.
        assert!(!cikis_sorulmali(Some(0), true, false));
        assert!(!cikis_sorulmali(Some(i32::MAX), true, false));
        // Ana pencere yok: soracak arayüz yok.
        assert!(!cikis_sorulmali(None, false, false));
        // Zaten onaylandı.
        assert!(!cikis_sorulmali(None, true, true));
    }

    #[test]
    fn yerel_kapatma_arayuz_onayi_beklemeden_gizler_ve_temizligi_baslatir() {
        let durum = KapanisDurumu::new();
        let simdi = Instant::now();
        let sira = std::cell::RefCell::new(Vec::new());
        assert!(baslat_tam_kapanis(
            &durum,
            simdi,
            || sira.borrow_mut().push("bekci"),
            || sira.borrow_mut().push("gizle"),
            || sira.borrow_mut().push("temizlik"),
        ));
        assert_eq!(*sira.borrow(), ["bekci", "gizle", "temizlik"]);
        assert!(durum.onayli_mi());
        assert!(!cikis_sorulmali(None, true, durum.onayli_mi()));
        assert_eq!(durum.karar(simdi), Karar::Bekle);
        assert_eq!(
            durum.karar(simdi + TEMIZLIK_UST_SINIRI),
            Karar::TemizlikAsildi
        );
    }

    #[test]
    fn tekrarlanan_yerel_kapatma_temizligi_ve_bekciyi_yeniden_baslatmaz() {
        let durum = KapanisDurumu::new();
        let sira = std::cell::RefCell::new(Vec::new());
        for _ in 0..2 {
            baslat_tam_kapanis(
                &durum,
                Instant::now(),
                || sira.borrow_mut().push("bekci"),
                || sira.borrow_mut().push("gizle"),
                || sira.borrow_mut().push("temizlik"),
            );
        }
        assert_eq!(*sira.borrow(), ["bekci", "gizle", "temizlik"]);
    }

    #[test]
    fn acik_onay_sorusundan_yerel_kapatma_ikinci_bekci_baslatmaz() {
        let durum = KapanisDurumu::new();
        let simdi = Instant::now();
        assert!(durum.iste(simdi));
        let sira = std::cell::RefCell::new(Vec::new());
        assert!(baslat_tam_kapanis(
            &durum,
            simdi,
            || sira.borrow_mut().push("bekci"),
            || sira.borrow_mut().push("gizle"),
            || sira.borrow_mut().push("temizlik"),
        ));
        assert_eq!(*sira.borrow(), ["gizle", "temizlik"]);
        durum.vazgec();
        assert!(durum.onayli_mi());
    }

    #[test]
    fn eszamanli_yerel_kapatmalardan_yalniz_biri_temizlik_sahibi_olur() {
        use std::sync::atomic::{AtomicUsize, Ordering};
        use std::sync::{Arc, Barrier};

        let durum = Arc::new(KapanisDurumu::new());
        let sayaclar = Arc::new([
            AtomicUsize::new(0),
            AtomicUsize::new(0),
            AtomicUsize::new(0),
        ]);
        let basla = Arc::new(Barrier::new(8));
        let mut isler = Vec::new();
        for _ in 0..8 {
            let durum = Arc::clone(&durum);
            let sayaclar = Arc::clone(&sayaclar);
            let basla = Arc::clone(&basla);
            isler.push(std::thread::spawn(move || {
                basla.wait();
                baslat_tam_kapanis(
                    &durum,
                    Instant::now(),
                    || {
                        sayaclar[0].fetch_add(1, Ordering::SeqCst);
                    },
                    || {
                        sayaclar[1].fetch_add(1, Ordering::SeqCst);
                    },
                    || {
                        sayaclar[2].fetch_add(1, Ordering::SeqCst);
                    },
                )
            }));
        }
        assert_eq!(
            isler
                .into_iter()
                .map(|is| is.join().unwrap())
                .filter(|basladi| *basladi)
                .count(),
            1
        );
        for sayac in sayaclar.iter() {
            assert_eq!(sayac.load(Ordering::SeqCst), 1);
        }
    }
}
