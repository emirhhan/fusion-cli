use portable_pty::{native_pty_system, Child, CommandBuilder, MasterPty, PtySize};
use serde::Serialize;
use std::collections::HashMap;
use std::io::Write;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{mpsc, Arc, Condvar, Mutex};

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
        }
    }

    pub(crate) fn open(
        &self,
        cwd: String,
        cols: u16,
        rows: u16,
    ) -> Result<TerminalSnapshot, String> {
        if cols == 0 || rows == 0 {
            return Err("terminal boyutu sıfır olamaz".into());
        }
        let cwd_path = std::path::Path::new(&cwd);
        if !cwd_path.is_dir() {
            return Err(format!("çalışma dizini bulunamadı: {cwd}"));
        }

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
        let events = event_worker(
            terminal_id.clone(),
            Arc::clone(&self.output_sink),
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
        close_terminal(terminal);
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
        for (_, terminal) in terminals {
            close_terminal(terminal);
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
            .is_some_and(|terminal| terminal.child.lock().unwrap().is_some())
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

fn close_terminal(terminal: Arc<ManagedTerminal>) {
    wait_for_child(&terminal, true);
    terminal.writer.lock().unwrap().take();
    terminal.master.lock().unwrap().take();
    wait_for_close_delivery(&terminal);
}

fn wait_for_child(terminal: &ManagedTerminal, kill: bool) -> Option<u32> {
    let child = terminal.child.lock().unwrap().take();
    if let Some(mut child) = child {
        if kill {
            let _ = child.kill();
        }
        return child.wait().ok().map(|status| status.exit_code());
    }
    None
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

fn wait_for_close_delivery(terminal: &ManagedTerminal) {
    let (delivered, wake) = &*terminal.close_delivered;
    let mut delivered = delivered.lock().unwrap();
    while !*delivered {
        delivered = wake.wait(delivered).unwrap();
    }
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
            let exit_code = wait_for_child(&terminal, false);
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
        claim_explicit_terminal, event_worker, forward_output, queue_closed_once, wait_for_child,
        ManagedTerminal, TerminalClosed, TerminalManager, TerminalMap, TerminalOutput,
    };
    use portable_pty::{native_pty_system, CommandBuilder, PtySize};
    use std::io::Write;
    use std::path::Path;
    use std::sync::atomic::AtomicBool;
    use std::sync::{mpsc, Arc, Condvar, Mutex, MutexGuard, OnceLock};
    use std::time::{Duration, Instant};

    type OutputLog = Arc<Mutex<Vec<TerminalOutput>>>;
    type ClosedLog = Arc<Mutex<Vec<TerminalClosed>>>;

    fn pty_test_guard() -> MutexGuard<'static, ()> {
        static PTY_TEST_LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        PTY_TEST_LOCK.get_or_init(|| Mutex::new(())).lock().unwrap()
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

        wait_for_child(&terminal, true);
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
