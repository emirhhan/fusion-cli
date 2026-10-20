import Foundation
import Speech
import AVFoundation
import Darwin

// Fusion konuşma tanıma yardımcısı. Ses tamponları yalnız cihazda işlenir.
struct TanimaOlayi: Codable {
    let tur: String
    let metin: String
    let guven: Float?
    let speech_ms: Int
    let segment: Int

    enum CodingKeys: String, CodingKey { case tur, metin, guven, speech_ms, segment }

    func encode(to encoder: Encoder) throws {
        var kutu = encoder.container(keyedBy: CodingKeys.self)
        try kutu.encode(tur, forKey: .tur)
        try kutu.encode(metin, forKey: .metin)
        if let guven = guven { try kutu.encode(guven, forKey: .guven) }
        else { try kutu.encodeNil(forKey: .guven) }
        try kutu.encode(speech_ms, forKey: .speech_ms)
        try kutu.encode(segment, forKey: .segment)
    }
}

func yaz(_ tur: String, _ metin: String = "", guven: Float? = nil, speechMs: Int = 0, segment: Int = 0) {
    let olay = TanimaOlayi(tur: tur, metin: metin, guven: guven, speech_ms: speechMs, segment: segment)
    if let veri = try? JSONEncoder().encode(olay), let satır = String(data: veri, encoding: .utf8) {
        print(satır); fflush(stdout)
    }
}

final class SesEtkinligiKapisi {
    private let kalibrasyonMs = 300
    private let enAzKonusmaMs = 250
    private let baslangicDogrulamaMs = 60
    // Yavaş konuşan biri cümle ortasında duraklayınca tur kesilmesin: 350 ms
    // cümlenin başını gönderiyordu. İnsanlar arası doğal duraklama 1-2 sn'dir.
    let bitisDogrulamaMs = 2000
    private var gecenMs = 0
    private var kalibrasyonEnDusuk: Float = .greatestFiniteMagnitude
    /// Sürekli izlenen ortam gürültüsü tabanı (asgari istatistik: hızlı iner, yavaş çıkar).
    private var taban: Float = 0
    private var kalibrasyonOrnegi = 0
    private var yuksekMs = 0
    private var sessizMs = 0
    private(set) var konusmaMs = 0
    private(set) var etkin = false
    private(set) var segment = 0

    var finalIcinYeterli: Bool { yeterliKonusma(konusmaMs) }
    func yeterliKonusma(_ sure: Int) -> Bool { sure >= enAzKonusmaMs }

    func isle(rms: Float, sureMs: Int) -> String? {
        if gecenMs < kalibrasyonMs {
            // Ses işleme motoru açılırken ilk tamponlar yüksek bir geçici
            // üretir (günlükte 0.05–0.15). Ortalama bu geçiciyi gürültü
            // sanıp eşiği konuşmanın üstüne çıkarıyordu; kapı hiç açılmıyor,
            // tur hiç kapanmıyordu. En düşük örnek gerçek taban gürültüsüdür.
            if rms > 0 { kalibrasyonEnDusuk = min(kalibrasyonEnDusuk, rms) }
            kalibrasyonOrnegi += 1
            gecenMs += sureMs
            return nil
        }
        if taban == 0 { taban = kalibrasyonEnDusuk == .greatestFiniteMagnitude ? 0 : kalibrasyonEnDusuk }
        let gurultu = taban
        // Tabanlar ÖLÇÜMLE düşürüldü: bu makinede konuşma 0.007–0.010 RMS
        // üretiyor ve eski 0.012 tabanı konuşmayı hiç görmüyordu. Gürültüye
        // göre uyarlanan çarpan asıl karardır; taban yalnızca tam sessizlikte
        // kapının kendiliğinden açılmasını engeller.
        let baslangicEsigi = max(0.004, gurultu * 3.0)
        let bitisEsigi = max(0.002, gurultu * 1.8)

        if !etkin {
            // Konuşma yokken taban güncellenir: oda gürültüsü değişirse eşik de
            // onunla gelir; konuşma sırasında (eşik üstü) taban yükselmez.
            if rms < baslangicEsigi {
                taban = rms < taban ? rms : taban + (rms - taban) * 0.002
            }
            yuksekMs = rms >= baslangicEsigi ? yuksekMs + sureMs : 0
            if yuksekMs >= baslangicDogrulamaMs {
                etkin = true
                segment += 1
                konusmaMs = yuksekMs
                sessizMs = 0
                return "ses-basladi"
            }
        } else if rms >= bitisEsigi {
            konusmaMs += sureMs
            sessizMs = 0
        } else {
            sessizMs += sureMs
            if sessizMs >= bitisDogrulamaMs {
                etkin = false
                yuksekMs = 0
                return "ses-bitti"
            }
        }
        return nil
    }
}

let dil = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "tr-TR"
let motor = AVAudioEngine()
let kapı = SesEtkinligiKapisi()
/// Bir tanıma turu: isteği ve görevi BİRLİKTE yaşar.
///
/// Üç ayrı global (`istek`, `görev`, `acikIstek`) tutmak aynı hatayı iki kez
/// üretti: yeni tur açılırken globale atama yapmak bir öncekini serbest
/// bırakıyor ve `endAudio()` çağrılmış olsa bile tanıyıcı finali üretmeden
/// İPTAL oluyordu. Günlükte bu, kısmi sonucun hemen ardından `ham-son` yerine
/// `ham-hata` olarak görünüyordu. Tur, ikisini bir arada tutar ve ancak
/// finalini teslim edince bırakılır.
final class Tur {
    let istek: SFSpeechAudioBufferRecognitionRequest
    var gorev: SFSpeechRecognitionTask?
    /// Bu turda görülen SON boş olmayan kısmi metin.
    ///
    /// `endAudio()` sonrası final BOŞ gelebiliyor (ölçüldü: kısmi sonuçta 13
    /// karakter varken final 0 karakter). Kullanıcının söylediği kaybolmasın
    /// diye en iyi kısmi saklanır ve final boşsa o teslim edilir.
    var konusmaMs = 0
    var sonKismi = ""
    /// Tanıyıcının O ANKİ hipotezi (birleştirilmemiş ham metin).
    var hamKismi = ""
    /// Tanıyıcı uzun bir duraklamadan sonra hipotezini SIFIRLAYIP yalnız yeni
    /// parçayı veriyor (ölçüldü: 1,8 sn duraklama sonrası "Bugün gittiğimiz
    /// parka çok fazla aptal bir kullanıcı vardı" yerine yalnız "Ve ben o
    /// parkın banını" geldi). Sıfırlanmadan önceki metin burada saklanır.
    var onceki = ""
    var sonKismiGuven: Float = 0
    /// Kısmi metin her değiştiğinde artar; durma gözcüsü bununla eşleşir.
    var kismiSayaci = 0
    /// Bu turda en son ne zaman bir işaret geldi (kısmi sonuç ya da konuşma
    /// sesi). Gözcü buna bakar; sabit süreye bakmak konuşmanın ORTASINDA turu
    /// kesiyordu ve kullanıcı Talk'ı kapatıp açmak zorunda kalıyordu.
    var sonEtkinlik = Date()

    init(istek: SFSpeechAudioBufferRecognitionRequest) { self.istek = istek }

