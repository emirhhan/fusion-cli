"""`fusion -p` (Claude Code `--print`) yolunun kullanıcıya görünen metinleri.

Claude'un hata metni birebir korunması gereken yerlerde (betikler bu dizgeleri arar)
İngilizce özgün metin aynen tutulur; Fusion'ın kendi açıklamaları Türkçedir.
"""

from __future__ import annotations

#: Claude Code ile aynı metin (betikler bu dizgeyi arıyor).
PRINT_INVALID_JSON_SCHEMA = "Error: --json-schema is not a valid JSON Schema"
PRINT_STREAM_JSON_NEEDS_VERBOSE = (
    "Error: When using --print, --output-format=stream-json requires --verbose"
)
PRINT_INPUT_STREAM_NEEDS_OUTPUT_STREAM = (
    "Error: --input-format=stream-json requires output-format=stream-json."
)
PRINT_NO_PROMPT = (
    "Error: Input must be provided either through stdin or as a prompt argument when using --print"
)
PRINT_STDIN_TOO_LARGE = (
    "Hata: boru stdin girdisi {limit} MB sınırını aşıyor; daha küçük bir girdi verin."
)
PRINT_STDIN_UNREADABLE = "Uyarı: stdin okunamadı ({error}); yalnız argümandaki istemle sürüyor."
PRINT_UNKNOWN_INPUT_FORMAT = "Bilinmeyen girdi biçimi: {given}. Geçerli olanlar: text, stream-json"
PRINT_UNKNOWN_PERMISSION_MODE = (
    "Bilinmeyen izin kipi: {given}. Geçerli olanlar: "
    "default, acceptEdits, plan, auto, dontAsk, bypassPermissions, manual"
)
PRINT_UNKNOWN_PERMISSION_PROMPTS = (
    "Bilinmeyen --permission-prompts değeri: {given}. Geçerli: host, none"
)
PRINT_UNMAPPED_TOOLS = (
    "Uyarı: şu araç adlarının Fusion'da karşılığı yok, kural yalnız eşleşen çağrıya uygulanır: "
    "{names}"
)
PRINT_BG_WITH_PRINT = "Error: --bg cannot be used with --print"
PRINT_SESSION_ID_INVALID = "Error: Invalid session ID. Must be a valid UUID."
PRINT_SESSION_ID_CONFLICT = (
    "Error: --session-id can only be used with --continue or --resume if --fork-session is "
    "also specified."
)
PRINT_FILE_UNREADABLE = "Hata: {flag} dosyası okunamadı ({path}): {error}"
PRINT_SETTINGS_INVALID = "Hata: --settings okunamadı: {error}"
PRINT_MCP_CONFIG_INVALID = "Uyarı: --mcp-config girdisi atlandı ({source}): {error}"
PRINT_UNSUPPORTED_FLAG = "Uyarı: {flag} Fusion'da etkisiz; bayrak yok sayıldı."
PRINT_STREAM_LINE_INVALID = "Hata: stream-json girdisinde geçersiz satır: {error}"
PRINT_DEPRECATED_AGENT = (
    "Uyarı: `fusion agent` kullanımdan kalkıyor; Claude Code ile aynı kullanım `fusion -p` "
    '(ör. fusion -p "görev" --output-format json).'
)
PRINT_MODEL_UNRESOLVED = "Hata: --model çözülemedi: {error}"
PRINT_WAITING_BACKGROUND = "Waiting for background work to finish"
#: Tek tur sonunda başarısız yapısal çıktı için yeniden deneme talimatı.
PRINT_SCHEMA_RETRY = (
    "Önceki cevabın JSON şemasına uymadı: {errors}. Yalnız şemaya uyan tek bir JSON nesnesi yaz."
)
PRINT_SLASH_UNAVAILABLE = "/{name} isn't available in this environment."
PRINT_CONFIG_SESSION = "{path} = {value} — yalnız bu koşu için (kalıcı yazılmadı)"
PRINT_FROM_PR_INVALID = "Hata: --from-pr bir PR numarası ya da PR/MR adresi olmalı: {value}"
PRINT_FROM_PR_NONE = "Bu PR'a bağlı oturum bulunamadı: {value}"
SYSTEM_PROMPT_SNAPSHOT_INVALID = "Hata: --system-prompt-snapshot yalnız on ya da off alır: {given}"
PRINT_CONTROL_UNSUPPORTED = "Unsupported control request subtype: {subtype}"
PRINT_INTERRUPTED = "[Request interrupted by user]"
PRINT_SETTING_SOURCES_INVALID = (
    "Hata: --setting-sources geçersiz kaynak: {given}. Geçerli: user, project, local"
)
PRINT_PROMPT_TOOL_ERROR = "--permission-prompt-tool {tool}: {error} (istek reddedildi)"
PRINT_PROMPT_TOOL_MISSING = "onay aracı bulunamadı"
PRINT_DEBUG_FILE_FAILED = "Hata: --debug-file açılamadı ({path}): {error}"
PRINT_BYPASS_NOT_ALLOWED = (
    "bypassPermissions kipine geçilemez: koşu --dangerously-skip-permissions ya da "
    "--allow-dangerously-skip-permissions ile başlatılmadı."
)
PRINT_RESTRICTED_BYPASS = (
    "Hata: --restricted kipinde bypassPermissions kullanılamaz "
    "(--permission-mode bypassPermissions, --dangerously-skip-permissions ya da "
    "--settings permissions.defaultMode)."
)
PRINT_SUBAGENT_APPEND_CONFLICT = (
    "Error: --append-subagent-system-prompt and --append-subagent-system-prompt-file "
    "cannot be used together."
)
PRINT_MODEL_CURRENT = "Geçerli model: {model}"
PRINT_MODEL_SET = "Model ayarlandı: {model}"
PRINT_EFFORT_CURRENT = "Geçerli effort: {effort}"
PRINT_EFFORT_SET = "Effort ayarlandı: {effort}"
PRINT_MCP_ROW = "{name} ({transport}): {status}"
PRINT_MCP_CONFIGURED = "yapılandırıldı"
PRINT_MCP_FAILED = "yüklenemedi — {message}"
PRINT_MCP_NONE = "Yapılandırılmış MCP sunucusu yok."
