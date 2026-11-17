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
func windowMetadataTimeRemaining(_ deadline: Double?) -> Bool {
    guard let deadline = deadline else { return true }
    return ProcessInfo.processInfo.systemUptime < deadline
}
func targetWindow(_ windows: [AXUIElement], _ row: [String: Any], _ id: Int,
    _ deadline: Double? = nil) -> AXUIElement? {
    let direct = windows.filter {
        windowMetadataTimeRemaining(deadline) &&
            (attribute($0, "AXWindowNumber") as? NSNumber)?.intValue == id
    }
    guard windowMetadataTimeRemaining(deadline) else { return nil }
    if !direct.isEmpty { return direct.count == 1 ? direct[0] : nil }
    guard let bounds = row[kCGWindowBounds as String] as? NSDictionary,
        let frame = CGRect(dictionaryRepresentation: bounds) else { return nil }
    let title = row[kCGWindowName as String] as? String ?? ""
    let matches = windows.filter {
        windowMetadataTimeRemaining(deadline) &&
            canUseWindowFallback((attribute($0, "AXWindowNumber") as? NSNumber)?.intValue,
                windowFrame($0), attribute($0, kAXTitleAttribute) as? String ?? "", frame, title)
    }
    guard windowMetadataTimeRemaining(deadline) else { return nil }
    return matches.count == 1 ? matches[0] : nil
}
struct Entry {
    let element: AXUIElement
    let path: [Int]
    let identity: String
    let valueDigest: String
    let valueKind: String
    let displayValue: String?
    let displayValueTruncated: Bool
    let actionLabels: [String: String]
}
func digest(_ text: String) -> String {
    SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
}
func identity(_ element: AXUIElement) -> String {
    [kAXRoleAttribute, kAXTitleAttribute, kAXIdentifierAttribute, kAXDescriptionAttribute].map {
        attribute(element, $0) as? String ?? ""
    }.joined(separator: "\u{001f}")
}
// Unsupported/no-value subroles are explicitly absent; failed reads stay unknown.
func displaySecurityString(_ element: AXUIElement, _ name: String) -> String? {
    var result: CFTypeRef?
    let status = AXUIElementCopyAttributeValue(element, name as CFString, &result)
    if status == .attributeUnsupported || status == .noValue { return "" }
    guard status == .success else { return nil }
    return result as? String
}
// Pure policy helpers: preserve actual query status through every ancestor.
enum DisplayEditability: Equatable {
    case readOnly, editable, unsupported, unknown
}
func displayEditability(_ status: AXError, _ settable: Bool) -> DisplayEditability {
    if status == .success { return settable ? .editable : .readOnly }
    if status == .attributeUnsupported || status == .noValue { return .unsupported }
    return .unknown
}
func displayBranchIsSafe(_ role: String?, _ subrole: String?, _ ancestorsSafe: Bool,
    _ editability: DisplayEditability) -> Bool {
    guard ancestorsSafe, let role = role, !role.isEmpty, role != "AXUnknown",
        let subrole = subrole,
        editability == .readOnly || editability == .unsupported else { return false }
    let security = (role + " " + subrole).lowercased()
    guard !security.contains("secure"), !security.contains("password"),
        !["AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"].contains(role) else { return false }
    return true
}
func safeDisplayValue(_ role: String?, _ branchSafe: Bool,
    _ editability: DisplayEditability, _ rawValue: Any?) -> String? {
    guard branchSafe, role == "AXStaticText", editability == .readOnly,
        let value = rawValue as? String else { return nil }
    return String(value.prefix(1000))
}
func safeActionLabels(_ role: String?, _ branchSafe: Bool,
    _ editability: DisplayEditability, _ actions: [String],
    _ rawDescription: Any?, _ rawIdentifier: Any?) -> [String: String] {
    guard branchSafe, role == "AXButton", actions.contains("AXPress"),
        editability == .readOnly || editability == .unsupported else { return [:] }
    var labels: [String: String] = [:]
    if let description = rawDescription as? String, !description.isEmpty {
        labels["description"] = String(description.prefix(256))
        labels["label"] = labels["description"]
        labels["label_source"] = "AXDescription"
    }
    if let identifier = rawIdentifier as? String, !identifier.isEmpty {
        labels["identifier"] = String(identifier.prefix(256))
        if labels["label"] == nil {
            labels["label"] = labels["identifier"]
            labels["label_source"] = "AXIdentifier"
        }
    }
    return labels
}
func safeWindowSelectionMetadata(_ mappingVerified: Bool, _ role: String?,
    _ subrole: String?, _ isMain: Bool?, _ isFocused: Bool?) -> [String: Any] {
    guard mappingVerified, role == "AXWindow" else { return [:] }
    var metadata: [String: Any] = ["role": "AXWindow"]
    if let subrole = subrole, !subrole.isEmpty { metadata["subrole"] = String(subrole.prefix(128)) }
    if let isMain = isMain { metadata["is_main"] = isMain }
    if let isFocused = isFocused { metadata["is_focused"] = isFocused }
    return metadata
}
func fingerprintValueKind(_ value: CFTypeRef?) -> String {
    guard let value = value else { return "absent" }
    let kind = CFGetTypeID(value)
    if kind == CFStringGetTypeID() { return "string" }
    if kind == CFBooleanGetTypeID() { return "boolean" }
    if kind == CFNumberGetTypeID() { return "number" }
    if kind == AXValueGetTypeID() { return "ax_value" }
    if kind == AXUIElementGetTypeID() { return "element" }
    if kind == CFArrayGetTypeID() { return "array" }
    return "other"
}
func tree(_ window: AXUIElement) -> [Entry] {
    var queue: [(AXUIElement, [Int], Bool)] = [(window, [], true)], entries: [Entry] = []
    while !queue.isEmpty && entries.count < 500 {
        let (element, path, ancestorsSafe) = queue.removeFirst()
        let role = displaySecurityString(element, kAXRoleAttribute)
        let subrole = displaySecurityString(element, kAXSubroleAttribute)
        var settable = DarwinBoolean(false)
        let editableStatus = AXUIElementIsAttributeSettable(element, kAXValueAttribute as CFString, &settable)
        let editability = displayEditability(editableStatus, settable.boolValue)
        let branchSafe = displayBranchIsSafe(role, subrole, ancestorsSafe, editability)
        let rawValue = attribute(element, kAXValueAttribute)
        // Fingerprint compatibility is independent from the stricter display type contract.
        let value = rawValue.map { String(describing: $0) } ?? ""
        let display = safeDisplayValue(role, branchSafe, editability, rawValue)
        let stringValue = rawValue as? String
        var labels: [String: String] = [:]
        if branchSafe && role == "AXButton" {
            var actionNames: CFArray?
            let status = AXUIElementCopyActionNames(element, &actionNames)
            let actions = status == .success ? (actionNames as? [String] ?? []) : []
            labels = safeActionLabels(role, branchSafe, editability, actions,
                attribute(element, kAXDescriptionAttribute), attribute(element, kAXIdentifierAttribute))
        }
        entries.append(Entry(element: element, path: path, identity: identity(element),
            valueDigest: digest(value), valueKind: fingerprintValueKind(rawValue), displayValue: display,
            displayValueTruncated: display != nil && (stringValue?.count ?? 0) > 1000, actionLabels: labels))
        let children = attribute(element, kAXChildrenAttribute) as? [AXUIElement] ?? []
        for (index, child) in children.enumerated() {
            queue.append((child, path + [index], branchSafe))
        }
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
func actionGuardChecks(_ count: Int, _ fingerprintMatches: Bool,
    _ identityCount: Int, _ pathMatches: Bool) -> [String: Bool] {
    ["tree_complete": count < 500, "fingerprint_matches": fingerprintMatches,
        "identity_unique": identityCount == 1, "path_identity_matches": pathMatches]
}
func valueKindCounts(_ entries: [Entry]) -> [String: Int] {
    entries.reduce(into: [:]) { $0[$1.valueKind, default: 0] += 1 }
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
    let entry = entries.first(where: { $0.path == path && $0.identity == expectedIdentity })
    let checks = actionGuardChecks(entries.count, treeDigest(entries) == fingerprint,
        entries.filter({ $0.identity == expectedIdentity }).count, entry != nil)
    guard checks.values.allSatisfy({ $0 }), let entry = entry else {
        emit(["ok": false, "status": "unavailable",
            "metin": "Hedef öğe değişti veya kimliği belirsiz; pencereyi yeniden incele.",
            "action_checks": checks, "value_kinds": valueKindCounts(entries)])
        return
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
// Native process metadata only; this proof is never accepted from tool arguments.
func isSystemCalculator(_ pid: pid_t, _ bundleIdentifier: String?,
    _ bundleURL: URL?, _ executableURL: URL?) -> Bool {
    guard pid > 0, bundleIdentifier == "com.apple.calculator",
        let bundleURL = bundleURL, bundleURL.isFileURL,
        let executableURL = executableURL, executableURL.isFileURL else { return false }
    return bundleURL.resolvingSymlinksInPath().standardizedFileURL.path ==
        "/System/Applications/Calculator.app" &&
        executableURL.resolvingSymlinksInPath().standardizedFileURL.path ==
        "/System/Applications/Calculator.app/Contents/MacOS/Calculator"
}
func appInfo(_ pid: pid_t) -> [String: Any]? {
    guard let app = NSRunningApplication(processIdentifier: pid) else { return nil }
    return ["app": app.localizedName ?? "", "bundle": app.bundleIdentifier ?? "", "pid": Int(pid),
        "system_calculator": isSystemCalculator(pid, app.bundleIdentifier,
            app.bundleURL, app.executableURL)]
}
// A process can own many windows: pin a CG identity as well as AX title/geometry.
func windowInfo(_ window: AXUIElement, _ pid: pid_t) -> [String: Any]? {
    guard let frame = windowFrame(window) else { return nil }
    let rows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []
    let matches = rows.filter { row in
        guard (row[kCGWindowOwnerPID as String] as? Int) == Int(pid),
            let id = row[kCGWindowNumber as String] as? Int else { return false }
        return targetWindow([window], row, id) != nil
    }
    guard matches.count == 1, let id = matches[0][kCGWindowNumber as String] as? Int else { return nil }
    return ["id": id, "title": attribute(window, kAXTitleAttribute) as? String ?? "",
        "bounds": [frame.origin.x, frame.origin.y, frame.width, frame.height]]
}
struct AppWindowSnapshot {
    let windows: [AXUIElement]?
    let windowCount: Int?
    let focused: AXUIElement?
}
func appWindowSnapshot(_ pid: pid_t, _ deadline: Double) -> AppWindowSnapshot {
    let app = AXUIElementCreateApplication(pid)
    guard windowMetadataTimeRemaining(deadline),
        AXUIElementSetMessagingTimeout(app, 0.01) == .success else {
        return AppWindowSnapshot(windows: nil, windowCount: nil, focused: nil)
    }
    let all = attribute(app, kAXWindowsAttribute) as? [AXUIElement]
    let rawFocused = windowMetadataTimeRemaining(deadline) ? attribute(app, kAXFocusedWindowAttribute) : nil
    var focused = rawFocused.flatMap {
        CFGetTypeID($0) == AXUIElementGetTypeID() ? unsafeBitCast($0, to: AXUIElement.self) : nil
    }
    let complete = all.flatMap { windows -> [AXUIElement]? in
        guard windows.count <= 16 else { return nil }
        for window in windows {
            guard windowMetadataTimeRemaining(deadline),
                AXUIElementSetMessagingTimeout(window, 0.01) == .success else { return nil }
        }
        return windows
    }
    if let candidate = focused,
        (!windowMetadataTimeRemaining(deadline) || AXUIElementSetMessagingTimeout(candidate, 0.01) != .success) {
        focused = nil
    }
    return AppWindowSnapshot(windows: complete, windowCount: all?.count, focused: focused)
}
func windowBoolean(_ window: AXUIElement, _ name: String) -> Bool? {
    guard let raw = attribute(window, name), CFGetTypeID(raw) == CFBooleanGetTypeID() else { return nil }
    return CFBooleanGetValue(unsafeBitCast(raw, to: CFBoolean.self))
}
func targetWindowDiagnostics(_ pid: pid_t, _ expectedTitle: String, _ expected: CGRect) -> [String: Any] {
    guard AXIsProcessTrusted() else { return ["ax_trusted": false] }
    let deadline = ProcessInfo.processInfo.systemUptime + 0.35
    let snapshot = appWindowSnapshot(pid, deadline)
    var result: [String: Any] = ["ax_trusted": true, "windows_known": snapshot.windowCount != nil,
        "focused_window_known": snapshot.focused != nil]
    if let count = snapshot.windowCount { result["windows_count"] = count; result["windows_truncated"] = count > 8 }
    func metadata(_ window: AXUIElement) -> [String: Any] {
        guard windowMetadataTimeRemaining(deadline) else { return ["query_budget_exhausted": true] }
        var row: [String: Any] = [:]
        if let role = attribute(window, kAXRoleAttribute) as? String { row["role"] = String(role.prefix(128)) }
        if windowMetadataTimeRemaining(deadline), let subrole = attribute(window, kAXSubroleAttribute) as? String { row["subrole"] = String(subrole.prefix(128)) }
        if windowMetadataTimeRemaining(deadline), let main = windowBoolean(window, kAXMainAttribute) { row["is_main"] = main }
        if let focused = snapshot.focused { row["is_focused"] = CFEqual(window, focused) }
        if windowMetadataTimeRemaining(deadline) { row["window_number_known"] = (attribute(window, "AXWindowNumber") as? NSNumber)?.intValue ?? 0 > 0 }
        if windowMetadataTimeRemaining(deadline), let title = attribute(window, kAXTitleAttribute) as? String { row["title_matches_expected"] = title == expectedTitle }
        if windowMetadataTimeRemaining(deadline), let frame = windowFrame(window) { row["bounds_match_expected"] = frame == expected }
        return row
    }
    result["windows"] = snapshot.windows.map { Array($0.prefix(8)).map(metadata) } ?? []
    if let focused = snapshot.focused { result["focused_window"] = metadata(focused) }
    return result
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
        let window = attribute(hit, kAXRoleAttribute) as? String == "AXWindow" ? hit :
            attribute(hit, kAXWindowAttribute).map { unsafeBitCast($0, to: AXUIElement.self) }
        if let window = window { info["window"] = windowInfo(window, pid) }
        emit(info)
    } else if let pid = request["pid"] as? Int, pid > 0 {
        guard var info = appInfo(pid_t(pid)) else { fail("Süreç bulunamadı."); return }
        info["ok"] = true
        if let expected = request["window_diagnostics"] as? [String: Any],
            let title = expected["title"] as? String, title.count <= 500,
            let bounds = expected["bounds"] as? [Double], bounds.count == 4,
            bounds.allSatisfy({ $0.isFinite }), bounds[2] > 0, bounds[3] > 0 {
            info["window_diagnostics"] = targetWindowDiagnostics(pid_t(pid), title,
                CGRect(x: bounds[0], y: bounds[1], width: bounds[2], height: bounds[3]))
        }
        emit(info)
    } else {
        guard let front = NSWorkspace.shared.frontmostApplication, var info = appInfo(front.processIdentifier) else { fail("Öndeki uygulama okunamadı."); return }
        info["ok"] = true
        if trusted, let window = attribute(AXUIElementCreateApplication(front.processIdentifier), kAXFocusedWindowAttribute) {
            info["window"] = windowInfo(unsafeBitCast(window, to: AXUIElement.self), front.processIdentifier)
        }
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
    let eligibleRows = rows.filter { row in
        guard (row[kCGWindowLayer as String] as? Int) == 0,
            row[kCGWindowNumber as String] is Int,
            let pid = row[kCGWindowOwnerPID as String] as? Int,
            let app = NSRunningApplication(processIdentifier: pid_t(pid)) else { return false }
        return app.activationPolicy == .regular
    }
    let metadataDeadline = ProcessInfo.processInfo.systemUptime + 0.35
    var snapshots: [Int: AppWindowSnapshot] = [:]
    var metadataByID: [Int: [String: Any]] = [:]
    if AXIsProcessTrusted() {
        for row in eligibleRows {
            guard windowMetadataTimeRemaining(metadataDeadline),
                let id = row[kCGWindowNumber as String] as? Int,
                let pid = row[kCGWindowOwnerPID as String] as? Int else { break }
            if snapshots[pid] == nil { snapshots[pid] = appWindowSnapshot(pid_t(pid), metadataDeadline) }
            if let snapshot = snapshots[pid], let candidates = snapshot.windows,
                let window = targetWindow(candidates, row, id, metadataDeadline) {
                let metadata = safeWindowSelectionMetadata(true,
                    attribute(window, kAXRoleAttribute) as? String,
                    attribute(window, kAXSubroleAttribute) as? String,
                    windowBoolean(window, kAXMainAttribute),
                    snapshot.focused.map { CFEqual(window, $0) })
                if windowMetadataTimeRemaining(metadataDeadline) { metadataByID[id] = metadata }
            }
        }
    }
    // Icon rendering follows the bounded AX prepass; it cannot consume its budget.
    let windows = eligibleRows.compactMap { row -> [String: Any]? in
        guard let id = row[kCGWindowNumber as String] as? Int,
            let pid = row[kCGWindowOwnerPID as String] as? Int,
            let app = NSRunningApplication(processIdentifier: pid_t(pid)) else { return nil }
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
        var info: [String: Any] = ["icon": iconData, "kind": "window", "id": id, "pid": pid, "app": app.localizedName ?? "Uygulama", "title": row[kCGWindowName as String] as? String ?? "", "visible": row[kCGWindowIsOnscreen as String] as? Bool ?? false]
        if let metadata = metadataByID[id] {
            for (key, value) in metadata { info[key] = value }
        }
        return info
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
                var info: [String: Any] = ["role": attribute(entry.element, kAXRoleAttribute) as? String ?? "",
                    "title": attribute(entry.element, kAXTitleAttribute) as? String ?? "",
                    "ref": reference(entry, fingerprint, id, pid),
                    "actions": actions as? [String] ?? [], "can_set_value": settable.boolValue,
                    "unique": entries.count < 500 && entries.filter { $0.identity == entry.identity }.count == 1]
                for (key, label) in entry.actionLabels { info[key] = label }
                if let value = entry.displayValue {
                    info["value"] = value
                    info["value_source"] = "AXValue"
                    info["value_truncated"] = entry.displayValueTruncated
                }
                return info
            }
            emit(["ok": true, "elements": elements, "fingerprint": fingerprint, "id": id, "pid": Int(pid), "value_kinds": valueKindCounts(entries)])
        } else { fail("Arka plan değiştirme işlemi desteklenmiyor.") }
    }
} else { fail("Masaüstü hedefi geçersiz.") }