    /// Duraklama öncesi metin + tanıyıcının güncel hipotezi.
    func tamMetin(_ ham: String) -> String {
        onceki.isEmpty ? ham : onceki + " " + ham
    }

    /// Yeni ham hipotez önceki hipotezin YARISINDAN kısaysa tanıyıcı sıfırlamıştır.
    /// Normal düzeltmeler (parça→parka) birkaç karakter oynatır; sıfırlama ise
    /// ölçümde 60+ karakterden 2 karaktere düştü.
    func hipotezSifirlandiMi(_ ham: String) -> Bool {
        !hamKismi.isEmpty && ham.count * 2 < hamKismi.count
    }
}

/// Yaşayan turlar, numaralarına göre.
var turlar: [Int: Tur] = [:]
var tapKurulu = false
var bitiyor = false
var sinyalKaynakları: [DispatchSourceSignal] = []

func temizle() {
    durumla {
        for (_, tur) in turlar {
            tur.gorev?.cancel()
            tur.istek.endAudio()
        }
        turlar.removeAll()
    }
    if motor.isRunning { motor.stop() }
    if tapKurulu { motor.inputNode.removeTap(onBus: 0); tapKurulu = false }
}

func bitir(_ kod: Int32) -> Never {
    if !bitiyor { bitiyor = true; temizle() }
    fflush(stdout); fflush(stderr); exit(kod)
}

func sinyalleriKur() {
    for sinyal in [SIGTERM, SIGINT] {
        signal(sinyal, SIG_IGN)
        let kaynak = DispatchSource.makeSignalSource(signal: sinyal, queue: .main)
        kaynak.setEventHandler { bitir(0) }
        kaynak.resume()
        sinyalKaynakları.append(kaynak)
    }
}

/// Tanı günlüğü: tanıyıcıdan NE GELDİĞİNİ ölçer.
///
/// "Konuşuyorum ama yazmıyor" sınıfı bir hatada tek tek kapıları tahmin ederek
/// aramak pahalıdır. Bu günlük, Apple'ın sonuç üretip üretmediğini kanıtlar.
///
/// Konuşulan METİN YAZILMAZ — yalnız olayın türü, karakter sayısı, güven puanı
/// ve segment numarası. Kullanıcının ne söylediği diske düşmez.
func taniYaz(_ etiket: String, uzunluk: Int, guven: Float, segment: Int) {
    guard let kok = ProcessInfo.processInfo.environment["HOME"] else { return }
    let dizin = URL(fileURLWithPath: kok)
        .appendingPathComponent("Library/Logs/Fusion", isDirectory: true)
    try? FileManager.default.createDirectory(at: dizin, withIntermediateDirectories: true)
    let dosya = dizin.appendingPathComponent("listen.log")
    let satır = String(
        format: "%@\t%@\tkarakter=%d\tguven=%.3f\tsegment=%d\n",
        ISO8601DateFormatter().string(from: Date()), etiket, uzunluk, guven, segment
    )
    guard let veri = satır.data(using: .utf8) else { return }
    if let tutamac = try? FileHandle(forWritingTo: dosya) {
        tutamac.seekToEndOfFile()
        tutamac.write(veri)
        try? tutamac.close()
    } else {
        try? veri.write(to: dosya)
    }
}

/// Ses akışının GERÇEKTEN gelip gelmediğini ölçen sayaç.
///
/// `hazir` yazılması motorun başladığını söyler, ses geldiğini SÖYLEMEZ.
/// macOS, mikrofon izni olmayan bir sürece hata vermek yerine sessizce SIFIR
/// dolu tampon verir; bu durumda kapı hiç açılmaz ve kullanıcı "konuşuyorum
/// ama hiçbir şey olmuyor" görür. Sayaç bu iki durumu ayırır.
final class AkisTanisi {
    /// Gürültü tabanının üstünde, gerçekten duyulur bir örnek görüldü mü?
    /// Sıfır dolu tampon akışı bunu asla true yapmaz.
    private(set) var duyulurOrnekYok = true
    private var tampon = 0
    private var enYuksek: Float = 0
    private var sonRapor = Date()
    private let aralik: TimeInterval = 1.0

    private var monoEnYuksek: Float = 0
    private var donusumHatasi = 0

    /// Tanıyıcıya GİDEN sesin seviyesi. Girişte ses varken burada yoksa
    /// dönüştürücü bozuktur; ikisini ayırmak için ayrı ölçülür.
    func olcMono(rms: Float) { monoEnYuksek = max(monoEnYuksek, rms) }

    func donusumBasarisiz() { donusumHatasi += 1 }

    func olc(rms: Float, biçim: AVAudioFormat) {
        tampon += 1
        enYuksek = max(enYuksek, rms)
        if rms > 0.0005 { duyulurOrnekYok = false }
        guard Date().timeIntervalSince(sonRapor) >= aralik else { return }
        sonRapor = Date()
        taniYaz(
            "akis tampon=\(tampon) girisRms=\(String(format: "%.5f", enYuksek)) "
                + "monoRms=\(String(format: "%.5f", monoEnYuksek)) donusumHatasi=\(donusumHatasi) "
                + "hz=\(Int(biçim.sampleRate)) kanal=\(biçim.channelCount)",
            uzunluk: tampon, guven: enYuksek, segment: 0
        )
        tampon = 0
        enYuksek = 0
        monoEnYuksek = 0
        donusumHatasi = 0
    }
}

let akisTanisi = AkisTanisi()

func rms(_ tampon: AVAudioPCMBuffer) -> Float {
    guard let kanallar = tampon.floatChannelData, tampon.frameLength > 0 else { return 0 }
    // Kanalların EN YÜKSEĞİ alınır, ortalaması DEĞİL. Ölçüldü: bu makinede
    // giriş 3 kanallı geliyor ve kanalların ikisi neredeyse sessiz. Ortalama
    // almak konuşmanın enerjisini üçe bölüyor, seviye 0.039'dan 0.010'a düşüp
    // eşiğin altında kalıyordu.
    let kanalSayisi = Int(tampon.format.channelCount)
    let cerceve = Int(tampon.frameLength)
    var enYuksek: Float = 0
    for kanal in 0..<kanalSayisi {
        let veri = kanallar[kanal]
        var kareToplami: Float = 0
        for indis in 0..<cerceve { kareToplami += veri[indis] * veri[indis] }
        enYuksek = max(enYuksek, sqrt(kareToplami / Float(cerceve)))
    }
    return enYuksek
}

func guven(_ sonuc: SFSpeechRecognitionResult) -> Float {
    sonuc.bestTranscription.segments.map(\.confidence).max() ?? 0
}

/// Bir konuşma şu an açık mı? Gerçek akışta `konusmaAc`/`konusmaKapat` yönetir,
/// sentetik fixture'larda ise ses motoru olmadan aynı durum kurulur.
var konusmaAcik = false

private let enAzGuven: Float = 0.2

/// Güven puanı yalnızca BİLDİRİLDİĞİNDE kapı olur.
///
/// Ölçüldü ve Apple geliştirici forumlarında da bildiriliyor: ABD dışı bölge
/// ayarlarında `SFTranscriptionSegment.confidence` 0.0 dönebiliyor ve kısmi
/// sonuçlarda zaten rutin olarak 0'dır. Koşulsuz eşik bu makinede (bölge
/// `tr_TR`) TÜM metni sessizce düşürüyordu — kullanıcı konuşuyor, dalga
/// oynuyor, ekranda hiçbir şey çıkmıyordu.
///
/// Bu yüzden eşik yalnız puan GERÇEKTEN raporlandığında (sıfırdan büyük)
/// uygulanır: gerçekten düşük güvenli tanıma hâlâ reddedilir, raporlanmayan
/// puan ise reddetme gerekçesi sayılmaz.
func guvenYeterli(_ puan: Float) -> Bool {
    puan <= 0 || puan >= enAzGuven
}

