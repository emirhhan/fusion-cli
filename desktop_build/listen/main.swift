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
    private let baslangicDogrulamaMs = 80
    private let bitisDogrulamaMs = 350
    private var gecenMs = 0
    private var kalibrasyonToplami: Float = 0
    private var kalibrasyonOrnegi = 0
    private var yuksekMs = 0
    private var sessizMs = 0
    private(set) var konusmaMs = 0
    private(set) var etkin = false
    private(set) var segment = 0

    var finalIcinYeterli: Bool { konusmaMs >= enAzKonusmaMs }

    func isle(rms: Float, sureMs: Int) -> String? {
        if gecenMs < kalibrasyonMs {
            kalibrasyonToplami += rms
            kalibrasyonOrnegi += 1
            gecenMs += sureMs
            return nil
        }
        let gurultu = kalibrasyonOrnegi == 0 ? 0 : kalibrasyonToplami / Float(kalibrasyonOrnegi)
        let baslangicEsigi = max(0.012, gurultu * 3.0)
        let bitisEsigi = max(0.006, gurultu * 1.8)

        if !etkin {
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
var istek: SFSpeechAudioBufferRecognitionRequest?
var görev: SFSpeechRecognitionTask?
var tapKurulu = false
var bitiyor = false
var sinyalKaynakları: [DispatchSourceSignal] = []

func temizle() {
    görev?.cancel(); görev = nil
    istek?.endAudio(); istek = nil
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

func rms(_ tampon: AVAudioPCMBuffer) -> Float {
    guard let kanallar = tampon.floatChannelData, tampon.frameLength > 0 else { return 0 }
    let kanal = kanallar[0]
    var kareToplami: Float = 0
    for indis in 0..<Int(tampon.frameLength) { kareToplami += kanal[indis] * kanal[indis] }
    return sqrt(kareToplami / Float(tampon.frameLength))
}

func guven(_ sonuc: SFSpeechRecognitionResult) -> Float {
    sonuc.bestTranscription.segments.map(\.confidence).max() ?? 0
}

private let enAzGuven: Float = 0.2

@discardableResult
func metinYaz(
    final: Bool, metin: String, guven puan: Float, callbackSegment: Int
) -> Bool {
    guard !metin.isEmpty, callbackSegment == kapı.segment, puan >= enAzGuven else { return false }
    guard final ? kapı.finalIcinYeterli : kapı.etkin else { return false }
    yaz(final ? "son" : "kismi", metin, guven: puan,
        speechMs: kapı.konusmaMs, segment: callbackSegment)
    return true
}

func sentetikFixture(_ ad: String) -> Never {
    yaz("hazir", dil)
    for _ in 0..<30 { _ = kapı.isle(rms: 0.001, sureMs: 10) }
    if ["voiced", "low-confidence", "low-confidence-partial", "delayed-partial"].contains(ad) {
        var fixtureSegment = 0
        for _ in 0..<30 {
            if let olay = kapı.isle(rms: 0.08, sureMs: 10) {
                fixtureSegment = kapı.segment
                yaz(olay, speechMs: kapı.konusmaMs, segment: kapı.segment)
            }
        }
        if ad == "voiced" {
            metinYaz(final: false, metin: "merhaba", guven: 0.82, callbackSegment: fixtureSegment)
            metinYaz(final: true, metin: "merhaba", guven: 0.91, callbackSegment: fixtureSegment)
        } else if ad == "delayed-partial" {
            metinYaz(final: false, metin: "zamaninda", guven: 0.82, callbackSegment: fixtureSegment)
        } else {
            _ = metinYaz(final: false, metin: "supheli", guven: 0.1, callbackSegment: fixtureSegment)
            yaz("hata", "Güvenilir konuşma tanınamadı.", speechMs: kapı.konusmaMs, segment: kapı.segment)
        }
        for _ in 0..<35 {
            if let olay = kapı.isle(rms: 0.001, sureMs: 10) {
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

func başlat() {
    guard tanıyıcı.isAvailable else { yaz("hata", "Tanıyıcı şu an kullanılamıyor."); bitir(3) }
    guard tanıyıcı.supportsOnDeviceRecognition else {
        yaz("hata", "Bu cihaz Türkçe çevrimdışı konuşma tanımayı desteklemiyor."); bitir(9)
    }
    let r = SFSpeechAudioBufferRecognitionRequest()
    let tanimaSegmenti = kapı.segment + 1
    r.shouldReportPartialResults = true
    r.requiresOnDeviceRecognition = true
    istek = r

    let girdi = motor.inputNode
    let biçim = girdi.outputFormat(forBus: 0)
    girdi.installTap(onBus: 0, bufferSize: 1024, format: biçim) { tampon, _ in
        let sureMs = max(1, Int(Double(tampon.frameLength) / biçim.sampleRate * 1000))
        let olay = kapı.isle(rms: rms(tampon), sureMs: sureMs)
        if kapı.etkin { r.append(tampon) }
        if let olay = olay {
            if olay == "ses-bitti" { r.endAudio() }
            else {
                yaz(olay, speechMs: kapı.konusmaMs, segment: tanimaSegmenti)
            }
        }
    }
    tapKurulu = true
    motor.prepare()
    do { try motor.start() } catch {
        yaz("hata", "Ses motoru başlatılamadı: \(error.localizedDescription)"); bitir(4)
    }
    yaz("hazir", dil)

    görev = tanıyıcı.recognitionTask(with: r) { sonuç, hata in
        if let sonuç = sonuç, tanimaSegmenti > 0 {
            let metin = sonuç.bestTranscription.formattedString
            let puan = guven(sonuç)
            if sonuç.isFinal {
                if !metinYaz(final: true, metin: metin, guven: puan,
                    callbackSegment: tanimaSegmenti) {
                    yaz("hata", "Güvenilir konuşma tanınamadı.", speechMs: kapı.konusmaMs,
                        segment: tanimaSegmenti)
                }
                yaz("ses-bitti", speechMs: kapı.konusmaMs, segment: tanimaSegmenti)
                bitir(0)
            } else {
                metinYaz(final: false, metin: metin, guven: puan,
                    callbackSegment: tanimaSegmenti)
            }
        }
        if let hata = hata { yaz("hata", hata.localizedDescription); bitir(5) }
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
