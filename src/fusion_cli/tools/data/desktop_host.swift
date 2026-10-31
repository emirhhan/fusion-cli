import AppKit
import ApplicationServices
import ScreenCaptureKit
import CryptoKit

// Kimlik doğrulanamazsa başka pencereye veya ekran geneline geri düşülmez.
func emit(_ value: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: value), let text = String(data: data, encoding: .utf8) { print(text) }
}
func fail(_ text: String) { emit(["ok": false, "status": "unavailable", "metin": text]) }
func attribute(_ element: AXUIElement, _ name: String) -> CFTypeRef? {
    var result: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, name as CFString, &result) == .success else { return nil }
    return result
}
func windowFrame(_ element: AXUIElement) -> CGRect? {
    guard let position = attribute(element, kAXPositionAttribute), CFGetTypeID(position) == AXValueGetTypeID(),
        let size = attribute(element, kAXSizeAttribute), CFGetTypeID(size) == AXValueGetTypeID() else { return nil }
    var point = CGPoint.zero, dimensions = CGSize.zero
    guard AXValueGetValue(unsafeBitCast(position, to: AXValue.self), .cgPoint, &point),
        AXValueGetValue(unsafeBitCast(size, to: AXValue.self), .cgSize, &dimensions) else { return nil }
    return CGRect(origin: point, size: dimensions)
}
// Geometri eşleşmesi yalnız AX pencere numarası bulunmayan öğelerde kullanılabilir.
func canUseWindowFallback(_ explicitNumber: Int?, _ candidateFrame: CGRect?, _ candidateTitle: String,
    _ targetFrame: CGRect, _ targetTitle: String) -> Bool {
    explicitNumber == nil && candidateFrame == targetFrame && candidateTitle == targetTitle
}
func targetWindow(_ windows: [AXUIElement], _ row: [String: Any], _ id: Int) -> AXUIElement? {
    let direct = windows.filter { (attribute($0, "AXWindowNumber") as? NSNumber)?.intValue == id }
    if !direct.isEmpty { return direct.count == 1 ? direct[0] : nil }
    guard let bounds = row[kCGWindowBounds as String] as? NSDictionary,
        let frame = CGRect(dictionaryRepresentation: bounds) else { return nil }
    let title = row[kCGWindowName as String] as? String ?? ""
    let matches = windows.filter {
        canUseWindowFallback((attribute($0, "AXWindowNumber") as? NSNumber)?.intValue,
            windowFrame($0), attribute($0, kAXTitleAttribute) as? String ?? "", frame, title)
    }
    return matches.count == 1 ? matches[0] : nil
}
struct Entry {
    let element: AXUIElement
    let path: [Int]
    let identity: String
    let valueDigest: String
}
func digest(_ text: String) -> String {
    SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
}
func identity(_ element: AXUIElement) -> String {
    [kAXRoleAttribute, kAXTitleAttribute, kAXIdentifierAttribute, kAXDescriptionAttribute].map {
        attribute(element, $0) as? String ?? ""
    }.joined(separator: "\u{001f}")
}
func tree(_ window: AXUIElement) -> [Entry] {
    var queue: [(AXUIElement, [Int])] = [(window, [])], entries: [Entry] = []
    while !queue.isEmpty && entries.count < 500 {
        let (element, path) = queue.removeFirst()
        let value = attribute(element, kAXValueAttribute).map { String(describing: $0) } ?? ""
        entries.append(Entry(element: element, path: path, identity: identity(element), valueDigest: digest(value)))
        let children = attribute(element, kAXChildrenAttribute) as? [AXUIElement] ?? []
        for (index, child) in children.enumerated() { queue.append((child, path + [index])) }
    }
    return entries
}
func treeDigest(_ entries: [Entry]) -> String {
    digest(entries.map { "\($0.path):\($0.identity):\($0.valueDigest)" }.joined(separator: "\n"))
}
func reference(_ entry: Entry, _ fingerprint: String, _ id: Int, _ pid: Int32) -> String {
    let payload: [String: Any] = ["path": entry.path, "identity": entry.identity, "fingerprint": fingerprint, "id": id, "pid": Int(pid)]
    return (try? JSONSerialization.data(withJSONObject: payload).base64EncodedString()) ?? ""
}
func action(_ window: AXUIElement, _ id: Int, _ pid: Int32) {
    let input = FileHandle.standardInput.readDataToEndOfFile()
    guard input.count <= 100_000,
        let request = try? JSONSerialization.jsonObject(with: input) as? [String: Any],
        let ref = request["ref"] as? String, let bytes = Data(base64Encoded: ref),
        let token = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
        (token["id"] as? Int) == id, (token["pid"] as? Int) == Int(pid),
        let path = token["path"] as? [Int], let expectedIdentity = token["identity"] as? String,
        let fingerprint = token["fingerprint"] as? String else { fail("Öğe başvurusu geçersiz; pencereyi yeniden incele."); return }
    let entries = tree(window)
    guard entries.count < 500, treeDigest(entries) == fingerprint,
        entries.filter({ $0.identity == expectedIdentity }).count == 1,
        let entry = entries.first(where: { $0.path == path && $0.identity == expectedIdentity }) else {
        fail("Hedef öğe değişti veya kimliği belirsiz; pencereyi yeniden incele."); return
    }
    let result: AXError
    if request["action"] as? String == "press" {
        var supported: CFArray?
        guard AXUIElementCopyActionNames(entry.element, &supported) == .success,
            (supported as? [String] ?? []).contains(kAXPressAction) else { fail("Öğe AXPress desteklemiyor."); return }
        result = AXUIElementPerformAction(entry.element, kAXPressAction as CFString)
    } else if request["action"] as? String == "set_value", let value = request["value"] as? String, value.count <= 10_000 {
        var settable = DarwinBoolean(false)
        guard AXUIElementIsAttributeSettable(entry.element, kAXValueAttribute as CFString, &settable) == .success,
            settable.boolValue else { fail("Öğe AXValue değiştirmeyi desteklemiyor."); return }
        result = AXUIElementSetAttributeValue(entry.element, kAXValueAttribute as CFString, value as CFString)
        guard result == .success, attribute(entry.element, kAXValueAttribute) as? String == value else {
            fail("Alan değeri doğrulanamadı; işlem tekrarlanmadı."); return
        }
    } else { fail("Yalnız press ve set_value destekleniyor."); return }
    emit(["ok": result == .success, "status": result == .success ? "executed" : "unavailable", "id": id, "pid": Int(pid), "metin": result == .success ? "Hedef öğede AX işlemi çalıştırıldı; uygulama sonucu yeniden incelenmeli." : "Hedef öğe AX işlemini reddetti."])
}
// Eylem hedefi (P-007/P-008): noktadaki ya da öndeki uygulama ve öğe; değer (metin) okunmaz.
let actionableRoles: Set<String> = ["AXButton", "AXMenuItem", "AXMenuBarItem", "AXLink", "AXCheckBox",
    "AXRadioButton", "AXPopUpButton", "AXMenuButton", "AXTab", "AXDisclosureTriangle"]
