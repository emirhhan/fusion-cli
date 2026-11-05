use portable_pty::{native_pty_system, Child, CommandBuilder, MasterPty, PtySize};
use serde::Serialize;
use std::collections::HashMap;
#[cfg(test)]
use std::collections::HashSet;
use std::io::Write;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{mpsc, Arc, Condvar, Mutex};
use std::time::{Duration, Instant};

const OUTPUT_CHUNK_BYTES: usize = 8 * 1024;
const OUTPUT_QUEUE_CAPACITY: usize = 128;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct TerminalSnapshot {
    pub(crate) terminal_id: String,
    pub(crate) cwd: String,
    pub(crate) cols: u16,
    pub(crate) rows: u16,
    pub(crate) pid: Option<u32>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct TerminalOutput {
    pub(crate) terminal_id: String,
    pub(crate) data: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct TerminalClosed {
    pub(crate) terminal_id: String,
    pub(crate) reason: String,
    pub(crate) exit_code: Option<u32>,
}

type OutputSink = Arc<dyn Fn(TerminalOutput) + Send + Sync>;
type ClosedSink = Arc<dyn Fn(TerminalClosed) + Send + Sync>;
/// Tek bir terminalin ham bayt alıcısı (Tauri `Channel`, U4-25). Verilirse o terminalin çıktısı
/// `TerminalOutput` JSON olayı yerine doğrudan bu alıcıya, bayt dizisi olarak gider.
pub(crate) type RawOutputSink = Arc<dyn Fn(Vec<u8>) + Send + Sync>;

struct ManagedTerminal {
    master: Mutex<Option<Box<dyn MasterPty + Send>>>,
    writer: Mutex<Option<Box<dyn Write + Send>>>,
    child: Mutex<Option<Box<dyn Child + Send + Sync>>>,
    close_reason: Mutex<Option<String>>,
    close_queued: AtomicBool,
    events: mpsc::SyncSender<TerminalEvent>,
    close_delivered: Arc<(Mutex<bool>, Condvar)>,
}

type TerminalMap = Arc<Mutex<HashMap<String, Arc<ManagedTerminal>>>>;

enum TerminalEvent {
    Output(Vec<u8>),
    Closed {
        reason: String,
        exit_code: Option<u32>,
    },
}

pub(crate) struct TerminalManager {
    terminals: TerminalMap,
    next_id: AtomicU64,
    output_sink: OutputSink,
    closed_sink: ClosedSink,
    #[cfg(test)]
    exited_test_pids: Mutex<HashSet<u32>>,
}

impl TerminalManager {
    pub(crate) fn new(
        output: impl Fn(TerminalOutput) + Send + Sync + 'static,
        closed: impl Fn(TerminalClosed) + Send + Sync + 'static,
    ) -> Self {
        Self {
            terminals: Arc::new(Mutex::new(HashMap::new())),
            next_id: AtomicU64::new(1),
            output_sink: Arc::new(output),
            closed_sink: Arc::new(closed),
            #[cfg(test)]
            exited_test_pids: Mutex::new(HashSet::new()),
        }
    }

    pub(crate) fn open(
        &self,
        cwd: String,
        cols: u16,
        rows: u16,
    ) -> Result<TerminalSnapshot, String> {
        self.open_raw(cwd, cols, rows, None)
    }

    /// `raw` verilirse bu terminalin çıktısı yalnız ona gider (ham bayt, JSON sayı dizisi değil);
    /// verilmezse genel `output` olayı kullanılır (eski arayüzlerle uyum).
    pub(crate) fn open_raw(
        &self,
        cwd: String,
        cols: u16,
        rows: u16,
        raw: Option<RawOutputSink>,
    ) -> Result<TerminalSnapshot, String> {
        if cols == 0 || rows == 0 {
            return Err("terminal boyutu sıfır olamaz".into());
        }
        let cwd_path = std::path::Path::new(&cwd);
        if !cwd_path.is_dir() {
            return Err(format!("çalışma dizini bulunamadı: {cwd}"));
        }
        ensure_terminal_capacity(self.terminals.lock().unwrap().len())?;

        let size = PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        };
        let (pair, child) = spawn_shell(size, cwd_path)?;
        let pid = child.process_id();
        let reader = pair
            .master
            .try_clone_reader()
            .map_err(|error| format!("terminal çıktısı alınamadı: {error}"))?;
        let writer = pair
            .master
            .take_writer()
            .map_err(|error| format!("terminal girdisi alınamadı: {error}"))?;
        let terminal_id = format!("terminal-{}", self.next_id.fetch_add(1, Ordering::Relaxed));
        let close_delivered = Arc::new((Mutex::new(false), Condvar::new()));
        let output_sink: OutputSink = match raw {
            Some(raw) => Arc::new(move |event: TerminalOutput| raw(event.data)),
            None => Arc::clone(&self.output_sink),
        };
        let events = event_worker(
            terminal_id.clone(),
            output_sink,
            Arc::clone(&self.closed_sink),
            Arc::clone(&close_delivered),
        );
        let terminal = Arc::new(ManagedTerminal {
            master: Mutex::new(Some(pair.master)),
            writer: Mutex::new(Some(writer)),
            child: Mutex::new(Some(child)),
            close_reason: Mutex::new(None),
            close_queued: AtomicBool::new(false),
            events,
            close_delivered,
        });
        self.terminals
            .lock()
            .unwrap()
            .insert(terminal_id.clone(), Arc::clone(&terminal));
        forward_output(
            terminal_id.clone(),
            reader,
            Arc::clone(&self.terminals),
            terminal,
        );

        Ok(TerminalSnapshot {
            terminal_id,
            cwd,
            cols,
            rows,
            pid,
        })
    }

    pub(crate) fn write(&self, id: &str, data: Vec<u8>) -> Result<(), String> {
        let terminal = self.terminal(id)?;
        let mut writer = terminal.writer.lock().unwrap();
        let writer = writer.as_mut().ok_or("terminal bulunamadı")?;
        writer
            .write_all(&data)
            .and_then(|_| writer.flush())
            .map_err(|error| format!("terminale yazılamadı: {error}"))
    }

    pub(crate) fn resize(&self, id: &str, cols: u16, rows: u16) -> Result<(), String> {
        if cols == 0 || rows == 0 {
            return Err("terminal boyutu sıfır olamaz".into());
        }
        let terminal = self.terminal(id)?;
        let master = terminal.master.lock().unwrap();
        master
            .as_ref()
            .ok_or("terminal bulunamadı")?
            .resize(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .map_err(|error| format!("terminal boyutlandırılamadı: {error}"))
    }

    pub(crate) fn close(&self, id: &str) -> Result<(), String> {
        let terminal = claim_explicit_terminal(&mut self.terminals.lock().unwrap(), id)
            .ok_or("terminal bulunamadı")?;
        #[cfg(test)]
        let pid = terminal
            .child
            .lock()
            .unwrap()
            .as_ref()
            .and_then(|child| child.process_id());
        let close_result = close_terminal(terminal);
        #[cfg(test)]
        if close_result.is_ok() {
            if let Some(pid) = pid {
                self.exited_test_pids.lock().unwrap().insert(pid);
            }
        }
        let _ = close_result;
        Ok(())
    }

    pub(crate) fn close_all(&self) {
        let terminals: Vec<_> = {
            let mut terminals = self.terminals.lock().unwrap();
            for terminal in terminals.values() {
                claim_explicit_reason(terminal);
            }
            terminals.drain().collect()
        };
        // Signal every owned child before waiting for any child or UI callback.
        let closing: Vec<_> = terminals
            .into_iter()
            .map(|(_, terminal)| {
                let mut child = terminal.child.lock().unwrap().take();
                let kill_result = child
                    .as_mut()
                    .map_or(Ok(()), |child| match child.try_wait() {
                        Ok(Some(_)) => Ok(()),
                        Ok(None) => child.kill(),
                        Err(error) => Err(error),
                    });
                (terminal, child, kill_result)
            })
            .collect();
        let delivery_deadline =
            Instant::now() + KAPANIS_TESLIM_ZAMAN_ASIMI + KAPANIS_ZORLA_TESLIM_ZAMAN_ASIMI;
        let mut delivering = Vec::new();
        for (terminal, child, kill_result) in closing {
            #[cfg(test)]
            let pid = child.as_ref().and_then(|child| child.process_id());
            let wait_result = match child {
                Some(mut child) => child.wait().map(|_| ()),
                None => Ok(()),
            };
            let close_result = kill_result.and(wait_result);
            terminal.writer.lock().unwrap().take();
            terminal.master.lock().unwrap().take();
            #[cfg(test)]
            if close_result.is_ok() {
                if let Some(pid) = pid {
                    self.exited_test_pids.lock().unwrap().insert(pid);
                }
            }
            let _ = close_result;
            delivering.push(terminal);
        }
        for terminal in delivering {
            wait_for_close_delivery_until(&terminal, delivery_deadline);
        }
    }

    fn terminal(&self, id: &str) -> Result<Arc<ManagedTerminal>, String> {
        self.terminals
            .lock()
            .unwrap()
            .get(id)
            .cloned()
            .ok_or_else(|| "terminal bulunamadı".into())
    }

    #[cfg(test)]
    pub(crate) fn test_is_running(&self, id: &str) -> bool {
        self.terminals
            .lock()
            .unwrap()
            .get(id)
            .and_then(|terminal| {
                let mut child = terminal.child.lock().unwrap();
                child
                    .as_mut()
                    .map(|child| matches!(child.try_wait(), Ok(None)))
            })
            .unwrap_or(false)
    }

    #[cfg(test)]
    pub(crate) fn test_has_exited(&self, pid: u32) -> bool {
        self.exited_test_pids.lock().unwrap().contains(&pid)
    }
}

fn claim_explicit_terminal(
    terminals: &mut HashMap<String, Arc<ManagedTerminal>>,
    id: &str,
) -> Option<Arc<ManagedTerminal>> {
    let terminal = terminals.get(id)?.clone();
    claim_explicit_reason(&terminal);
    terminals.remove(id)
}

fn claim_explicit_reason(terminal: &ManagedTerminal) {
    *terminal.close_reason.lock().unwrap() = Some("kullanıcı kapattı".into());
}

fn close_terminal(terminal: Arc<ManagedTerminal>) -> std::io::Result<Option<u32>> {
    let wait_result = wait_for_child(&terminal, true);
    terminal.writer.lock().unwrap().take();
    terminal.master.lock().unwrap().take();
    wait_for_close_delivery(&terminal);
    wait_result
}

fn wait_for_child(terminal: &ManagedTerminal, kill: bool) -> std::io::Result<Option<u32>> {
    let child = terminal.child.lock().unwrap().take();
    if let Some(mut child) = child {
        let kill_error = kill.then(|| child.kill()).and_then(Result::err);
        let wait_result = child.wait().map(|status| Some(status.exit_code()));
        if let Some(error) = kill_error {
            return Err(error);
        }
        return wait_result;
    }
    Ok(None)
}

fn queue_closed_once(terminal: &ManagedTerminal, exit_code: Option<u32>) {
    if terminal.close_queued.swap(true, Ordering::AcqRel) {
        return;
    }
    let reason = terminal
        .close_reason
        .lock()
        .unwrap()
        .take()
        .unwrap_or_else(|| "süreç kapandı".into());
    let _ = terminal
        .events
        .send(TerminalEvent::Closed { reason, exit_code });
}

/// Kapanış olayının doğal yoldan (okuyucu iş parçacığı) kuyruğa girmesi için
/// beklenen en uzun süre.
const KAPANIS_TESLIM_ZAMAN_ASIMI: Duration = Duration::from_millis(1500);

/// Olayı kendimiz kuyruğa koyduktan sonra işleyicinin teslim etmesi için ek süre.
const KAPANIS_ZORLA_TESLIM_ZAMAN_ASIMI: Duration = Duration::from_millis(500);

/// Kapanış olayının teslim edilmesini sınırlı süre bekler. Okuyucu iş parçacığı
/// pty'yi elinde tutan bir torun süreç yüzünden bitmezse olay hiç kuyruğa
/// girmez; zaman aşımsız beklemek `close`'u (ve uygulama kapanışını) sonsuza dek
/// kilitliyordu (R2-03). Süre dolarsa olayı biz kuyruğa koyarız; ikinci bekleme
/// de dolarsa vazgeçilir.
fn wait_for_close_delivery(terminal: &ManagedTerminal) {
    wait_for_close_delivery_until(
        terminal,
        Instant::now() + KAPANIS_TESLIM_ZAMAN_ASIMI + KAPANIS_ZORLA_TESLIM_ZAMAN_ASIMI,
    );
}

fn wait_for_close_delivery_until(terminal: &ManagedTerminal, deadline: Instant) {
    let remaining = deadline.saturating_duration_since(Instant::now());
    if bekle_teslim(terminal, KAPANIS_TESLIM_ZAMAN_ASIMI.min(remaining)) {
        return;
    }
    queue_closed_once(terminal, None);
    let remaining = deadline.saturating_duration_since(Instant::now());
    bekle_teslim(terminal, KAPANIS_ZORLA_TESLIM_ZAMAN_ASIMI.min(remaining));
}

fn bekle_teslim(terminal: &ManagedTerminal, sure: Duration) -> bool {
    let (delivered, wake) = &*terminal.close_delivered;
    let guard = delivered.lock().unwrap();
    let (guard, _) = wake
        .wait_timeout_while(guard, sure, |teslim_edildi| !*teslim_edildi)
        .unwrap();
    *guard
}

fn event_worker(
    id: String,
    output_sink: OutputSink,
    closed_sink: ClosedSink,
    close_delivered: Arc<(Mutex<bool>, Condvar)>,
) -> mpsc::SyncSender<TerminalEvent> {
    let (sender, receiver) = mpsc::sync_channel(OUTPUT_QUEUE_CAPACITY);
    std::thread::spawn(move || {
        while let Ok(event) = receiver.recv() {
            match event {
                TerminalEvent::Output(data) => output_sink(TerminalOutput {
                    terminal_id: id.clone(),
                    data,
                }),
                TerminalEvent::Closed { reason, exit_code } => {
                    closed_sink(TerminalClosed {
                        terminal_id: id,
                        reason,
                        exit_code,
                    });
                    let (delivered, wake) = &*close_delivered;
                    *delivered.lock().unwrap() = true;
                    wake.notify_all();
                    break;
                }
            }
        }
    });
    sender
}

fn forward_output(
    id: String,
    mut reader: Box<dyn std::io::Read + Send>,
    terminals: TerminalMap,
    terminal: Arc<ManagedTerminal>,
) {
    std::thread::spawn(move || {
        let mut buffer = vec![0; OUTPUT_CHUNK_BYTES];
        loop {
            match reader.read(&mut buffer) {
                Ok(0) | Err(_) => break,
                Ok(count) => {
                    if terminal
                        .events
                        .send(TerminalEvent::Output(buffer[..count].to_vec()))
                        .is_err()
                    {
                        break;
                    }
                }
            }
        }
        let removed = terminals.lock().unwrap().remove(&id);
        if removed.is_some() {
            let exit_code = wait_for_child(&terminal, false).ok().flatten();
            terminal.writer.lock().unwrap().take();
            terminal.master.lock().unwrap().take();
            queue_closed_once(&terminal, exit_code);
        } else {
            queue_closed_once(&terminal, None);
        }
    });
}

fn spawn_shell(
    size: PtySize,
    cwd: &std::path::Path,
) -> Result<(portable_pty::PtyPair, Box<dyn Child + Send + Sync>), String> {
    let mut errors = Vec::new();
    for shell in shell_candidates() {
        let pair = native_pty_system()
            .openpty(size)
            .map_err(|error| format!("PTY açılamadı: {error}"))?;
        let mut command = CommandBuilder::new(&shell);
        command.cwd(cwd);
        apply_shell_args(&mut command);
        apply_terminal_env(&mut command);
        match pair.slave.spawn_command(command) {
            Ok(child) => return Ok((pair, child)),
            Err(error) => errors.push(format!("{shell}: {error}")),
        }
    }
    Err(format!(
        "etkileşimli kabuk başlatılamadı: {}",
        errors.join("; ")
    ))
}

/// Kabuk GİRİŞ (login) kabuğu olarak açılır (Terminal.app ile aynı): Homebrew'in `shellenv`'i
/// ve nvm/pyenv gibi PATH eklemeleri çoğunlukla `~/.zprofile`'dadır ve yalnız giriş
/// kabuğunda okunur. GUI uygulaması minimal PATH ile açıldığından etkileşimli ama girişsiz
/// kabukta `git`/`node`/`python` görünmüyordu (R2-15). Windows kabukları `-l` bilmez.
fn apply_shell_args(command: &mut CommandBuilder) {
    if cfg!(unix) {
        command.arg("-l");
    }
}

/// Ham bayt girdisinin hangi terminale gittiğini taşıyan istek başlığı (U4-25).
pub(crate) const TERMINAL_KIMLIK_BASLIGI: &str = "x-terminal-id";

/// `terminal_yaz` isteğinden (terminal kimliği, bayt) çıkarır.
///
/// Yeni arayüz gövdede HAM bayt gönderir, kimliği başlıkta taşır: JSON sayı dizisi her bayt için
/// birkaç karakter ve bir ayrıştırma turu demekti. Eski biçim (`{terminalId, data:[..]}` JSON)
/// kabul edilmeye devam eder; böylece arayüz ve çekirdek ayrı sürümde kalsa da yazma bozulmaz.
pub(crate) fn girdi_coz(
    body: &tauri::ipc::InvokeBody,
    headers: &tauri::http::HeaderMap,
) -> Result<(String, Vec<u8>), String> {
    match body {
        tauri::ipc::InvokeBody::Raw(bytes) => {
            let id = headers
                .get(TERMINAL_KIMLIK_BASLIGI)
                .and_then(|value| value.to_str().ok())
                .filter(|value| !value.is_empty())
                .ok_or("terminal kimliği başlığı eksik")?;
            Ok((id.to_owned(), bytes.clone()))
        }
        tauri::ipc::InvokeBody::Json(value) => {
            #[derive(serde::Deserialize)]
            #[serde(rename_all = "camelCase")]
            struct EskiGirdi {
                terminal_id: String,
                data: Vec<u8>,
            }
            let girdi: EskiGirdi = serde_json::from_value(value.clone())
                .map_err(|error| format!("terminal girdisi çözülemedi: {error}"))?;
            Ok((girdi.terminal_id, girdi.data))
        }
    }
}

/// Aynı anda açık terminal sayısı üst sınırı; sınırsız açılış PTY/dosya tanıtıcısı tüketirdi.
const MAX_TERMINALS: usize = 16;

fn ensure_terminal_capacity(open: usize) -> Result<(), String> {
    if open >= MAX_TERMINALS {
        return Err(format!(
            "en fazla {MAX_TERMINALS} terminal açılabilir; birini kapatıp yeniden dene"
        ));
    }
    Ok(())
}

/// Fusion Dock'tan açıldığında ortamda `TERM` yoktur; kabuk ekran türünü
/// bilmeyince `clear`, `vim`, `top` çalışmaz ("TERM environment variable not
/// set"). Terminal görünümü xterm.js'tir ve 256 renk ile gerçek rengi destekler.
fn apply_terminal_env(command: &mut CommandBuilder) {
    command.env("TERM", "xterm-256color");
    command.env("COLORTERM", "truecolor");
}

#[cfg(unix)]
fn shell_candidates() -> Vec<String> {
    let shell = std::env::var("SHELL")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "/bin/sh".into());
    if shell == "/bin/sh" {
        vec![shell]
    } else {
        vec![shell, "/bin/sh".into()]
    }
}

#[cfg(windows)]
fn shell_candidates() -> Vec<String> {
    vec!["powershell.exe".into(), "cmd.exe".into()]
}

#[cfg(test)]
mod tests {
    use super::{
        claim_explicit_terminal, close_terminal, event_worker, forward_output, queue_closed_once,
        wait_for_child, ManagedTerminal, TerminalClosed, TerminalManager, TerminalMap,
        TerminalOutput,
    };
    use portable_pty::{
        native_pty_system, Child, ChildKiller, CommandBuilder, ExitStatus, PtySize,
    };
    use std::io;
    use std::io::Write;
    use std::path::Path;
    use std::sync::atomic::AtomicBool;
    use std::sync::{mpsc, Arc, Condvar, Mutex, MutexGuard, OnceLock};
    use std::time::{Duration, Instant};

    #[test]
    fn kabuk_ekran_turunu_bilir_clear_calisir() {
        let mut command = CommandBuilder::new("/bin/sh");
        super::apply_terminal_env(&mut command);
        assert_eq!(command.get_env("TERM").unwrap(), "xterm-256color");
        assert_eq!(command.get_env("COLORTERM").unwrap(), "truecolor");
    }

    /// Ölçüldü (30 Ekim): kabuk giriş kabuğu değildi; `~/.zprofile`'daki PATH (Homebrew) görünmüyordu.
    #[cfg(unix)]
    #[test]
    fn kabuk_giris_kabugu_olarak_acilir() {
        let mut command = CommandBuilder::new("/bin/sh");
        super::apply_shell_args(&mut command);
        let args: Vec<_> = command
            .get_argv()
            .iter()
            .map(|item| item.to_string_lossy().into_owned())
            .collect();
        assert_eq!(args, vec!["/bin/sh", "-l"]);
    }

    /// Ölçüldü (30 Ekim): çıktı `terminal://cikti` olayında JSON sayı dizisiydi; kanalla ham bayt gider.
    #[test]
    fn ham_kanal_verilirse_cikti_genel_olaya_degil_kanala_gider() {
        let _guard = pty_test_guard();
        let cwd = tempfile::tempdir().unwrap();
        let (manager, outputs, _) = manager();
        let alinan = Arc::new(Mutex::new(Vec::<u8>::new()));
        let alinan_kopya = Arc::clone(&alinan);
        let snapshot = manager
            .open_raw(
                cwd.path().to_string_lossy().into_owned(),
                80,
                24,
                Some(Arc::new(move |bytes| {
                    alinan_kopya.lock().unwrap().extend(bytes);
                })),
            )
            .unwrap();
        manager
            .write(&snapshot.terminal_id, print_command("fusion-raw-kanal"))
            .unwrap();
        let bitis = Instant::now() + Duration::from_secs(5);
        let needle = b"fusion-raw-kanal";
        while !alinan
            .lock()
            .unwrap()
            .windows(needle.len())
            .any(|pencere| pencere == needle)
        {
            assert!(Instant::now() < bitis, "kanal çıktıyı almadı");
            std::thread::sleep(Duration::from_millis(20));
        }
        assert!(
            outputs.lock().unwrap().is_empty(),
            "ham kanal varken genel olay da gitmemeli"
        );
        manager.close_all();
    }

    #[test]
    fn girdi_ham_govdede_kimlik_basliktan_okunur() {
        let mut basliklar = tauri::http::HeaderMap::new();
        basliklar.insert(
            super::TERMINAL_KIMLIK_BASLIGI,
            "terminal-7".parse().unwrap(),
        );
        let (id, bayt) =
            super::girdi_coz(&tauri::ipc::InvokeBody::Raw(vec![3, 10, 0xff]), &basliklar).unwrap();
        assert_eq!(id, "terminal-7");
        assert_eq!(bayt, vec![3, 10, 0xff]);
    }

    #[test]
    fn girdi_ham_govdede_baslik_yoksa_reddedilir() {
        let hata = super::girdi_coz(
            &tauri::ipc::InvokeBody::Raw(vec![1]),
            &tauri::http::HeaderMap::new(),
        )
        .unwrap_err();
        assert!(hata.contains("başlığı eksik"));
    }

    #[test]
    fn girdi_eski_json_bicimi_hala_kabul_edilir() {
        let govde = tauri::ipc::InvokeBody::Json(serde_json::json!({
            "terminalId": "terminal-2", "data": [104, 105]
        }));
        let (id, bayt) = super::girdi_coz(&govde, &tauri::http::HeaderMap::new()).unwrap();
        assert_eq!(id, "terminal-2");
        assert_eq!(bayt, b"hi".to_vec());
        assert!(super::girdi_coz(
            &tauri::ipc::InvokeBody::Json(serde_json::json!({"x": 1})),
            &tauri::http::HeaderMap::new()
        )
        .is_err());
    }

    #[test]
    fn terminal_sayisi_ust_sinirla_kisitlanir() {
        assert!(super::ensure_terminal_capacity(0).is_ok());
        assert!(super::ensure_terminal_capacity(super::MAX_TERMINALS - 1).is_ok());
        assert!(super::ensure_terminal_capacity(super::MAX_TERMINALS)
            .unwrap_err()
            .contains("en fazla"));
    }

    type OutputLog = Arc<Mutex<Vec<TerminalOutput>>>;
    type ClosedLog = Arc<Mutex<Vec<TerminalClosed>>>;

    fn pty_test_guard() -> MutexGuard<'static, ()> {
        static PTY_TEST_LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        // Zehirlenme YUTULUR, çünkü bu kilit veri değil SIRA korur.
        //
        // Ölçüldü (Windows CI): tek bir zamanlama assert'i kilidi tutarken
        // paniklediğinde diğer dokuz test `PoisonError` ile düştü ve çıktı "10
        // başarısız test" dedi. Gerçek arıza BİRDİ; dokuzu gürültüydü ve asıl
        // sebebi gizliyordu. Kilit yalnız PTY testlerinin üst üste binmesini
        // engeller; içinde korunan bir durum yok, bu yüzden zehirli kilidi
        // devralmak güvenlidir.
        PTY_TEST_LOCK
            .get_or_init(|| Mutex::new(()))
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    fn manager() -> (TerminalManager, OutputLog, ClosedLog) {
        let outputs = OutputLog::default();
        let closed = ClosedLog::default();
        let output_log = Arc::clone(&outputs);
        let closed_log = Arc::clone(&closed);
        let manager = TerminalManager::new(
            move |event| output_log.lock().unwrap().push(event),
            move |event| closed_log.lock().unwrap().push(event),
        );
        (manager, outputs, closed)
    }

    fn wait_for_output(outputs: &OutputLog, id: &str, needle: &[u8]) {
        let deadline = Instant::now() + Duration::from_secs(5);
        loop {
            let bytes: Vec<u8> = outputs
                .lock()
                .unwrap()
                .iter()
                .filter(|event| event.terminal_id == id)
                .flat_map(|event| event.data.iter().copied())
                .collect();
            if bytes.windows(needle.len()).any(|window| window == needle) {
                return;
            }
            assert!(
                Instant::now() < deadline,
                "PTY output did not contain {needle:?}; got {bytes:?}"
            );
            std::thread::sleep(Duration::from_millis(20));
        }
    }

    fn wait_for_closed(closed: &ClosedLog, id: &str) -> TerminalClosed {
        let deadline = Instant::now() + Duration::from_secs(5);
        loop {
            if let Some(event) = closed
                .lock()
                .unwrap()
                .iter()
                .find(|event| event.terminal_id == id)
                .cloned()
            {
                return event;
            }
            assert!(
                Instant::now() < deadline,
                "PTY close event was not delivered"
            );
            std::thread::sleep(Duration::from_millis(20));
        }
    }

    #[cfg(unix)]
    fn print_command(text: &str) -> Vec<u8> {
        format!("printf '{text}\\n'\n").into_bytes()
    }

    #[cfg(windows)]
    fn print_command(text: &str) -> Vec<u8> {
        format!("Write-Output '{text}'\r\n").into_bytes()
    }

    #[test]
    fn opens_an_interactive_pty_in_the_requested_working_directory() {
        let _guard = pty_test_guard();
        let cwd = tempfile::tempdir().unwrap();
        let marker = cwd.path().join("fusion-cwd-marker");
        std::fs::write(&marker, b"").unwrap();
        let (manager, outputs, _) = manager();

        let snapshot = manager
            .open(cwd.path().to_string_lossy().into_owned(), 80, 24)
            .unwrap();
        for _ in 0..25 {
            #[cfg(unix)]
            manager
                .write(&snapshot.terminal_id, b"pwd\n".to_vec())
                .unwrap();
            #[cfg(windows)]
            manager
                .write(&snapshot.terminal_id, b"Get-Location\r\n".to_vec())
                .unwrap();
            let has_cwd = outputs
                .lock()
                .unwrap()
                .iter()
                .filter(|event| event.terminal_id == snapshot.terminal_id)
                .flat_map(|event| event.data.iter().copied())
                .collect::<Vec<_>>()
                .windows(cwd.path().to_string_lossy().len())
                .any(|window| window == cwd.path().to_string_lossy().as_bytes());
            if has_cwd {
                break;
            }
            std::thread::sleep(Duration::from_millis(100));
        }

        wait_for_output(
            &outputs,
            &snapshot.terminal_id,
            cwd.path().to_string_lossy().as_bytes(),
        );
        assert_eq!(Path::new(&snapshot.cwd), cwd.path());
        manager.close_all();
    }

    #[test]
    fn forwards_terminal_output_without_stripping_ansi_bytes() {
        let _guard = pty_test_guard();
        let pair = native_pty_system().openpty(PtySize::default()).unwrap();
        let mut command = CommandBuilder::new(std::env::current_exe().unwrap());
        command.args([
            "--exact",
            "terminal::tests::terminal_test_helper",
            "--ignored",
            "--nocapture",
        ]);
        let child = pair.slave.spawn_command(command).unwrap();
        let reader = pair.master.try_clone_reader().unwrap();
        let writer = pair.master.take_writer().unwrap();
        let outputs = OutputLog::default();
        let output_log = Arc::clone(&outputs);
        let close_delivered = Arc::new((Mutex::new(false), Condvar::new()));
        let events = event_worker(
            "raw-byte-helper".into(),
            Arc::new(move |event| output_log.lock().unwrap().push(event)),
            Arc::new(|_| {}),
            Arc::clone(&close_delivered),
        );
        let terminal = Arc::new(ManagedTerminal {
            master: Mutex::new(Some(pair.master)),
            writer: Mutex::new(Some(writer)),
            child: Mutex::new(Some(child)),
            close_reason: Mutex::new(None),
            close_queued: AtomicBool::new(false),
            events,
            close_delivered,
        });
        let terminals = TerminalMap::default();
        terminals
            .lock()
            .unwrap()
            .insert("raw-byte-helper".into(), Arc::clone(&terminal));
        forward_output("raw-byte-helper".into(), reader, terminals, terminal);

        wait_for_output(&outputs, "raw-byte-helper", b"\x1b[31mfusion-pty-ok\x1b[0m");
    }

    #[test]
    fn cleanup_liveness_is_false_for_a_naturally_exited_but_registered_child() {
        let _guard = pty_test_guard();
        let pair = native_pty_system().openpty(PtySize::default()).unwrap();
        #[cfg(unix)]
        let command = CommandBuilder::new("/usr/bin/true");
        #[cfg(windows)]
        let command = {
            let mut command = CommandBuilder::new("cmd.exe");
            command.args(["/C", "exit", "0"]);
            command
        };
        let child = pair.slave.spawn_command(command).unwrap();
        let writer = pair.master.take_writer().unwrap();
        let close_delivered = Arc::new((Mutex::new(false), Condvar::new()));
        let events = event_worker(
            "exited-still-registered".into(),
            Arc::new(|_| {}),
            Arc::new(|_| {}),
            Arc::clone(&close_delivered),
        );
        let terminal = Arc::new(ManagedTerminal {
            master: Mutex::new(Some(pair.master)),
            writer: Mutex::new(Some(writer)),
            child: Mutex::new(Some(child)),
            close_reason: Mutex::new(None),
            close_queued: AtomicBool::new(false),
            events,
            close_delivered,
        });
        let manager = TerminalManager::new(|_| {}, |_| {});
        manager
            .terminals
            .lock()
            .unwrap()
            .insert("exited-still-registered".into(), Arc::clone(&terminal));
        let deadline = Instant::now() + Duration::from_secs(2);

        while manager.test_is_running("exited-still-registered") && Instant::now() < deadline {
            std::thread::yield_now();
        }

        assert!(!manager.test_is_running("exited-still-registered"));
        manager.terminals.lock().unwrap().clear();
        terminal.child.lock().unwrap().take();
    }

    /// Ölçüldü (30 Ekim): okuyucu iş parçacığı hiç bitmezse (pty'yi elinde tutan
    /// torun süreç) kapanış olayı kuyruğa girmiyor, `close` zaman aşımsız
    /// Condvar'da sonsuza dek bekliyordu (R2-03).
    #[test]
    fn kapanis_olayi_gelmeyen_terminalde_close_zaman_asimiyla_doner() {
        let kapanislar = Arc::new(Mutex::new(Vec::new()));
        let kayit = Arc::clone(&kapanislar);
        let close_delivered = Arc::new((Mutex::new(false), Condvar::new()));
        let events = event_worker(
            "okuyucu-takili".into(),
            Arc::new(|_| {}),
            Arc::new(move |kapanis| kayit.lock().unwrap().push(kapanis)),
            Arc::clone(&close_delivered),
        );
        let terminal = Arc::new(ManagedTerminal {
            master: Mutex::new(None),
            writer: Mutex::new(None),
            child: Mutex::new(None),
            close_reason: Mutex::new(Some("kullanıcı kapattı".into())),
            close_queued: AtomicBool::new(false),
            events,
            close_delivered,
        });
        let (bitti, bekle) = mpsc::channel();
        let kopya = Arc::clone(&terminal);
        std::thread::spawn(move || {
            let _ = close_terminal(kopya);
            let _ = bitti.send(());
        });

        assert!(
            bekle.recv_timeout(Duration::from_secs(5)).is_ok(),
            "close 5 sn içinde dönmedi"
        );
        let kapanislar = kapanislar.lock().unwrap();
        assert_eq!(kapanislar.len(), 1);
        assert_eq!(kapanislar[0].reason, "kullanıcı kapattı");
    }

    #[derive(Debug)]
    struct FailedChild {
        pid: u32,
        kill_fails: bool,
        wait_fails: bool,
    }

    impl ChildKiller for FailedChild {
        fn kill(&mut self) -> io::Result<()> {
            if self.kill_fails {
                Err(io::Error::other("deterministic kill failure"))
            } else {
                Ok(())
            }
        }

        fn clone_killer(&self) -> Box<dyn ChildKiller + Send + Sync> {
            Box::new(Self {
                pid: self.pid,
                kill_fails: self.kill_fails,
                wait_fails: self.wait_fails,
            })
        }
    }

    impl Child for FailedChild {
        fn try_wait(&mut self) -> io::Result<Option<ExitStatus>> {
            Ok(None)
        }

        fn wait(&mut self) -> io::Result<ExitStatus> {
            if self.wait_fails {
                Err(io::Error::other("deterministic wait failure"))
            } else {
                Ok(ExitStatus::with_exit_code(0))
            }
        }

        fn process_id(&self) -> Option<u32> {
            Some(self.pid)
        }

        #[cfg(windows)]
        fn as_raw_handle(&self) -> Option<std::os::windows::io::RawHandle> {
            None
        }
    }

    fn assert_failed_cleanup_is_not_recorded(child: FailedChild) {
        let (manager, _, _) = manager();
        let pid = child.pid;
        let close_delivered = Arc::new((Mutex::new(false), Condvar::new()));
        let events = event_worker(
            "failed-wait".into(),
            Arc::new(|_| {}),
            Arc::new(|_| {}),
            Arc::clone(&close_delivered),
        );
        let terminal = Arc::new(ManagedTerminal {
            master: Mutex::new(None),
            writer: Mutex::new(None),
            child: Mutex::new(Some(Box::new(child))),
            close_reason: Mutex::new(None),
            close_queued: AtomicBool::new(false),
            events,
            close_delivered,
        });
        manager
            .terminals
            .lock()
            .unwrap()
            .insert("failed-wait".into(), Arc::clone(&terminal));
        queue_closed_once(&terminal, None);

        manager.close_all();

        assert!(!manager.test_has_exited(pid));
    }

    #[test]
    fn failed_child_wait_is_not_recorded_as_a_successful_exit() {
        assert_failed_cleanup_is_not_recorded(FailedChild {
            pid: 424_242,
            kill_fails: false,
            wait_fails: true,
        });
    }

    #[test]
    fn failed_child_kill_is_not_recorded_as_a_successful_exit() {
        assert_failed_cleanup_is_not_recorded(FailedChild {
            pid: 424_243,
            kill_fails: true,
            wait_fails: false,
        });
    }

    #[test]
    #[ignore]
    fn terminal_test_helper() {
        std::io::stdout()
            .write_all(b"\x1b[31mfusion-pty-ok\x1b[0m")
            .unwrap();
        std::io::stdout().flush().unwrap();
    }

    #[test]
    fn explicit_reason_is_claimed_before_reader_can_observe_map_removal() {
        let _guard = pty_test_guard();
        let cwd = tempfile::tempdir().unwrap();
        let (manager, _, closed) = manager();
        let snapshot = manager
            .open(cwd.path().to_string_lossy().into_owned(), 80, 24)
            .unwrap();

        let terminal = {
            let mut terminals = manager.terminals.lock().unwrap();
            claim_explicit_terminal(&mut terminals, &snapshot.terminal_id).unwrap()
        };
        assert!(!manager
            .terminals
            .lock()
            .unwrap()
            .contains_key(&snapshot.terminal_id));

        queue_closed_once(&terminal, None);
        let deadline = Instant::now() + Duration::from_secs(1);
        loop {
            let reasons: Vec<_> = closed
                .lock()
                .unwrap()
                .iter()
                .map(|event| event.reason.clone())
                .collect();
            if !reasons.is_empty() {
                assert_eq!(reasons, ["kullanıcı kapattı"]);
                break;
            }
            assert!(
                Instant::now() < deadline,
                "reader-side close event was not delivered"
            );
            std::thread::sleep(Duration::from_millis(10));
        }

        let _ = wait_for_child(&terminal, true);
        terminal.writer.lock().unwrap().take();
        terminal.master.lock().unwrap().take();
    }

    #[test]
    fn natural_shell_exit_reports_its_portable_pty_exit_code() {
        let _guard = pty_test_guard();
        let cwd = tempfile::tempdir().unwrap();
        let (manager, _, closed) = manager();
        let snapshot = manager
            .open(cwd.path().to_string_lossy().into_owned(), 80, 24)
            .unwrap();

        #[cfg(unix)]
        manager
            .write(&snapshot.terminal_id, b"exit 1\n".to_vec())
            .unwrap();
        #[cfg(windows)]
        manager
            .write(&snapshot.terminal_id, b"exit 1\r\n".to_vec())
            .unwrap();

        let event = wait_for_closed(&closed, &snapshot.terminal_id);
        assert_eq!(event.exit_code, Some(1));
    }

    #[test]
    fn explicit_close_does_not_report_a_process_exit_code() {
        let _guard = pty_test_guard();
        let cwd = tempfile::tempdir().unwrap();
        let (manager, _, closed) = manager();
        let snapshot = manager
            .open(cwd.path().to_string_lossy().into_owned(), 80, 24)
            .unwrap();

        manager.close(&snapshot.terminal_id).unwrap();

        let event = wait_for_closed(&closed, &snapshot.terminal_id);
        assert_eq!(event.reason, "kullanıcı kapattı");
        assert_eq!(event.exit_code, None);
    }

    struct BlockingWriter {
        entered: mpsc::SyncSender<()>,
        release: mpsc::Receiver<()>,
        inner: Box<dyn Write + Send>,
    }

    impl Write for BlockingWriter {
        fn write(&mut self, buffer: &[u8]) -> std::io::Result<usize> {
            self.entered.send(()).unwrap();
            self.release.recv().unwrap();
            self.inner.write(buffer)
        }

        fn flush(&mut self) -> std::io::Result<()> {
            self.inner.flush()
        }
    }

    #[test]
    fn blocked_write_on_one_terminal_does_not_block_another_terminal_resize() {
        let _guard = pty_test_guard();
        let first_cwd = tempfile::tempdir().unwrap();
        let second_cwd = tempfile::tempdir().unwrap();
        let (manager, _, _) = manager();
        let manager = Arc::new(manager);
        let first = manager
            .open(first_cwd.path().to_string_lossy().into_owned(), 80, 24)
            .unwrap();
        let second = manager
            .open(second_cwd.path().to_string_lossy().into_owned(), 80, 24)
            .unwrap();
        let (entered_tx, entered_rx) = mpsc::sync_channel(0);
        let (release_tx, release_rx) = mpsc::sync_channel(0);
        let first_terminal = manager
            .terminals
            .lock()
            .unwrap()
            .get(&first.terminal_id)
            .unwrap()
            .clone();
        let mut first_writer = first_terminal.writer.lock().unwrap();
        let inner = first_writer.take().unwrap();
        first_writer.replace(Box::new(BlockingWriter {
            entered: entered_tx,
            release: release_rx,
            inner,
        }));
        drop(first_writer);

        let writing_manager = Arc::clone(&manager);
        let first_id = first.terminal_id.clone();
        let write_thread =
            std::thread::spawn(move || writing_manager.write(&first_id, b"blocked".to_vec()));
        entered_rx.recv_timeout(Duration::from_secs(1)).unwrap();

        let resizing_manager = Arc::clone(&manager);
        let second_id = second.terminal_id.clone();
        let (resized_tx, resized_rx) = mpsc::sync_channel(0);
        let resize_thread = std::thread::spawn(move || {
            let result = resizing_manager.resize(&second_id, 100, 40);
            resized_tx.send(result).unwrap();
        });
        let resize_was_independent = resized_rx.recv_timeout(Duration::from_millis(200));

        release_tx.send(()).unwrap();
        write_thread.join().unwrap().unwrap();
        resize_thread.join().unwrap();
        manager.close_all();
        assert!(
            matches!(resize_was_independent, Ok(Ok(()))),
            "second terminal resize was blocked by first terminal write"
        );
    }

    #[test]
    fn explicit_close_is_emitted_once_after_the_terminal_final_output() {
        let _guard = pty_test_guard();
        let cwd = tempfile::tempdir().unwrap();
        let ordered = Arc::new(Mutex::new(Vec::<String>::new()));
        let output_log = Arc::clone(&ordered);
        let closed_log = Arc::clone(&ordered);
        let (output_entered_tx, output_entered_rx) = mpsc::sync_channel(0);
        let (release_output_tx, release_output_rx) = mpsc::sync_channel(0);
        let release_output_rx = Mutex::new(release_output_rx);
        let manager = Arc::new(TerminalManager::new(
            move |event| {
                if event.data.windows(12).any(|bytes| bytes == b"final-output") {
                    output_entered_tx.send(()).unwrap();
                    release_output_rx.lock().unwrap().recv().unwrap();
                    output_log.lock().unwrap().push("output".into());
                }
            },
            move |event| {
                closed_log
                    .lock()
                    .unwrap()
                    .push(format!("closed:{}", event.reason))
            },
        ));
        let snapshot = manager
            .open(cwd.path().to_string_lossy().into_owned(), 80, 24)
            .unwrap();
        manager
            .write(&snapshot.terminal_id, print_command("final-output"))
            .unwrap();
        output_entered_rx
            .recv_timeout(Duration::from_secs(1))
            .unwrap();

        let closing_manager = Arc::clone(&manager);
        let terminal_id = snapshot.terminal_id.clone();
        let close_thread = std::thread::spawn(move || closing_manager.close(&terminal_id));
        std::thread::sleep(Duration::from_millis(100));
        let close_overtook_output = !ordered.lock().unwrap().is_empty();
        release_output_tx.send(()).unwrap();
        close_thread.join().unwrap().unwrap();

        let deadline = Instant::now() + Duration::from_secs(1);
        loop {
            let events = ordered.lock().unwrap().clone();
            if events.len() >= 2 {
                assert!(
                    !close_overtook_output,
                    "close was emitted while final output was blocked"
                );
                assert_eq!(events, ["output", "closed:kullanıcı kapattı"]);
                break;
            }
            assert!(
                Instant::now() < deadline,
                "ordered events did not finish: {events:?}"
            );
            std::thread::sleep(Duration::from_millis(10));
        }
    }

    #[test]
    fn resizes_an_open_pty_and_keeps_it_writable() {
        let _guard = pty_test_guard();
        let cwd = tempfile::tempdir().unwrap();
        let (manager, outputs, _) = manager();
        let snapshot = manager
            .open(cwd.path().to_string_lossy().into_owned(), 80, 24)
            .unwrap();

        manager.resize(&snapshot.terminal_id, 100, 40).unwrap();
        manager
            .write(&snapshot.terminal_id, print_command("fusion-resized"))
            .unwrap();

        wait_for_output(&outputs, &snapshot.terminal_id, b"fusion-resized");
        manager.close_all();
    }

    #[test]
    fn ctrl_c_interrupts_the_foreground_command_without_closing_the_shell() {
        let _guard = pty_test_guard();
        let cwd = tempfile::tempdir().unwrap();
        let (manager, outputs, _) = manager();
        let snapshot = manager
            .open(cwd.path().to_string_lossy().into_owned(), 80, 24)
            .unwrap();

        #[cfg(unix)]
        manager
            .write(&snapshot.terminal_id, b"sleep 30\n".to_vec())
            .unwrap();
        #[cfg(windows)]
        manager
            .write(
                &snapshot.terminal_id,
                b"Start-Sleep -Seconds 30\r\n".to_vec(),
            )
            .unwrap();
        std::thread::sleep(Duration::from_millis(150));
        manager.write(&snapshot.terminal_id, vec![0x03]).unwrap();
        manager
            .write(
                &snapshot.terminal_id,
                print_command("fusion-after-interrupt"),
            )
            .unwrap();

        wait_for_output(&outputs, &snapshot.terminal_id, b"fusion-after-interrupt");
        manager.close_all();
    }

    #[test]
    #[cfg(unix)]
    fn close_all_stops_every_owned_child_before_waiting_for_blocked_event_delivery() {
        let _guard = pty_test_guard();
        let cwd = tempfile::tempdir().unwrap();
        let release = Arc::new((Mutex::new(false), Condvar::new()));
        let callback_release = release.clone();
        let manager = Arc::new(TerminalManager::new(
            |_| {},
            move |_| {
                let (lock, wake) = &*callback_release;
                let released = lock.lock().unwrap();
                drop(wake.wait_while(released, |released| !*released).unwrap());
            },
        ));
        let pids: Vec<_> = (0..3)
            .map(|_| {
                manager
                    .open(cwd.path().to_string_lossy().into_owned(), 80, 24)
                    .unwrap()
                    .pid
                    .unwrap()
            })
            .collect();
        let closing_manager = manager.clone();
        let worker = std::thread::spawn(move || closing_manager.close_all());
        let deadline = Instant::now() + Duration::from_secs(1);
        let all_exited = || {
            pids.iter().all(|pid| {
                // SAFETY: signal zero only observes the exact PTY fixture PIDs.
                unsafe { libc::kill(*pid as i32, 0) != 0 }
            })
        };
        while !all_exited() && Instant::now() < deadline {
            std::thread::sleep(Duration::from_millis(10));
        }
        let exited_before_delivery = all_exited();
        let return_deadline = Instant::now() + Duration::from_secs(3);
        while !worker.is_finished() && Instant::now() < return_deadline {
            std::thread::sleep(Duration::from_millis(10));
        }
        let finished_without_delivery = worker.is_finished();
        *release.0.lock().unwrap() = true;
        release.1.notify_all();
        worker.join().unwrap();
        assert!(
            exited_before_delivery,
            "a blocked event callback delayed stopping another owned terminal"
        );
        assert!(
            finished_without_delivery,
            "callback waits multiplied the terminal batch deadline"
        );
    }

    #[test]
    fn close_all_terminates_every_child_and_rejects_more_input() {
        let _guard = pty_test_guard();
        let first_cwd = tempfile::tempdir().unwrap();
        let second_cwd = tempfile::tempdir().unwrap();
        let (manager, _, closed) = manager();
        let first = manager
            .open(first_cwd.path().to_string_lossy().into_owned(), 80, 24)
            .unwrap();
        let second = manager
            .open(second_cwd.path().to_string_lossy().into_owned(), 80, 24)
            .unwrap();

        manager.close_all();

        assert!(manager.write(&first.terminal_id, b"x".to_vec()).is_err());
        assert!(manager.write(&second.terminal_id, b"x".to_vec()).is_err());
        let closed_ids: Vec<String> = closed
            .lock()
            .unwrap()
            .iter()
            .map(|event| event.terminal_id.clone())
            .collect();
        assert!(closed_ids.contains(&first.terminal_id));
        assert!(closed_ids.contains(&second.terminal_id));
    }
}