@discardableResult
func metinYaz(
    final: Bool, metin: String, guven puan: Float, callbackSegment: Int, konusmaSuresi: Int? = nil
) -> Bool {
    guard !metin.isEmpty, final || guvenYeterli(puan) else { return false }
    // Kısmi sonuç yalnız EN GÜNCEL turdan kabul edilir; kapanmış bir turdan geç
    // gelen kısmi, kullanıcı susmuşken ekrana yazı düşürürdü. Final için
    // konuşma süresi eşiği yeterlidir.
    let sure = konusmaSuresi ?? kapı.konusmaMs
    guard final ? kapı.yeterliKonusma(sure) : konusmaAcik else { return false }
    yaz(final ? "son" : "kismi", metin, guven: puan,
        speechMs: sure, segment: callbackSegment)
    return true
}

func sentetikFixture(_ ad: String) -> Never {
    yaz("hazir", dil)
    for _ in 0..<30 { _ = kapı.isle(rms: 0.001, sureMs: 10) }
    if ad == "segment-kaniti" {
        for _ in 0..<50 { _ = kapı.isle(rms: 0.08, sureMs: 10) }
        let oncekiSure = kapı.konusmaMs
        for _ in 0..<(kapı.bitisDogrulamaMs / 10 + 5) { _ = kapı.isle(rms: 0.001, sureMs: 10) }
        for _ in 0..<8 { _ = kapı.isle(rms: 0.08, sureMs: 10) }
        guard metinYaz(final: true, metin: "merhaba fuzyon", guven: 0.9,
                      callbackSegment: 1, konusmaSuresi: oncekiSure) else { bitir(14) }
        bitir(0)
    }
    if ad == "kanal-sadakati" {
        guard let bicim = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 48_000, channels: 2, interleaved: false),
              let girdi = AVAudioPCMBuffer(pcmFormat: bicim, frameCapacity: 480),
              let veri = girdi.floatChannelData else { bitir(11) }
        girdi.frameLength = 480
        for indis in 0..<480 {
            veri[0][indis] = sin(Float(indis) * 0.1) * 0.5
            veri[1][indis] = cos(Float(indis) * 0.1) * 0.35
        }
        guard let cikti = monoIndirgerAl().indirge(girdi), let sonuc = cikti.floatChannelData else { bitir(12) }
        var hata: Float = 0
        for indis in 0..<480 { hata = max(hata, abs(sonuc[0][indis] - veri[0][indis])) }
        guard hata < 0.00001 else { yaz("hata", "kanal dalga biçimi bozuldu"); bitir(13) }
        yaz("son", "kanal-sadakati basarili"); bitir(0)
    }
    if ad == "indirgeme" {
        // Çok kanallı girişin tek kanala GERÇEKTEN indiğini kanıtlar.
        // Ölçülen hata: `AVAudioConverter` hata bildirmeden sessiz tampon
        // üretiyordu ve tanıyıcıya saf sessizlik gidiyordu.
        guard
            let bicim = AVAudioFormat(
                commonFormat: .pcmFormatFloat32,
                sampleRate: 48_000,
                channels: 2,
                interleaved: false
            ),
            let girdi = AVAudioPCMBuffer(pcmFormat: bicim, frameCapacity: 480),
            let veri = girdi.floatChannelData
        else { yaz("hata", "test tamponu kurulamadı"); bitir(11) }
        girdi.frameLength = 480
        // Sinyal YALNIZ 1. kanalda; 0. kanal sessiz. Gerçek makinedeki durum
        // budur ve ortalama alan bir indirgeme sinyali yarıya düşürür.
        for indis in 0..<480 {
            veri[0][indis] = 0
            veri[1][indis] = sin(Float(indis) * 0.1) * 0.5
        }
        let mono = monoIndirgerAl().indirge(girdi)
        let seviye = mono.map { rms($0) } ?? 0
        yaz("hazir", "indirgeme", guven: seviye, speechMs: Int(mono?.frameLength ?? 0), segment: 1)
        bitir(0)
    }
    if ad == "kapisiz" {
        // Kapı eşiğin altındaki sesle HİÇ açılmaz. Ses yine de tanıyıcıya
        // aktığı için kısmi sonuç üretilebilmelidir; eskiden bu durumda
        // kullanıcı konuşurken ekranda hiçbir şey çıkmıyordu.
        konusmaAcik = true
        for _ in 0..<60 { _ = kapı.isle(rms: 0.0009, sureMs: 10) }
        metinYaz(final: false, metin: "esik-altinda", guven: 0.0, callbackSegment: 1)
        bitir(0)
    }
    if ad == "iki-konusma" {
        // Yardımcı TEK konuşmalık değildir: ilk konuşma bittikten sonra ikinci
        // konuşma da tanınmalı. Eskiden `isFinal` gelince süreç kapanıyordu.
        for tur in 1...2 {
            var segment = 0
            for _ in 0..<30 {
                if let olay = kapı.isle(rms: 0.08, sureMs: 10) {
                    segment = kapı.segment
                    konusmaAcik = true
                    yaz(olay, speechMs: kapı.konusmaMs, segment: segment)
                }
            }
            metinYaz(final: false, metin: "kismi-\(tur)", guven: 0.0, callbackSegment: segment)
            for _ in 0..<(kapı.bitisDogrulamaMs / 10 + 5) {
                if let olay = kapı.isle(rms: 0.001, sureMs: 10) {
                    konusmaAcik = false
                    metinYaz(final: true, metin: "son-\(tur)", guven: 0.0, callbackSegment: segment)
                    yaz(olay, speechMs: kapı.konusmaMs, segment: segment)
                }
            }
        }
        bitir(0)
    }
    if ["voiced", "low-confidence", "low-confidence-partial", "delayed-partial"].contains(ad) {
        var fixtureSegment = 0
        for _ in 0..<30 {
            if let olay = kapı.isle(rms: 0.08, sureMs: 10) {
                fixtureSegment = kapı.segment
                yaz(olay, speechMs: kapı.konusmaMs, segment: kapı.segment)
            }
        }
        konusmaAcik = true
        if ad == "voiced" {
            metinYaz(final: false, metin: "merhaba", guven: 0.82, callbackSegment: fixtureSegment)
            metinYaz(final: true, metin: "merhaba", guven: 0.91, callbackSegment: fixtureSegment)
        } else if ad == "delayed-partial" {
            metinYaz(final: false, metin: "zamaninda", guven: 0.82, callbackSegment: fixtureSegment)
        } else {
            _ = metinYaz(final: false, metin: "supheli", guven: 0.1, callbackSegment: fixtureSegment)
            yaz("hata", "Güvenilir konuşma tanınamadı.", speechMs: kapı.konusmaMs, segment: kapı.segment)
        }
        for _ in 0..<(kapı.bitisDogrulamaMs / 10 + 5) {
            if let olay = kapı.isle(rms: 0.001, sureMs: 10) {
                // Konuşma bitti: bu andan sonra gelen KISMİ sonuç düşürülmeli.
                konusmaAcik = false
                if ad == "delayed-partial" {
                    _ = metinYaz(final: false, metin: "gecikmis", guven: 0.92,
                        callbackSegment: fixtureSegment)
                    metinYaz(final: true, metin: "zamaninda", guven: 0.91,
                        callbackSegment: fixtureSegment)
                }
                yaz(olay, speechMs: kapı.konusmaMs, segment: fixtureSegment)
            }
        }
    }
    bitir(0)
}

