use serde::Serialize;
use std::io::{BufRead, BufReader, Read};
use std::process::{Child, ChildStderr, ChildStdout, Command, Stdio};
use std::sync::{
    atomic::{AtomicU64, Ordering},
    Mutex,
};
use tauri::{AppHandle, Emitter, Manager};

pub(crate) const STDERR_LIMIT: usize = 2 * 1024;

struct OwnedChild {
    child: Child,
    session: u64,
}

pub(crate) struct SpeechManager {
    child: Mutex<Option<OwnedChild>>,
    next_session: AtomicU64,
}

impl SpeechManager {
    pub(crate) fn new() -> Self {
        Self {
            child: Mutex::new(None),
            next_session: AtomicU64::new(0),
        }
    }

    fn start(&self, command: &mut Command) -> Result<SpeechStart, String> {
        let mut child_slot = self
            .child
            .lock()
            .map_err(|_| "tanıma süreç kilidi kullanılamıyor".to_string())?;

        if let Some(owned) = child_slot.as_mut() {
            match owned.child.try_wait() {
                Ok(None) => return Ok(SpeechStart::reused(owned.child.id(), owned.session)),
                Ok(Some(_)) => {
                    child_slot.take();
                }
                Err(_) => {
                    if let Some(mut stale) = child_slot.take() {
                        let _ = stale.child.kill();
                        let _ = stale.child.wait();
                    }
                }
            }
        }

        let mut child = command
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|error| format!("tanıma başlatılamadı: {error}"))?;
        let pid = child.id();
        let stdout = match child.stdout.take() {
            Some(stdout) => stdout,
            None => {
                terminate(child);
                return Err("tanıma çıktısı okunamadı".into());
            }
        };
        let stderr = match child.stderr.take() {
            Some(stderr) => stderr,
            None => {
                terminate(child);
                return Err("tanıma hata çıktısı okunamadı".into());
            }
        };
        let session = self.next_session.fetch_add(1, Ordering::Relaxed) + 1;
        *child_slot = Some(OwnedChild { child, session });
        Ok(SpeechStart::started(pid, session, stdout, stderr))
    }

    pub(crate) fn stop(&self) -> Result<(), String> {
        let child = self
            .child
            .lock()
            .map_err(|_| "tanıma süreç kilidi kullanılamıyor".to_string())?
            .take();
        if let Some(owned) = child {
            terminate(owned.child);
        }
        Ok(())
    }

    pub(crate) fn is_running(&self) -> bool {
        let Ok(mut child_slot) = self.child.lock() else {
            return false;
        };
        let running = child_slot
            .as_mut()
            .is_some_and(|owned| matches!(owned.child.try_wait(), Ok(None)));
        if !running {
            child_slot.take();
        }
        running
    }

    fn finish(&self, pid: u32, session: u64) -> bool {
        let child = {
            let Ok(mut child_slot) = self.child.lock() else {
                return false;
            };
            match child_slot.as_ref() {
                Some(owned) if owned.child.id() == pid && owned.session == session => {
                    child_slot.take()
                }
                Some(_) => return false,
                // `stop()` child'ı yuvadan bilerek çıkardıysa eski stdout
                // okuyucusu artık bir "beklenmedik son" olayı yayınlamamalı.
                None => return false,
            }
        };
        if let Some(owned) = child {
            terminate(owned.child);
        }
        true
    }

    #[cfg(test)]
    pub(crate) fn start_test_child(&self) -> Result<u32, String> {
        let mut command = Command::new(
            std::env::current_exe().map_err(|error| format!("test ikilisi bulunamadı: {error}"))?,
        );
        command
            .args([
                "--exact",
                "speech::tests::speech_test_helper",
                "--ignored",
                "--nocapture",
            ])
            .env("FUSION_SPEECH_TEST_MODE", "sleep");
        let mut started = self.start(&mut command)?;
        if let Some(mut stdout) = started.stdout.take() {
            std::thread::spawn(move || {
                let _ = std::io::copy(&mut stdout, &mut std::io::sink());
            });
        }
        if let Some(mut stderr) = started.stderr.take() {
            std::thread::spawn(move || {
                let _ = std::io::copy(&mut stderr, &mut std::io::sink());
            });
        }
        Ok(started.pid())
    }
}

