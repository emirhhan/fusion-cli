use std::fs;
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::PathBuf;
use std::sync::Mutex;
use tauri::{Manager, WebviewWindow};

const HISTORY_BYTES: u64 = 128 * 1024;
const TURN_CHARS: usize = 4_000;
static TRANSCRIPT_LOCK: Mutex<()> = Mutex::new(());

fn transcript_path(window: &WebviewWindow) -> Result<PathBuf, String> {
    if window.label() != super::SES_PENCERESI {
        return Err("Konuşma dökümü yalnız Talk penceresinden açılabilir.".into());
    }
    let dir = window
        .app_handle()
        .path()
        .app_data_dir()
        .map_err(|error| error.to_string())?;
    fs::create_dir_all(&dir).map_err(|error| error.to_string())?;
    Ok(dir.join("talk-transcript.jsonl"))
}

fn read_tail(path: &PathBuf) -> std::io::Result<Vec<String>> {
    let mut file = match fs::File::open(path) {
        Ok(file) => file,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(error),
    };
    let start = file.metadata()?.len().saturating_sub(HISTORY_BYTES);
    file.seek(SeekFrom::Start(start))?;
    let mut bytes = Vec::new();
    file.take(HISTORY_BYTES).read_to_end(&mut bytes)?;
    Ok(bytes
        .split(|byte| *byte == b'\n')
        .skip(usize::from(start > 0))
        .filter_map(|line| serde_json::from_slice::<String>(line).ok())
        .collect())
}

#[tauri::command]
pub fn talk_transcript_read(window: WebviewWindow) -> Result<Vec<String>, String> {
    let path = transcript_path(&window)?;
    let _lock = TRANSCRIPT_LOCK.lock().map_err(|error| error.to_string())?;
    read_tail(&path)
        .map(|lines| lines.into_iter().rev().take(100).rev().collect())
        .map_err(|error| error.to_string())
}

#[tauri::command]
pub fn talk_transcript_append(window: WebviewWindow, line: String) -> Result<(), String> {
    let line: String = line.chars().take(TURN_CHARS).collect();
    if line.trim().is_empty() {
        return Ok(());
    }
    let path = transcript_path(&window)?;
    let _lock = TRANSCRIPT_LOCK.lock().map_err(|error| error.to_string())?;
    let mut options = fs::OpenOptions::new();
    options.create(true).append(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(&path).map_err(|error| error.to_string())?;
    if file.metadata().map_err(|error| error.to_string())?.len() > HISTORY_BYTES * 2 {
        drop(file);
        let recent = read_tail(&path).map_err(|error| error.to_string())?;
        let mut temp =
            tempfile::NamedTempFile::new_in(path.parent().ok_or("Döküm klasörü bulunamadı.")?)
                .map_err(|error| error.to_string())?;
        for prior in recent {
            writeln!(temp, "{}", serde_json::json!(prior)).map_err(|error| error.to_string())?;
        }
        temp.persist(&path).map_err(|error| error.to_string())?;
        file = options.open(&path).map_err(|error| error.to_string())?;
    }
    writeln!(file, "{}", serde_json::json!(line)).map_err(|error| error.to_string())
}