sinyalleriKur()

if let fixture = ProcessInfo.processInfo.environment["FUSION_LISTEN_TEST_FIXTURE"] {
    sentetikFixture(fixture)
}

if ProcessInfo.processInfo.environment["FUSION_LISTEN_SIGNAL_SMOKE"] == "1" {
    yaz("hazir", dil)
    RunLoop.main.run()
}

guard let tanıyıcı = SFSpeechRecognizer(locale: Locale(identifier: dil)) else {
    yaz("hata", "Bu dil için tanıyıcı yok: \(dil)"); bitir(2)
}

/// Çok kanallı girişi TEK kanala indirger.
///
/// `AVAudioConverter` KULLANILMAZ. Ölçüldü: 3 kanal → 1 kanal dönüşümünde
/// dönüştürücü hata bildirmeden tamamen SESSİZ tampon üretiyordu
/// (`girisRms=0.00778 monoRms=0.00000 donusumHatasi=0`), yani tanıyıcıya saf
/// sessizlik gidiyor ve ne söylenirse söylensin aynı kırıntı çıkıyordu. Kanal
/// sayısı için tanımlı bir eşleme olmadığında dönüştürücünün davranışı budur.
///
/// Örnekleme hızı da DEĞİŞTİRİLMEZ: `SFSpeechAudioBufferRecognitionRequest`
/// girişin kendi hızını kabul eder ve yeniden örnekleme yeni bir hata yüzeyidir.
final class MonoIndirger {
    private var hedef: AVAudioFormat?
    private var kaynakBicim: AVAudioFormat?

    /// Tampon boyunca tek bir kanalın dalga biçimini koru.
    /// Her örnekte farklı kanalın tepesini seçmek yapay bir sinyal üretiyordu.
    /// En güçlü kanal tamponun toplam enerjisiyle seçilir; sessiz kanallarla
    /// ortalama alınıp konuşmanın seviyesi de düşürülmez.
    func indirge(_ tampon: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
        guard let kanallar = tampon.floatChannelData, tampon.frameLength > 0 else { return nil }
        if kaynakBicim != tampon.format {
            hedef = AVAudioFormat(
                commonFormat: .pcmFormatFloat32,
                sampleRate: tampon.format.sampleRate,
                channels: 1,
                interleaved: false
            )
            kaynakBicim = tampon.format
        }
        guard
            let hedef = hedef,
            let cikti = AVAudioPCMBuffer(pcmFormat: hedef, frameCapacity: tampon.frameLength),
            let hedefVeri = cikti.floatChannelData
        else { return nil }

        let kanalSayisi = Int(tampon.format.channelCount)
        let cerceve = Int(tampon.frameLength)
        let yaz = hedefVeri[0]
        var seciliKanal = 0
        var enYuksekEnerji: Float = -1
        for kanal in 0..<kanalSayisi {
            var enerji: Float = 0
            for indis in 0..<cerceve { enerji += kanallar[kanal][indis] * kanallar[kanal][indis] }
            if enerji > enYuksekEnerji { enYuksekEnerji = enerji; seciliKanal = kanal }
        }
        for indis in 0..<cerceve { yaz[indis] = kanallar[seciliKanal][indis] }
        cikti.frameLength = tampon.frameLength
        return cikti
    }
}

/// Ortak indirgeyici.
///
/// Düz bir global DEĞİLDİR: `main.swift` içindeki üst düzey kod sırayla
/// çalışır ve sentetik fixture'lar dosyanın ÜST kısmından çağrılır. Düz global
/// o noktada henüz kurulmamış olur ve erişim süreci çökertir (ölçüldü).
/// Tip içindeki `static let` tembeldir, bu yüzden sıradan bağımsızdır.
func monoIndirgerAl() -> MonoIndirger {
    enum Depo { static let ortak = MonoIndirger() }
    return Depo.ortak
}

//: Tanıyıcıya verilecek hedef tepe seviyesi.
//:
//: Ölçüldü: bu makinede konuşma yalnızca ~0.01 RMS üretiyor (normal konuşma
//: 0.05–0.2 aralığındadır). Tanıyıcıya bu kadar kısık ses vermek, ne söylenirse
//: söylensin birkaç karakterlik kırıntı üretiyordu. Kazanç, sinyali tanıyıcının
//: beklediği aralığa taşır.
private let HEDEF_TEPE: Float = 0.25

//: Kazanç tavanı. Sınırsız kazanç, sessizlikteki gürültüyü konuşma seviyesine
//: yükseltip tanıyıcıya çöp verirdi.
private let EN_YUKSEK_KAZANC: Float = 24.0

//: Bu tepenin altındaki tampon gürültü sayılır ve YÜKSELTİLMEZ.
private let GURULTU_TABANI: Float = 0.0015

/// Konuşma tepe zarfı ve ondan türeyen KALICI kazanç.
///
/// Eskiden kazanç HER TAMPONUN kendi tepesine göre hesaplanıyordu. Ölçüldü
/// (WAV girişiyle): sessiz odada 0.0006 RMS'lik gürültü tamponu 24 kat
/// yükseltilip 0.015 RMS'e, yani konuşma seviyesine çıkıyor; tanıyıcı bu
/// "yüksek gürültüden" hayalet sözcük ("Evet") üretiyordu ve kelime aralarındaki
/// sessizlikler de konuşma gibi yükseliyordu. Artık kazancı yalnız KONUŞMA
/// tamponları belirler (kapı etkinken); sessizlik ve gürültü, son konuşmanın
/// kazancıyla aynı oranda taşınır, tek tek yükseltilmez.
final class KazancZarfi {
    private var zarf: Float = 0
    /// Tepe zarfının tampon başına sönümü: 47 tampon/sn'de 0.995^47 ≈ 0.79/sn,
    /// yani konuşma bittikten sonra bile kazanç ~birkaç sn sabit kalır.
    private let sonum: Float = 0.995

    var kazanc: Float {
        guard zarf > GURULTU_TABANI else { return 1 }
        return max(1, min(HEDEF_TEPE / zarf, EN_YUKSEK_KAZANC))
    }

    /// Konuşma tamponunun tepesini zarfa kat (hızlı yükselir, yavaş söner).
    func konusmayiGoz(tepe: Float) { zarf = max(tepe, zarf * sonum) }
}

func kazancZarfiAl() -> KazancZarfi {
    enum Depo { static let ortak = KazancZarfi() }
    return Depo.ortak
}

func tepeBul(_ tampon: AVAudioPCMBuffer) -> Float {
    guard let kanallar = tampon.floatChannelData, tampon.frameLength > 0 else { return 0 }
    var tepe: Float = 0
    for indis in 0..<Int(tampon.frameLength) { tepe = max(tepe, abs(kanallar[0][indis])) }
    return tepe
}

