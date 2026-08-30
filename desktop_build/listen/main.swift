import Foundation
import Speech
import AVFoundation
import Darwin

// Fusion konuşma tanıma yardımcısı.
// Çıktı: satır başına bir JSON. {"tur":"kismi|son|hata|hazir","metin":"..."}
// Cihaz üstü tanıma zorunlu kılınır: ses buluta GİTMEZ.

func yaz(_ tur: String, _ metin: String) {
    let nesne: [String: Any] = ["tur": tur, "metin": metin]
    if let d = try? JSONSerialization.data(withJSONObject: nesne),
       let s = String(data: d, encoding: .utf8) {
        print(s); fflush(stdout)
    }
}

let dil = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "tr-TR"
let motor = AVAudioEngine()
var istek: SFSpeechAudioBufferRecognitionRequest?
var görev: SFSpeechRecognitionTask?
var tapKurulu = false
var bitiyor = false
var sinyalKaynakları: [DispatchSourceSignal] = []

func temizle() {
    görev?.cancel()
    görev = nil
    istek?.endAudio()
    istek = nil
    if motor.isRunning { motor.stop() }
    if tapKurulu {
        motor.inputNode.removeTap(onBus: 0)
        tapKurulu = false
    }
}

func bitir(_ kod: Int32) -> Never {
    if !bitiyor {
        bitiyor = true
        temizle()
    }
    fflush(stdout)
    fflush(stderr)
    exit(kod)
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

sinyalleriKur()

// Mikrofon izni gerektirmeden signal cleanup yolunu derleme/smoke testinde ölçer.
if ProcessInfo.processInfo.environment["FUSION_LISTEN_SIGNAL_SMOKE"] == "1" {
    yaz("hazir", dil)
    RunLoop.main.run()
}

guard let tanıyıcı = SFSpeechRecognizer(locale: Locale(identifier: dil)) else {
    yaz("hata", "Bu dil için tanıyıcı yok: \(dil)"); bitir(2)
}

func başlat() {
    guard tanıyıcı.isAvailable else { yaz("hata", "Tanıyıcı şu an kullanılamıyor."); bitir(3) }
    let r = SFSpeechAudioBufferRecognitionRequest()
    r.shouldReportPartialResults = true
    // Ses buluta gitmesin: cihaz üstü zorunlu.
    if tanıyıcı.supportsOnDeviceRecognition { r.requiresOnDeviceRecognition = true }
    istek = r

    let girdi = motor.inputNode
    let biçim = girdi.outputFormat(forBus: 0)
    girdi.installTap(onBus: 0, bufferSize: 1024, format: biçim) { tampon, _ in
        r.append(tampon)
    }
    tapKurulu = true
    motor.prepare()
    do { try motor.start() } catch {
        yaz("hata", "Ses motoru başlatılamadı: \(error.localizedDescription)"); bitir(4)
    }
    yaz("hazir", dil)

    görev = tanıyıcı.recognitionTask(with: r) { sonuç, hata in
        if let sonuç = sonuç {
            let metin = sonuç.bestTranscription.formattedString
            yaz(sonuç.isFinal ? "son" : "kismi", metin)
            if sonuç.isFinal { bitir(0) }
        }
        if let hata = hata {
            yaz("hata", hata.localizedDescription); bitir(5)
        }
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
