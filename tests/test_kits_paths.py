"""Kits durum dosyası yolu: Python (`config/paths.py`) ve Tauri (`kits_process.rs`) sözleşmesi.

Ölçüldü (31 Ekim, inceleme): Tauri `XDG_DATA_HOME`'u yok sayıyor, Python okuyordu; XDG ayarlı
kullanıcıda Fusion `kits-bridge.json`'ı bulamayıp "Kits çalışmıyor" diyordu. Rust tarafı
`kits_process::tests::kits_veri_klasoru_python_ile_ayni_kurali_izler` ile aynı örnekleri sınar.
"""

from __future__ import annotations

from fusion_cli.config import paths


def test_durum_dosyasi_yolu_xdg_data_home_kuralini_izler(tmp_path, monkeypatch):
    # Sözleşme (31 Ekim): Tauri `kits_process::kits_data_dir` ile aynı kural —
    # XDG_DATA_HOME ayarlıysa oradan, yoksa ~/.local/share; boş değer ayarsız sayılır.
    monkeypatch.setattr(paths.sys, "platform", "darwin")
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path / "ev"))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert paths.kits_state_file() == (
        tmp_path / "ev" / ".local" / "share" / "fusion-cli" / "kits" / "kits-bridge.json"
    )
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert paths.kits_state_file() == tmp_path / "xdg" / "fusion-cli" / "kits" / "kits-bridge.json"
    monkeypatch.setenv("XDG_DATA_HOME", "")
    assert paths.kits_state_file().parts[-5:-3] == (".local", "share")