/// Tamponu tanıyıcıya GİDERKEN kazançla çarp. Kırpma yok: örnekler [-1, 1]'e
/// sıkıştırılır. VPIO açıkken uygulanmaz (kendi otomatik kazancı vardır).
func kazancUygula(_ tampon: AVAudioPCMBuffer) {
    guard !yankiGidermeAcik else { return }
    guard let kanallar = tampon.floatChannelData, tampon.frameLength > 0 else { return }
    let kazanc = kazancZarfiAl().kazanc
    guard kazanc > 1.0 else { return }
    let veri = kanallar[0]
    for indis in 0..<Int(tampon.frameLength) {
        veri[indis] = max(-1.0, min(1.0, veri[indis] * kazanc))
    }
}

/// Konuşma başlangıcından ÖNCEKİ tamponların tutulduğu halka.
///
/// Kapı, sesi ancak `baslangicDogrulamaMs` kadar sürdükten sonra "başladı"
/// sayar. O ana kadarki tamponlar atılırsa ilk hece tanıyıcıya hiç ulaşmaz ve
/// "merhaba" → "aba" olur. Bu halka o pencereyi saklar ve konuşma açılınca
/// tanıyıcıya ÖNCE onu verir.
final class OnTampon {
    private var tamponlar: [AVAudioPCMBuffer] = []
    private let kapasite: Int

    init(kapasite: Int) { self.kapasite = kapasite }

    func ekle(_ tampon: AVAudioPCMBuffer) {
        tamponlar.append(tampon)
        if tamponlar.count > kapasite { tamponlar.removeFirst(tamponlar.count - kapasite) }
    }

    func bosalt() -> [AVAudioPCMBuffer] {
        let hepsi = tamponlar
        tamponlar.removeAll(keepingCapacity: true)
        return hepsi
    }
}

//: 1024 örneklik tamponlarda ~48 kHz'de her tampon ~21 ms; 16 tampon ≈ 340 ms.
//: Kapının 80 ms'lik doğrulama penceresini rahatça kapsar.
let onTampon = OnTampon(kapasite: 24)

/// Paylaşılan tur durumunu koruyan kilit.
///
/// Bu durum ÜÇ ayrı bağlamdan görülür: ses tapı (gerçek zamanlı ses iş
/// parçacığı), tanıma geri çağrısı (Apple'ın kuyruğu) ve süre gözcüsü
/// (`DispatchQueue.main`). Kilitsiz erişimde `append` ile `endAudio` aynı
/// istek üzerinde yarışabiliyor, `turlar` sözlüğü iki iş parçacığından
/// değiştirilebiliyordu — ikincisi tanımsız davranıştır.
///
/// Yinelemeli seçildi: `konusmaAc` içinden `konusmaKapat` çağrılır.
let durumKilidi = NSRecursiveLock()

/// Tur durumuna kilit altında eriş.
func durumla<T>(_ islem: () -> T) -> T {
    durumKilidi.lock()
    defer { durumKilidi.unlock() }
    return islem()
}

/// O anda dinlenen konuşmanın isteği.
var acikIstek: SFSpeechAudioBufferRecognitionRequest?

//: Bir turun açık kalabileceği en uzun süre.
//:
//: Ölçülen hata: kapı bir kez `ses-bitti` verip yeni tur açtıktan sonra
//: kullanıcı başlangıç eşiğini bir daha aşmazsa tur HİÇ kapanmıyordu. İstek
//: açık kaldığı için `isFinal` üretilmiyor ve arayüz "seni yazıya
//: çeviriyorum…" adımında sonsuza kadar bekliyordu.
private let enUzunTurSaniye = 12.0

//: `endAudio()` sonrası tanıma geri çağrısı için tanınan ek süre. Bu da
//: gelmezse tur asılı kalmış demektir ve dinleme zorla sürdürülür.
private let geriCagriBeklemeSaniye = 5.0

//: Kısmi metin bu kadar süre DEĞİŞMEZSE kullanıcı sözünü bitirmiştir.
//:
//: Ölçülen hata: ses kapısı (RMS) bazı mikrofonlarda `ses-bitti` üretmiyor;
//: `endAudio()` hiç çağrılmadığı için Apple `isFinal` vermiyor, arayüz kısmi
//: metni görüp bile hiçbir şey göndermiyordu. Bitiş kararı artık tanıyıcının
//: kendi çıktısına da bağlıdır; kapı yalnız ek bir kaynaktır.
private let kismiDurmaSaniye = 2.2

/// Kısmi metin durduysa turu kapat; final böylece teslim edilir.
func kismiDurmaGozcusuKur(turNo: Int, sayac: Int) {
    DispatchQueue.main.asyncAfter(deadline: .now() + kismiDurmaSaniye) {
        durumla {
            guard !bitiyor, acikTurNo == turNo, acikIstek != nil else { return }
            guard let tur = turlar[turNo], tur.kismiSayaci == sayac else { return }
            taniYaz("kismi-durdu", uzunluk: tur.sonKismi.count, guven: 0, segment: turNo)
            konusmaKapat()
        }
    }
}

/// Tanıyıcıya ses beslemesi KAPISI: yalnız kullanıcının sesi geçer, uzaktaki
/// konuşma ve ortam gürültüsü geçmez.
///
/// Kapı kapalıyken tamponlar önhafızada bekler (ilk hece kaybolmasın); kapı
/// açılınca önce onlar, sonra canlı ses verilir. Konuşma bitince 1,5 sn "kuyruk"
/// açık kalır (cümle sonu kesilmesin). Kapı oturumun ilk 8 saniyesinde HİÇ
/// açılmazsa (mikrofon çok kısık, eşik hatalı) güvenli tarafa düşülür ve ses
/// koşulsuz beslenir — yardımcı asla sağır kalmamalı.
let oturumBasi = Date()
var beslemeKuyrugaKadar = Date.distantPast
private let beslemeKuyrukSaniye = 1.5
private let kapiHicAcilmadiSaniye = 8.0

func beslemeAcikMi() -> Bool {
    let simdi = Date()
    if kapı.etkin {
        beslemeKuyrugaKadar = simdi.addingTimeInterval(beslemeKuyrukSaniye)
        return true
    }
    if simdi < beslemeKuyrugaKadar { return true }
    return kapı.segment == 0 && simdi.timeIntervalSince(oturumBasi) > kapiHicAcilmadiSaniye
}

/// Açık turun kimliği; gözcü yalnız KENDİ turunu kapatır.
var acikTurNo = 0