func elementInfo(_ element: AXUIElement) -> [String: Any] {
    var current: AXUIElement? = element
    var depth = 0
    while let candidate = current, depth < 4 {
        let role = attribute(candidate, kAXRoleAttribute) as? String ?? ""
        if actionableRoles.contains(role) { break }
        current = attribute(candidate, kAXParentAttribute).map { unsafeBitCast($0, to: AXUIElement.self) }
        depth += 1
    }
    let chosen = (current.flatMap { actionableRoles.contains(attribute($0, kAXRoleAttribute) as? String ?? "") ? $0 : nil }) ?? element
    return ["role": attribute(chosen, kAXRoleAttribute) as? String ?? "",
        "subrole": attribute(chosen, kAXSubroleAttribute) as? String ?? "",
        "title": attribute(chosen, kAXTitleAttribute) as? String ?? "",
        "description": attribute(chosen, kAXDescriptionAttribute) as? String ?? "",
        "help": attribute(chosen, kAXHelpAttribute) as? String ?? ""]
}
func appInfo(_ pid: pid_t) -> [String: Any]? {
    guard let app = NSRunningApplication(processIdentifier: pid) else { return nil }
    return ["app": app.localizedName ?? "", "bundle": app.bundleIdentifier ?? "", "pid": Int(pid)]
}
func target() {
    let input = FileHandle.standardInput.readDataToEndOfFile()
    let request = (input.count <= 10_000 ? (try? JSONSerialization.jsonObject(with: input) as? [String: Any]) : nil) ?? [:]
    let trusted = AXIsProcessTrusted()
    if let point = request["point"] as? [Double], point.count == 2 {
        guard trusted else { fail("macOS Erişilebilirlik izni gerekli."); return }
        var element: AXUIElement?
        guard AXUIElementCopyElementAtPosition(AXUIElementCreateSystemWide(), Float(point[0]), Float(point[1]), &element) == .success,
            let hit = element else { fail("Noktadaki öğe okunamadı."); return }
        var pid: pid_t = 0
        guard AXUIElementGetPid(hit, &pid) == .success, var info = appInfo(pid) else { fail("Noktadaki uygulama okunamadı."); return }
        info["ok"] = true
        info["element"] = elementInfo(hit)
        emit(info)
    } else if let pid = request["pid"] as? Int, pid > 0 {
        guard var info = appInfo(pid_t(pid)) else { fail("Süreç bulunamadı."); return }
        info["ok"] = true
        emit(info)
    } else {
        guard let front = NSWorkspace.shared.frontmostApplication, var info = appInfo(front.processIdentifier) else { fail("Öndeki uygulama okunamadı."); return }
        info["ok"] = true
        if trusted, let focused = attribute(AXUIElementCreateApplication(front.processIdentifier), kAXFocusedUIElementAttribute) {
            info["element"] = elementInfo(unsafeBitCast(focused, to: AXUIElement.self))
        }
        emit(info)
    }
}
// Esc ile durdurma (P-033): oturum düzeyinde etkin olay musluğu; Esc'i yutar ve bildirir.
// Fusion'ın kendi gönderdiği Esc (desktop_key) olayın kaynak pid'inden ayırt edilir.
var escIgnoredPid: Int64 = 0
var escTap: CFMachPort?
func writeLine(_ value: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: value) {
        FileHandle.standardOutput.write(data + Data([0x0a]))
    }
}
func escWatch() {
    guard AXIsProcessTrusted() else { fail("macOS Erişilebilirlik izni gerekli."); return }
    let mask = CGEventMask(1 << CGEventType.keyDown.rawValue)
    let callback: CGEventTapCallBack = { _, type, event, _ in
        if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
            if let tap = escTap { CGEvent.tapEnable(tap: tap, enable: true) }
            return Unmanaged.passUnretained(event)
        }
        let source = event.getIntegerValueField(.eventSourceUnixProcessID)
        if type == .keyDown && event.getIntegerValueField(.keyboardEventKeycode) == 53 && source != escIgnoredPid {
            writeLine(["esc": true])
            return nil
        }
        return Unmanaged.passUnretained(event)
    }
    guard let tap = CGEvent.tapCreate(tap: .cgSessionEventTap, place: .headInsertEventTap, options: .defaultTap,
        eventsOfInterest: mask, callback: callback, userInfo: nil) else { fail("Esc dinleyicisi kurulamadı."); return }
    escTap = tap
    CFRunLoopAddSource(CFRunLoopGetCurrent(), CFMachPortCreateRunLoopSource(nil, tap, 0), .commonModes)
    CGEvent.tapEnable(tap: tap, enable: true)
    writeLine(["ok": true, "status": "watching"])
    // Ebeveyn stdin'i kapatınca (tur bitti ya da süreç öldü) dinleyici de kapanır.
    DispatchQueue.global().async { _ = FileHandle.standardInput.readDataToEndOfFile(); exit(0) }
    CFRunLoopRun()
}
// Uygulamaları gizle / geri göster (P-033): yalnız normal (Dock'ta görünen) uygulamalar.
func hideOthers() {
    let input = FileHandle.standardInput.readDataToEndOfFile()
    let request = (input.count <= 10_000 ? (try? JSONSerialization.jsonObject(with: input) as? [String: Any]) : nil) ?? [:]
    var keep = Set(((request["keep"] as? [Int]) ?? []).map { pid_t($0) })
    if let front = NSWorkspace.shared.frontmostApplication { keep.insert(front.processIdentifier) }
    var hidden: [Int] = []
    for app in NSWorkspace.shared.runningApplications where app.activationPolicy == .regular && !app.isHidden && !keep.contains(app.processIdentifier) {
        if app.hide() { hidden.append(Int(app.processIdentifier)) }
    }
    emit(["ok": true, "hidden": hidden])
}
func unhideApps() {
    let input = FileHandle.standardInput.readDataToEndOfFile()
    let request = (input.count <= 10_000 ? (try? JSONSerialization.jsonObject(with: input) as? [String: Any]) : nil) ?? [:]
    var shown = 0
    for pid in (request["pids"] as? [Int]) ?? [] {
        if let app = NSRunningApplication(processIdentifier: pid_t(pid)), app.unhide() { shown += 1 }
    }
    emit(["ok": true, "shown": shown])
}
let args = CommandLine.arguments
let rows = CGWindowListCopyWindowInfo([.optionAll, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []
if args.count > 1 && args[1] == "list" {
    let windows = rows.compactMap { row -> [String: Any]? in
        guard (row[kCGWindowLayer as String] as? Int) == 0,
            let id = row[kCGWindowNumber as String] as? Int,
            let pid = row[kCGWindowOwnerPID as String] as? Int,
            let app = NSRunningApplication(processIdentifier: pid_t(pid)), app.activationPolicy == .regular else { return nil }
        var iconData = ""
        if let icon = app.icon, let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 24,
            pixelsHigh: 24, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0),
            let context = NSGraphicsContext(bitmapImageRep: bitmap) {
            NSGraphicsContext.saveGraphicsState()
            NSGraphicsContext.current = context
            icon.draw(in: NSRect(x: 0, y: 0, width: 24, height: 24))
            NSGraphicsContext.restoreGraphicsState()
            if let png = bitmap.representation(using: .png, properties: [:]) {
                iconData = "data:image/png;base64," + png.base64EncodedString()
            }
        }
        return ["icon": iconData, "kind": "window", "id": id, "pid": pid, "app": app.localizedName ?? "Uygulama", "title": row[kCGWindowName as String] as? String ?? "", "visible": row[kCGWindowIsOnscreen as String] as? Bool ?? false]
    }
    emit(["ok": true, "windows": windows])
} else if args.count == 3 && args[1] == "escwatch", let ignored = Int64(args[2]) {
    escIgnoredPid = ignored
    escWatch()
} else if args.count == 2 && args[1] == "hide" {
    hideOthers()
} else if args.count == 2 && args[1] == "unhide" {
    unhideApps()
} else if args.count == 2 && args[1] == "target" {
    target()
} else if args.count == 3, args[1] == "screen", let displayID = UInt32(args[2]) {
    // Ekranı Fusion'ın (ve isteyen sürecin) pencereleri HARİÇ yakala (P-033): model kendi
    // sohbet penceresini görmez, görüntü kirlenmez. Yalnız ScreenCaptureKit; geri düşüş yok.
    if #available(macOS 14.0, *) {
        let input = FileHandle.standardInput.readDataToEndOfFile()
        let request = (input.count <= 100_000 ? (try? JSONSerialization.jsonObject(with: input) as? [String: Any]) : nil) ?? [:]
        let excludedPids = Set((request["excludePids"] as? [Int]) ?? [])
        // Reddedilen/engelli uygulamalar da görüntüye girmez (P-007): ad ya da paket öneki.
        let excludedNames = Set(((request["excludeNames"] as? [String]) ?? []).map { $0.lowercased() })
        let excludedPrefixes = ((request["excludeBundlePrefixes"] as? [String]) ?? []).map { $0.lowercased() }
        let maxWidth = request["maxWidth"] as? Int ?? 0
        Task {
            do {
                let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
                guard let display = content.displays.first(where: { $0.displayID == displayID }) else { fail("Ekran bulunamadı."); exit(0) }
                let excluded = content.applications.filter { app in
                    let bundle = app.bundleIdentifier.lowercased()
                    return excludedPids.contains(Int(app.processID)) || excludedNames.contains(app.applicationName.lowercased())
                        || excludedPrefixes.contains { !bundle.isEmpty && bundle.hasPrefix($0) }
                }
                let filter = SCContentFilter(display: display, excludingApplications: excluded, exceptingWindows: [])
                var width = max(1, CGDisplayPixelsWide(displayID)), height = max(1, CGDisplayPixelsHigh(displayID))
                let configuration = SCStreamConfiguration()
                // Bölge (region=): ekranın nokta dikdörtgeni; dışlama bölgede de geçerlidir (P-007).
                if let rect = request["rect"] as? [Double], rect.count == 4, rect[2] > 0, rect[3] > 0 {
                    let scale = Double(width) / max(1, Double(display.width))
                    configuration.sourceRect = CGRect(x: rect[0], y: rect[1], width: rect[2], height: rect[3])
                    width = max(1, Int(rect[2] * scale)); height = max(1, Int(rect[3] * scale))
                }
                if maxWidth > 0 && width > maxWidth { height = max(1, height * maxWidth / width); width = maxWidth }
                configuration.width = width
                configuration.height = height
                configuration.showsCursor = true
                let image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: configuration)
                guard let data = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]), data.count <= 12_000_000 else { fail("Ekran görüntüsü üretilemedi veya sınırı aştı."); exit(0) }
                emit(["ok": true, "kind": "display", "id": Int(displayID), "width": image.width, "height": image.height, "excluded": excluded.count, "image": "data:image/png;base64," + data.base64EncodedString(), "source": "display_capture"])
            } catch { fail("Ekran yakalanamadı: \(error.localizedDescription)") }
            exit(0)
        }
        dispatchMain()
    } else { fail("Ekran yakalama macOS 14 veya üstünü gerektiriyor.") }
} else if args.count == 4, let id = Int(args[2]), let pid = Int32(args[3]) {
    guard rows.contains(where: { ($0[kCGWindowNumber as String] as? Int) == id && ($0[kCGWindowOwnerPID as String] as? Int) == Int(pid) }) else { fail("Hedef pencere kapandı veya kimliği değişti."); exit(0) }
    if args[1] == "snapshot" {
        if #available(macOS 14.0, *) {
            Task {
                do {
                    let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
                    guard let window = content.windows.first(where: { Int($0.windowID) == id && $0.owningApplication?.processID == pid }) else { fail("Hedef pencere yakalanamıyor."); exit(0) }
                    let configuration = SCStreamConfiguration()
                    configuration.width = max(1, Int(window.frame.width))
                    configuration.height = max(1, Int(window.frame.height))
                    configuration.showsCursor = false
                    let image = try await SCScreenshotManager.captureImage(contentFilter: SCContentFilter(desktopIndependentWindow: window), configuration: configuration)
                    guard let data = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]), data.count <= 12_000_000 else { fail("Pencere görüntüsü üretilemedi veya sınırı aştı."); exit(0) }
                    emit(["ok": true, "kind": "window", "id": id, "pid": Int(pid), "image": "data:image/png;base64," + data.base64EncodedString(), "source": "window_capture"])
                } catch { fail("Pencere yakalanamadı: \(error.localizedDescription)") }
                exit(0)
            }
            dispatchMain()
        } else { fail("Pencere yakalama macOS 14 veya üstünü gerektiriyor.") }
    } else {
        guard AXIsProcessTrusted() else { fail("macOS Erişilebilirlik izni gerekli."); exit(0) }
        let application = AXUIElementCreateApplication(pid)
        let windows = attribute(application, kAXWindowsAttribute) as? [AXUIElement] ?? []
        guard let row = rows.first(where: { ($0[kCGWindowNumber as String] as? Int) == id && ($0[kCGWindowOwnerPID as String] as? Int) == Int(pid) }),
            let window = targetWindow(windows, row, id) else { fail("Hedef pencerenin erişilebilirlik kimliği doğrulanamadı."); exit(0) }
        if args[1] == "focus" {
            let raised = AXUIElementPerformAction(window, kAXRaiseAction as CFString) == .success
            let activated = NSRunningApplication(processIdentifier: pid)?.activate(options: []) ?? false
            emit(["ok": raised && activated, "metin": raised && activated ? "Pencere öne getirildi." : "Pencere öne getirilemedi."])
        } else if args[1] == "action" {
            action(window, id, pid)
        } else if args[1] == "inspect" {
            let entries = tree(window)
            let fingerprint = treeDigest(entries)
            let elements = entries.map { entry -> [String: Any] in
                var actions: CFArray?
                AXUIElementCopyActionNames(entry.element, &actions)
                var settable = DarwinBoolean(false)
                AXUIElementIsAttributeSettable(entry.element, kAXValueAttribute as CFString, &settable)
                return ["role": attribute(entry.element, kAXRoleAttribute) as? String ?? "",
                    "title": attribute(entry.element, kAXTitleAttribute) as? String ?? "",
                    "ref": reference(entry, fingerprint, id, pid),
                    "actions": actions as? [String] ?? [], "can_set_value": settable.boolValue,
                    "unique": entries.count < 500 && entries.filter { $0.identity == entry.identity }.count == 1]
            }
            emit(["ok": true, "elements": elements, "fingerprint": fingerprint, "id": id, "pid": Int(pid)])
        } else { fail("Arka plan değiştirme işlemi desteklenmiyor.") }
    }
} else { fail("Masaüstü hedefi geçersiz.") }
