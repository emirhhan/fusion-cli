use portable_pty::{native_pty_system, Child, CommandBuilder, MasterPty, PtySize};
use serde::Serialize;
use std::collections::HashMap;
use std::io::Write;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{mpsc, Arc, Mutex};

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
}

type OutputSink = Arc<dyn Fn(TerminalOutput) + Send + Sync>;
type ClosedSink = Arc<dyn Fn(TerminalClosed) + Send + Sync>;

struct ManagedTerminal {
    master: Box<dyn MasterPty + Send>,
    writer: Box<dyn Write + Send>,
    child: Box<dyn Child + Send + Sync>,
    closed: Arc<AtomicBool>,
}

type TerminalMap = Arc<Mutex<HashMap<String, ManagedTerminal>>>;

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
        let closed = Arc::new(AtomicBool::new(false));

        self.terminals.lock().unwrap().insert(
            terminal_id.clone(),
            ManagedTerminal {
                master: pair.master,
                writer,
                child,
                closed: Arc::clone(&closed),
            },
        );
        forward_output(
            terminal_id.clone(),
            reader,
            Arc::clone(&self.output_sink),
            Arc::clone(&self.closed_sink),
            closed,
            Arc::clone(&self.terminals),
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
        let mut terminals = self.terminals.lock().unwrap();
        let terminal = terminals.get_mut(id).ok_or("terminal bulunamadı")?;
        terminal
            .writer
            .write_all(&data)
            .and_then(|_| terminal.writer.flush())
            .map_err(|error| format!("terminale yazılamadı: {error}"))
    }

    pub(crate) fn resize(&self, id: &str, cols: u16, rows: u16) -> Result<(), String> {
        if cols == 0 || rows == 0 {
            return Err("terminal boyutu sıfır olamaz".into());
        }
        let terminals = self.terminals.lock().unwrap();
        let terminal = terminals.get(id).ok_or("terminal bulunamadı")?;
        terminal
            .master
            .resize(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .map_err(|error| format!("terminal boyutlandırılamadı: {error}"))
    }

    pub(crate) fn close(&self, id: &str) -> Result<(), String> {
        let terminal = self
            .terminals
            .lock()
            .unwrap()
            .remove(id)
            .ok_or("terminal bulunamadı")?;
        close_terminal(id, terminal, &self.closed_sink);
        Ok(())
    }

    pub(crate) fn close_all(&self) {
        let terminals: Vec<_> = self.terminals.lock().unwrap().drain().collect();
        for (id, terminal) in terminals {
            close_terminal(&id, terminal, &self.closed_sink);
        }
    }
}

fn close_terminal(id: &str, mut terminal: ManagedTerminal, sink: &ClosedSink) {
    let _ = terminal.child.kill();
    let _ = terminal.child.wait();
    emit_closed_once(id, "kullanıcı kapattı", &terminal.closed, sink);
}

fn emit_closed_once(id: &str, reason: &str, closed: &AtomicBool, sink: &ClosedSink) {
    if !closed.swap(true, Ordering::AcqRel) {
        sink(TerminalClosed {
            terminal_id: id.to_string(),
            reason: reason.to_string(),
        });
    }
}

fn forward_output(
    id: String,
    mut reader: Box<dyn std::io::Read + Send>,
    output_sink: OutputSink,
    closed_sink: ClosedSink,
    closed: Arc<AtomicBool>,
    terminals: TerminalMap,
) {
    let (sender, receiver) = mpsc::sync_channel::<Vec<u8>>(OUTPUT_QUEUE_CAPACITY);
    let output_id = id.clone();
    std::thread::spawn(move || {
        while let Ok(data) = receiver.recv() {
            output_sink(TerminalOutput {
                terminal_id: output_id.clone(),
                data,
            });
        }
    });
    std::thread::spawn(move || {
        let mut buffer = vec![0; OUTPUT_CHUNK_BYTES];
        loop {
            match reader.read(&mut buffer) {
                Ok(0) | Err(_) => break,
                Ok(count) => {
                    if sender.send(buffer[..count].to_vec()).is_err() {
                        break;
                    }
                }
            }
        }
        if let Some(mut terminal) = terminals.lock().unwrap().remove(&id) {
            let _ = terminal.child.wait();
        }
        emit_closed_once(&id, "süreç kapandı", &closed, &closed_sink);
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
    use super::{TerminalClosed, TerminalManager, TerminalOutput};
    use std::path::Path;
    use std::sync::{Arc, Mutex};
    use std::time::{Duration, Instant};

    type OutputLog = Arc<Mutex<Vec<TerminalOutput>>>;
    type ClosedLog = Arc<Mutex<Vec<TerminalClosed>>>;

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
        let cwd = tempfile::tempdir().unwrap();
        let marker = cwd.path().join("fusion-cwd-marker");
        std::fs::write(&marker, b"").unwrap();
        let (manager, outputs, _) = manager();

        let snapshot = manager
            .open(cwd.path().to_string_lossy().into_owned(), 80, 24)
            .unwrap();
        #[cfg(unix)]
        manager
            .write(&snapshot.terminal_id, b"pwd\n".to_vec())
            .unwrap();
        #[cfg(windows)]
        manager
            .write(&snapshot.terminal_id, b"Get-Location\r\n".to_vec())
            .unwrap();

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
        let cwd = tempfile::tempdir().unwrap();
        let (manager, outputs, _) = manager();
        let snapshot = manager
            .open(cwd.path().to_string_lossy().into_owned(), 80, 24)
            .unwrap();

        #[cfg(unix)]
        manager
            .write(
                &snapshot.terminal_id,
                b"printf '\\x1b[31mfusion-pty-ok\\x1b[0m\\n'\n".to_vec(),
            )
            .unwrap();
        #[cfg(windows)]
        manager
            .write(
                &snapshot.terminal_id,
                b"Write-Output \"`e[31mfusion-pty-ok`e[0m\"\r\n".to_vec(),
            )
            .unwrap();

        wait_for_output(
            &outputs,
            &snapshot.terminal_id,
            b"\x1b[31mfusion-pty-ok\x1b[0m",
        );
        manager.close_all();
    }

    #[test]
    fn resizes_an_open_pty_and_keeps_it_writable() {
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