/// Konuşma başlat: bu konuşmaya ÖZEL taze bir istek ve görev kur.
///
/// Neden konuşma başına: tek bir istek/görevle çalışmak yardımcıyı TEK
/// konuşmalık yapıyordu — ilk sessizlikte `endAudio()` çağrılıp `isFinal`
/// gelince süreç kapanıyordu. Ortamdan gelen sahte bir tetik tek konuşma
/// hakkını harcayınca kullanıcı konuşmaya başlamadan dinleme bitiyordu.
/// Turu ETKİNLİKSİZ kaldığında kapatan gözcü.
///
/// Eskiden sabit 12 saniyede kapatıyordu ve kullanıcı hâlâ konuşurken turu
/// kesebiliyordu; yarım kalan tur arayüzü bozuk bırakıyor, kullanıcı Talk'ı
/// kapatıp açmak zorunda kalıyordu. Artık son işaretin (kısmi sonuç ya da
/// konuşma sesi) üstünden geçen süreye bakılır.
func turGozcusuKur(turNo: Int) {
    DispatchQueue.main.asyncAfter(deadline: .now() + enUzunTurSaniye) {
        durumla {
            guard !bitiyor, acikTurNo == turNo, acikIstek != nil else { return }
            guard let tur = turlar[turNo] else { return }
            let bosGecen = Date().timeIntervalSince(tur.sonEtkinlik)
            if bosGecen < enUzunTurSaniye {
                // Tur hâlâ canlı: kesme, yeniden ölç.
                turGozcusuKur(turNo: turNo)
                return
            }
            taniYaz("tur-suresi-doldu", uzunluk: 0, guven: 0, segment: turNo)
            konusmaKapat()
        }
    }
}

func konusmaAc(segment: Int) {
  durumla {
    // Açık tur burada TERK EDİLMEZ; `konusmaKapat` ona `endAudio()` der ve
    // finalini teslim etmesi beklenir.
    konusmaKapat()
    acikTurNo += 1
    let turNo = acikTurNo
    turGozcusuKur(turNo: turNo)
    // İKİNCİ gözcü: `endAudio()` sonrası tanıma geri çağrısı hiç gelmezse tur
    // sonsuza kadar sözlükte kalır ve yeni tur açılmaz — süreç sessizce sağır
    // olur. Bu gözcü o durumu görür, görevi iptal eder ve dinlemeyi sürdürür.
    DispatchQueue.main.asyncAfter(deadline: .now() + enUzunTurSaniye + geriCagriBeklemeSaniye) {
        durumla {
            guard !bitiyor, let asili = turlar[turNo] else { return }
            taniYaz("tur-geri-cagri-gelmedi", uzunluk: 0, guven: 0, segment: turNo)
            asili.gorev?.cancel()
            turTamamlandi(turNo)
        }
    }
    let r = SFSpeechAudioBufferRecognitionRequest()
    r.shouldReportPartialResults = true
    r.requiresOnDeviceRecognition = true
    let tur = Tur(istek: r)
    turlar[turNo] = tur
    acikIstek = r
    konusmaAcik = true
    taniYaz("konusma-acildi", uzunluk: 0, guven: 0, segment: segment)
    for tampon in onTampon.bosalt() { r.append(tampon) }

    tur.gorev = tanıyıcı.recognitionTask(with: r) { sonuç, hata in
      durumla {
        // Sonuç ve hata AYNI çağrıda gelebiliyor. İki bağımsız `if let`
        // kullanmak turu iki kez tamamlıyor ve başarılı finalin hemen ardından
        // sahte bir hata yazıyordu; bu yüzden dallar birbirini dışlar.
        if let sonuç = sonuç, sonuç.isFinal || hata == nil {
            let metin = sonuç.bestTranscription.formattedString
            let puan = guven(sonuç)
            taniYaz(
                sonuç.isFinal ? "ham-son" : "ham-kismi",
                uzunluk: metin.count, guven: puan, segment: segment
            )
            if sonuç.isFinal {
                // Final BOŞ gelebiliyor: ölçüldü, kısmi sonuçta 13 karakter
                // varken final 0 karakter döndü. Kullanıcının söylediği
                // kaybolmasın diye o turun en son kısmi metni teslim edilir.
                let tur = turlar[turNo]
                let teslim = metin.isEmpty ? (tur?.sonKismi ?? "") : (tur?.tamMetin(metin) ?? metin)
                let teslimGuven = metin.isEmpty ? (tur?.sonKismiGuven ?? 0) : puan
                if !metinYaz(
                    final: true, metin: teslim, guven: teslimGuven, callbackSegment: segment,
                    konusmaSuresi: tur?.konusmaMs
                ) {
                    let sure = tur?.konusmaMs ?? 0
                    if teslim.isEmpty && !kapı.yeterliKonusma(sure) {
                        yaz("ses-bitti", speechMs: sure, segment: segment)
                    } else {
                        yaz("hata", "Ses duydum ancak sözcükleri net çözemedim. Tekrar söyleyebilirsin.",
                            speechMs: sure, segment: segment)
                    }
                }
                turTamamlandi(turNo)
            } else {
                var tamMetin = metin
                if !metin.isEmpty, let tur = turlar[turNo] {
                    if tur.hipotezSifirlandiMi(metin) { tur.onceki = tur.sonKismi }
                    tur.hamKismi = metin
                    tamMetin = tur.tamMetin(metin)
                }
                if !metin.isEmpty {
                    turlar[turNo]?.sonKismi = tamMetin
                    turlar[turNo]?.sonKismiGuven = puan
                    turlar[turNo]?.sonEtkinlik = Date()
                    // Tanıyıcı metin üretti: konuşma vardır. Kapı açılmamış olsa
                    // bile final bu yüzden "çok kısa" diye reddedilmez.
                    if let tur = turlar[turNo] {
                        tur.konusmaMs = max(tur.konusmaMs, 250)
                        tur.kismiSayaci += 1
                        kismiDurmaGozcusuKur(turNo: turNo, sayac: tur.kismiSayaci)
                    }
                }
                metinYaz(final: false, metin: tamMetin, guven: puan, callbackSegment: segment,
                    konusmaSuresi: turlar[turNo]?.konusmaMs)
            }
        } else if let hata = hata {
            // Hata KODU ve alanı yazılır: "iptal edildi" ile "konuşma
            // bulunamadı" ve gerçek arıza aynı görünmemeli. Sistem hata
            // kodudur, kullanıcının konuştuğu metin DEĞİLDİR.
            let ns = hata as NSError
            taniYaz(
                "ham-hata alan=\(ns.domain) kod=\(ns.code)",
                uzunluk: 0, guven: 0, segment: segment
            )
            // İptal (`kLSRErrorDomain 301`) bizim `endAudio()` çağrımızın
            // normal sonucudur; kullanıcıya "bir sorun oluştu" demek yanlıştır.
            // Elde kalan kısmi metin varsa o teslim edilir.
            let iptal = ns.domain == "kLSRErrorDomain" && ns.code == 301
            let kalan = turlar[turNo]?.sonKismi ?? ""
            if iptal, !kalan.isEmpty {
                metinYaz(
                    final: true,
                    metin: kalan,
                    guven: turlar[turNo]?.sonKismiGuven ?? 0,
                    callbackSegment: segment, konusmaSuresi: turlar[turNo]?.konusmaMs
                )
            } else if !iptal {
                let sure = turlar[turNo]?.konusmaMs ?? 0
                if ns.domain == "kAFAssistantErrorDomain" && ns.code == 1110 {
                    if !kalan.isEmpty {
                        metinYaz(final: true, metin: kalan, guven: turlar[turNo]?.sonKismiGuven ?? 0,
                                 callbackSegment: segment, konusmaSuresi: sure)
                    } else if !kapı.yeterliKonusma(sure) {
                        yaz("ses-bitti", speechMs: sure, segment: segment)
                    } else {
                        yaz("hata", "Ses duydum ancak sözcükleri net çözemedim. Tekrar söyleyebilirsin.",
                            speechMs: sure, segment: segment)
                    }
                } else {
                    yaz("hata", hata.localizedDescription, speechMs: sure, segment: segment)
                }
            }
            turTamamlandi(turNo)
        }
      }
    }
  }
}