fn terminate(mut child: Child) {
    if matches!(child.try_wait(), Ok(None)) {
        let _ = child.kill();
    }
    let _ = child.wait();
}

struct SpeechStart {
    pid: u32,
    session: u64,
    started: bool,
    stdout: Option<ChildStdout>,
    stderr: Option<ChildStderr>,
}

impl SpeechStart {
    fn started(pid: u32, session: u64, stdout: ChildStdout, stderr: ChildStderr) -> Self {
        Self {
            pid,
            session,
            started: true,
            stdout: Some(stdout),
            stderr: Some(stderr),
        }
    }

    fn reused(pid: u32, session: u64) -> Self {
        Self {
            pid,
            session,
            started: false,
            stdout: None,
            stderr: None,
        }
    }

    fn pid(&self) -> u32 {
        self.pid
    }

    fn session(&self) -> u64 {
        self.session
    }

    fn was_started(&self) -> bool {
        self.started
    }
}

#[derive(Clone, Debug, Serialize)]
struct StderrSummary {
    message: String,
    captured_bytes: usize,
    truncated: bool,
}

#[derive(Clone, Debug, Serialize)]
struct SpeechEnded {
    session: u64,
    stderr_summary: Option<StderrSummary>,
}

pub(crate) fn start_recognition(
    app: AppHandle,
    manager: &SpeechManager,
    command: &mut Command,
) -> Result<u64, String> {
    let mut started = manager.start(command)?;
    if !started.was_started() {
        return Ok(started.session());
    }

    let pid = started.pid();
    let session = started.session();
    let stdout = started
        .stdout
        .take()
        .ok_or_else(|| "tanıma çıktısı okunamadı".to_string())?;
    let stderr = started
        .stderr
        .take()
        .ok_or_else(|| "tanıma hata çıktısı okunamadı".to_string())?;
    let stderr_reader = std::thread::spawn(move || summarize_stderr(stderr));

    std::thread::spawn(move || {
        forward_stdout(stdout, |line| {
            let _ = app.emit("ses://tanima", SpeechOutput { session, line });
        });
        let is_current = app.state::<SpeechManager>().finish(pid, session);
        let stderr_summary = stderr_reader.join().unwrap_or(None);
        if is_current {
            let _ = app.emit(
                "ses://tanima-sonlandi",
                SpeechEnded {
                    session,
                    stderr_summary,
                },
            );
        }
    });
    Ok(session)
}

#[derive(Clone, Debug, Serialize)]
struct SpeechOutput {
    session: u64,
    line: String,
}

fn forward_stdout(reader: impl Read, mut emit: impl FnMut(String)) {
    for line in BufReader::new(reader).lines().map_while(Result::ok) {
        emit(line);
    }
}

