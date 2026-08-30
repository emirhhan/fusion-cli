import Foundation
import Speech
import AVFoundation

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
guard let tanıyıcı = SFSpeechRecognizer(locale: Locale(identifier: dil)) else {
    yaz("hata", "Bu dil için tanıyıcı yok: \(dil)"); exit(2)
}

let motor = AVAudioEngine()
var istek: SFSpeechAudioBufferRecognitionRequest?
var görev: SFSpeechRecognitionTask?

func başlat() {
    guard tanıyıcı.isAvailable else { yaz("hata", "Tanıyıcı şu an kullanılamıyor."); exit(3) }
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
    motor.prepare()
    do { try motor.start() } catch {
        yaz("hata", "Ses motoru başlatılamadı: \(error.localizedDescription)"); exit(4)
    }
    yaz("hazir", dil)

    görev = tanıyıcı.recognitionTask(with: r) { sonuç, hata in
        if let sonuç = sonuç {
            let metin = sonuç.bestTranscription.formattedString
            yaz(sonuç.isFinal ? "son" : "kismi", metin)
            if sonuç.isFinal { exit(0) }
        }
        if let hata = hata {
            yaz("hata", hata.localizedDescription); exit(5)
        }
    }
}

SFSpeechRecognizer.requestAuthorization { durum in
    DispatchQueue.main.async {
        switch durum {
        case .authorized: başlat()
        case .denied: yaz("hata", "Konuşma tanıma izni reddedildi."); exit(6)
        case .restricted: yaz("hata", "Konuşma tanıma bu cihazda kısıtlı."); exit(7)
        default: yaz("hata", "Konuşma tanıma izni verilmedi."); exit(8)
        }
    }
}
RunLoop.main.run()