/// Tur bitti: kaydını bırak ve GEREKİYORSA sıradakini aç.
///
/// Sıradaki tur burada açılır, `ses-bitti` anında DEĞİL:
/// `SFSpeechRecognizer` aynı anda tek görev destekler ve yeni görev başlatmak
/// bir öncekini iptal eder (ölçüldü: `kLSRErrorDomain 301`, final boş dönüyordu).
func turTamamlandi(_ turNo: Int) {
  durumla {
    turlar.removeValue(forKey: turNo)
    // Koşul TUR KİMLİĞİDİR, `acikIstek == nil` DEĞİL.
    //
    // Tanıyıcı kendi iç sezgileriyle bizim kapımızdan ÖNCE final üretebiliyor.
    // O durumda `acikIstek` hâlâ dolu olur; `acikIstek == nil` koşulu tutmaz ve
    // yeni tur HİÇ açılmazdı. Ses ölmüş bir isteğe akmaya devam eder, kapı
    // sonradan kapansa bile kimse yeni tur açmaz ve süreç sessizce KALICI
    // olarak sağır kalırdı — düzeltmeye çalıştığımız hatanın ta kendisi.
    guard !bitiyor, acikTurNo == turNo else { return }
    konusmaKapat()
    konusmaAc(segment: kapı.segment + 1)
  }
}

/// Açık konuşmayı kapat; tanıyıcı kalan sesi işleyip `isFinal` üretir.
func konusmaKapat() {
  durumla {
    if acikIstek != nil { taniYaz("ses-sonu-bildirildi", uzunluk: 0, guven: 0, segment: acikTurNo) }
    acikIstek?.endAudio()
    acikIstek = nil
    konusmaAcik = false
  }
}

/// Ses tapını güncel giriş biçimiyle kur. Kurulum TEK yerde durur ki
/// yeniden kurulum ile ilk kurulum ayrışmasın.
//: Ses işlemenin (yankı giderme) açık olup olmadığı. Kazanç kararı buna bakar.
var yankiGidermeAcik = false

/// macOS'un ses işleme motorunu (VPIO) aç: akustik yankı giderme, gürültü
/// bastırma ve otomatik kazanç.
///
/// Sürekli dinlemede zorunludur: Fusion hoparlörden konuşurken mikrofon kendi
/// sesini duyar ve tanıyıcı onu kullanıcının sözü sanar. VPIO, FaceTime'ın da
/// kullandığı yoldur ve tap'e ULAŞAN sesi filtreler.
///
/// Başarısız olabilir (giriş ve çıkış farklı cihazlarsa macOS'ta bilinen bir
/// kısıt). O durumda dinleme SÜRDÜRÜLÜR — yankı gidermesiz çalışmak, hiç
/// çalışmamaktan iyidir; metin seviyesindeki ayıklama ikinci savunmadır.
func yankiGidermeyiAc(_ girdi: AVAudioInputNode) {
    do {
        try girdi.setVoiceProcessingEnabled(true)
        // TTS ayrı say/afplay sürecinden gelir; varsayılan diğer-ses kısılması
        // Fusion'ın kendi yanıtını da bastırabilir. Yankı giderme açık kalır.
        if #available(macOS 14.0, *) {
            girdi.voiceProcessingOtherAudioDuckingConfiguration =
                AVAudioVoiceProcessingOtherAudioDuckingConfiguration(
                    enableAdvancedDucking: false, duckingLevel: .min
                )
        }
        yankiGidermeAcik = true
        taniYaz("yanki-giderme acik", uzunluk: 0, guven: 0, segment: 0)
    } catch {
        yankiGidermeAcik = false
        taniYaz(
            "yanki-giderme kapali neden=\(error.localizedDescription)",
            uzunluk: 0, guven: 0, segment: 0
        )
    }
}

/// Tek bir giriş tamponunun BORU HATTI: kapı, mono indirgeme, kazanç, önhafıza,
/// besleme kapısı ve tanıyıcı. Mikrofon tapı da test amaçlı WAV girişi de
/// AYNI fonksiyonu çağırır; böylece ölçüm gerçek hattı sınar.
func tamponIsle(_ tampon: AVAudioPCMBuffer) {
    let biçim = tampon.format
    let sureMs = max(1, Int(Double(tampon.frameLength) / biçim.sampleRate * 1000))
    let seviye = rms(tampon)
    akisTanisi.olc(rms: seviye, biçim: biçim)
    let olay = kapı.isle(rms: seviye, sureMs: sureMs)
    // Ses tanıyıcıya KOŞULSUZ akar. Eskiden kapı açılmadan tampon
    // tutuluyordu; kapının eşiği bu mikrofonun seviyesinin üstünde kalınca
    // tanıyıcıya tek bir örnek bile gitmiyor ve hiçbir şey olmuyordu.
    // Apple'ın tanıyıcısı kendi bitiş tespitini zaten yapar; VAD'ın işi
    // sesi ENGELLEMEK değil, turun ne zaman biteceğini söylemektir.
    if let mono = monoIndirgerAl().indirge(tampon) {
        // Zarf yalnız konuşma sırasında beslenir; kazanç tanıyıcıya GİDERKEN
        // uygulanır, önhafızadaki tamponlar HAM saklanır.
        if kapı.etkin { kazancZarfiAl().konusmayiGoz(tepe: tepeBul(mono)) }
        akisTanisi.olcMono(rms: rms(mono))
        // `append` ile `endAudio` aynı istek üzerinde yarışabiliyordu;
        // ikisi de aynı kilidi alır.
        durumla {
            if beslemeAcikMi() {
                for onceki in onTampon.bosalt() { kazancUygula(onceki); acikIstek?.append(onceki) }
                kazancUygula(mono)
                acikIstek?.append(mono)
            } else {
                onTampon.ekle(mono)
            }
            // Konuşma sesi de etkinliktir; gözcü konuşmanın ortasında
            // turu kesmemeli.
            if kapı.etkin {
                turlar[acikTurNo]?.sonEtkinlik = Date()
                turlar[acikTurNo]?.konusmaMs += sureMs
            }
        }
    } else {
        akisTanisi.donusumBasarisiz()
    }
    guard let olay = olay else { return }
    if olay == "ses-bitti" {
        // YALNIZCA kapatılır. Sıradaki tur, bir öncekinin finali gelince
        // açılır: `SFSpeechRecognizer` aynı anda TEK görev destekler ve
        // yeni görev başlatmak bir öncekini iptal eder (ölçüldü:
        // `kLSRErrorDomain kod=301`, final boş dönüyordu).
        konusmaKapat()
        yaz(olay, speechMs: kapı.konusmaMs, segment: kapı.segment)
    } else {
        yaz(olay, speechMs: kapı.konusmaMs, segment: kapı.segment)
    }
}