fn summarize_stderr(mut reader: impl Read) -> Option<StderrSummary> {
    let mut captured_bytes = 0usize;
    let mut total_bytes = 0usize;
    let mut buffer = [0u8; 512];
    loop {
        match reader.read(&mut buffer) {
            Ok(0) | Err(_) => break,
            Ok(read) => {
                total_bytes = total_bytes.saturating_add(read);
                captured_bytes = captured_bytes.saturating_add(read).min(STDERR_LIMIT);
            }
        }
    }
    (total_bytes > 0).then(|| StderrSummary {
        message: "Tanıma yardımcısı hata ayrıntısı bildirdi; içerik güvenlik nedeniyle gizlendi."
            .into(),
        captured_bytes,
        truncated: total_bytes > STDERR_LIMIT,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;
    use std::process::Command;
    use std::thread;
    use std::time::{Duration, Instant};

    fn helper_command(mode: &str) -> Command {
        let mut command = Command::new(std::env::current_exe().expect("test ikilisi bulunamadı"));
        command
            .args([
                "--exact",
                "speech::tests::speech_test_helper",
                "--ignored",
                "--nocapture",
            ])
            .env("FUSION_SPEECH_TEST_MODE", mode);
        command
    }

    fn wait_until_stopped(manager: &SpeechManager) {
        let deadline = Instant::now() + Duration::from_secs(2);
        while manager.is_running() && Instant::now() < deadline {
            thread::sleep(Duration::from_millis(10));
        }
        assert!(!manager.is_running(), "tanıma child süreci sonlanmadı");
    }

    #[test]
    fn second_start_reuses_the_single_owned_child() {
        let manager = SpeechManager::new();
        let first = manager
            .start(&mut helper_command("sleep"))
            .expect("ilk child başlamalı");
        let first_pid = first.pid();

        let second = manager
            .start(&mut helper_command("sleep"))
            .expect("ikinci çağrı mevcut child'ı kullanmalı");

        assert!(first.was_started());
        assert!(!second.was_started());
        assert_eq!(second.pid(), first_pid);
        manager.stop().expect("test child'ı temizlenmeli");
    }

    #[test]
    fn stop_terminates_and_releases_the_owned_child() {
        let manager = SpeechManager::new();
        manager
            .start(&mut helper_command("sleep"))
            .expect("child başlamalı");

        assert!(manager.is_running());
        manager.stop().expect("child sonlandırılmalı");

        wait_until_stopped(&manager);
    }

    #[test]
    fn stale_stdout_reader_cannot_finish_a_newer_child() {
        let manager = SpeechManager::new();
        let first_pid = manager
            .start(&mut helper_command("sleep"))
            .expect("ilk child başlamalı")
            .pid();
        manager.stop().expect("ilk child durmalı");
        let second_pid = manager
            .start(&mut helper_command("sleep"))
            .expect("ikinci child başlamalı")
            .pid();

        assert!(!manager.finish(first_pid, 1));
        assert!(manager.is_running());
        assert_ne!(first_pid, second_pid);
        manager.stop().expect("ikinci child temizlenmeli");
    }

    #[test]
    fn intentionally_stopped_child_does_not_publish_an_ended_signal() {
        let manager = SpeechManager::new();
        let pid = manager
            .start(&mut helper_command("sleep"))
            .expect("child başlamalı")
            .pid();

        manager.stop().expect("child temizlenmeli");

        assert!(!manager.finish(pid, 1));
    }

    #[test]
    fn every_fresh_child_gets_a_monotonically_increasing_session_token() {
        let manager = SpeechManager::new();
        let first = manager
            .start(&mut helper_command("sleep"))
            .expect("ilk child başlamalı");
        let first_session = first.session();
        manager.stop().expect("ilk child durmalı");
        let second = manager
            .start(&mut helper_command("sleep"))
            .expect("ikinci child başlamalı");

        assert!(second.session() > first_session);
        manager.stop().expect("ikinci child temizlenmeli");
    }

    #[test]
    fn reused_child_keeps_its_session_token() {
        let manager = SpeechManager::new();
        let first = manager
            .start(&mut helper_command("sleep"))
            .expect("ilk child başlamalı");
        let second = manager
            .start(&mut helper_command("sleep"))
            .expect("mevcut child kullanılmalı");

        assert_eq!(second.session(), first.session());
        manager.stop().expect("child temizlenmeli");
    }

    #[test]
    fn stdout_lines_are_forwarded_without_rewriting_the_helper_protocol() {
        let input = Cursor::new(
            b"{\"tur\":\"hazir\",\"metin\":\"tr-TR\"}\n{\"tur\":\"son\",\"metin\":\"merhaba\"}\n",
        );
        let mut events = Vec::new();

        forward_stdout(input, |line| events.push(line));

        assert_eq!(
            events,
            vec![
                "{\"tur\":\"hazir\",\"metin\":\"tr-TR\"}",
                "{\"tur\":\"son\",\"metin\":\"merhaba\"}",
            ]
        );
    }

    #[test]
    fn stderr_summary_is_bounded_and_never_contains_raw_secrets() {
        let secret = "token=super-secret-value ".repeat(300);

        let summary = summarize_stderr(Cursor::new(secret.as_bytes()))
            .expect("stderr varsa güvenli bir özet dönmeli");

        assert!(summary.captured_bytes <= STDERR_LIMIT);
        assert!(summary.truncated);
        assert!(!summary.message.contains("super-secret-value"));
        assert!(!summary.message.contains("token="));
    }

    #[test]
    #[ignore]
    fn speech_test_helper() {
        match std::env::var("FUSION_SPEECH_TEST_MODE").as_deref() {
            Ok("sleep") => thread::sleep(Duration::from_secs(30)),
            Ok("output") => {
                println!("{{\"tur\":\"son\",\"metin\":\"merhaba\"}}");
                eprintln!("token=super-secret-value");
            }
            mode => panic!("bilinmeyen test helper kipi: {mode:?}"),
        }
    }
}