func tapKur() {
    let girdi = motor.inputNode
    // Ses işleme tap kurulmadan ÖNCE açılır: biçimi değiştirir (genelde tek
    // kanala indirir), sonradan açmak tap'i bayat biçimle bırakırdı.
    yankiGidermeyiAc(girdi)
    let biçim = girdi.inputFormat(forBus: 0)
    // Geçersiz biçimle tap kurmak sessizce hiç veri getirmez. `outputFormat`
    // motor başlamadan 0 Hz dönebiliyor; giriş biçimi doğru olandır.
    guard biçim.sampleRate > 0, biçim.channelCount > 0 else {
        taniYaz("biçim-gecersiz", uzunluk: 0, guven: 0, segment: 0)
        yaz("hata", "Mikrofon giriş biçimi okunamadı. Ses giriş cihazını kontrol edin.")
        bitir(10)
    }
    taniYaz(
        "biçim hz=\(Int(biçim.sampleRate)) kanal=\(biçim.channelCount)",
        uzunluk: 0, guven: 0, segment: 0
    )
    girdi.installTap(onBus: 0, bufferSize: 1024, format: biçim) { tampon, _ in
        tamponIsle(tampon)
    }
    tapKurulu = true
}

/// Ses tapını güncel giriş biçimiyle yeniden kur.
func tapYenidenKur() {
    if tapKurulu { motor.inputNode.removeTap(onBus: 0); tapKurulu = false }
    if motor.isRunning { motor.stop() }
    tapKur()
    motor.prepare()
    do { try motor.start() } catch {
        yaz("hata", "Ses motoru yeniden başlatılamadı: \(error.localizedDescription)")
    }
}

/// TEST GİRİŞİ: `FUSION_LISTEN_WAV=<yol>` ile mikrofon yerine kayıtlı ses
/// dosyası, GERÇEK ZAMANLI hızla aynı boru hattına (`tamponIsle`) beslenir.
/// Üretimde env verilmediği için hiçbir şey değişmez. Dosya bitince
/// `FUSION_LISTEN_WAV_SONRA_SN` (varsayılan 6) saniye sessizlik eklenir ve
/// stderr'e `wav-bitti` yazılır; ölçüm betiği finalleri bekleyip süreci kapatır.
func wavBesle(yol: String) {
    guard let dosya = try? AVAudioFile(forReading: URL(fileURLWithPath: yol)) else {
        yaz("hata", "WAV açılamadı"); bitir(5)
    }
    let biçim = dosya.processingFormat
    let sonraSn = Double(ProcessInfo.processInfo.environment["FUSION_LISTEN_WAV_SONRA_SN"] ?? "") ?? 6.0
    let cerceve: AVAudioFrameCount = 1024
    let aralik = Double(cerceve) / biçim.sampleRate
    Thread.detachNewThread {
        let baslangic = Date()
        var gonderilen = 0.0
        func bekle() {
            let hedef = baslangic.addingTimeInterval(gonderilen)
            let fark = hedef.timeIntervalSinceNow
            if fark > 0 { Thread.sleep(forTimeInterval: fark) }
        }
        while let tampon = AVAudioPCMBuffer(pcmFormat: biçim, frameCapacity: cerceve),
              (try? dosya.read(into: tampon)) != nil, tampon.frameLength > 0 {
            bekle()
            tamponIsle(tampon)
            gonderilen += Double(tampon.frameLength) / biçim.sampleRate
        }
        var kalan = sonraSn
        while kalan > 0 {
            guard let sessiz = AVAudioPCMBuffer(pcmFormat: biçim, frameCapacity: cerceve) else { break }
            sessiz.frameLength = cerceve
            if let veri = sessiz.floatChannelData {
                for k in 0..<Int(biçim.channelCount) { for i in 0..<Int(cerceve) { veri[k][i] = 0 } }
            }
            bekle()
            tamponIsle(sessiz)
            gonderilen += aralik
            kalan -= aralik
        }
        FileHandle.standardError.write("wav-bitti\n".data(using: .utf8) ?? Data())
    }
}

func başlat() {
    guard tanıyıcı.isAvailable else { yaz("hata", "Tanıyıcı şu an kullanılamıyor."); bitir(3) }
    guard tanıyıcı.supportsOnDeviceRecognition else {
        yaz("hata", "Bu cihaz Türkçe çevrimdışı konuşma tanımayı desteklemiyor."); bitir(9)
    }

    if let wavYolu = ProcessInfo.processInfo.environment["FUSION_LISTEN_WAV"], !wavYolu.isEmpty {
        taniYaz("wav-girisi", uzunluk: 0, guven: 0, segment: 0)
        yaz("hazir", dil)
        konusmaAc(segment: kapı.segment + 1)
        wavBesle(yol: wavYolu)
        return
    }
    tapKur()
    motor.prepare()
    do { try motor.start() } catch {
        yaz("hata", "Ses motoru başlatılamadı: \(error.localizedDescription)"); bitir(4)
    }
    // Giriş cihazı çalışırken değişirse (Bluetooth/USB takma-çıkarma, hız
    // değişimi) tap eski biçimle kalır ve sessizce sıfır dolu ya da yanlış
    // hızda tampon üretir. Bu, hatasız görünen bir sağırlıktır; bu yüzden
    // yapılandırma değişikliğinde tap yeniden kurulur.
    NotificationCenter.default.addObserver(
        forName: .AVAudioEngineConfigurationChange, object: motor, queue: .main
    ) { _ in
        guard !bitiyor else { return }
        taniYaz("bicim-degisti", uzunluk: 0, guven: 0, segment: acikTurNo)
        tapYenidenKur()
    }
    taniYaz("hazir", uzunluk: 0, guven: 0, segment: 0)
    yaz("hazir", dil)
    // İstek HEMEN açılır: ses tanıyıcıya kapıdan bağımsız akmalı.
    konusmaAc(segment: kapı.segment + 1)
    sessizAkisGozcusuKur()
}

//: Motor başladıktan sonra ses akışının kanıtlanması için tanınan süre.
//: Kullanıcının düşünüp konuşmaya başlaması için yeterince uzun, "bozuk"
//: demek için yeterince kısa.
private let sessizAkisEsigiSaniye = 6.0

/// Motor çalışıyor ama tek bir DUYULUR örnek gelmediyse bunu bildir.
///
/// macOS, mikrofon izni olmayan sürece hata vermek yerine sessizce sıfır dolu
/// tampon verir. Eskiden bu durumda hiçbir şey olmuyordu: kullanıcı konuşuyor,
/// ekranda hiçbir şey çıkmıyor, hiçbir hata da görünmüyordu. Sessiz başarısızlık
/// yerine açık bir mesaj verilir.
func sessizAkisGozcusuKur() {
    DispatchQueue.main.asyncAfter(deadline: .now() + sessizAkisEsigiSaniye) {
        guard !bitiyor else { return }
        guard akisTanisi.duyulurOrnekYok else { return }
        taniYaz("akis-sessiz", uzunluk: 0, guven: 0, segment: 0)
        yaz(
            "hata",
            "Mikrofondan ses gelmiyor. Sistem Ayarları > Gizlilik ve Güvenlik > "
                + "Mikrofon altında Fusion'a izin verildiğini ve doğru giriş cihazının "
                + "seçili olduğunu kontrol edin."
        )
    }
}

SFSpeechRecognizer.requestAuthorization { durum in
    DispatchQueue.main.async {
        switch durum {
        case .authorized: başlat()
        case .denied: yaz("hata", "Konuşma tanıma izni reddedildi."); bitir(6)
        case .restricted: yaz("hata", "Konuşma tanıma bu cihazda kısıtlı."); bitir(7)
        default: yaz("hata", "Konuşma tanıma izni verilmedi."); bitir(8)
        }
    }
}
RunLoop.main.run()
