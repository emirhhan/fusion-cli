"""AST sınırları, bounded büyük semboller ve güvenli satır geri dönüşü."""

from __future__ import annotations

import pytest

from fusion_cli.memory.chunking import CHUNK_LINES, build_chunks, chunk_file


def test_decorator_sinif_ve_islev_sinirlari_korunur(tmp_path):
    source = (
        "import functools\n\n@decorate\ndef first():\n    return 1\n\n"
        "class Service:\n    def run(self):\n        return 2\n\n"
        "async def last():\n    return 3\n"
    )
    path = tmp_path / "service.py"
    path.write_text(source, encoding="utf-8")
    chunks = chunk_file(path, tmp_path, strategy="symbols")

    assert [(chunk.start_line, chunk.end_line) for chunk in chunks] == [
        (1, 2),
        (3, 5),
        (7, 9),
        (11, 12),
    ]
    assert chunks[1].text.startswith("@decorate\ndef first")
    assert "def run" in chunks[2].text


def test_buyuk_sinif_metot_sinirlariyla_ve_buyuk_islev_bounded_bolunur(tmp_path):
    path = tmp_path / "large.py"
    path.write_text(
        "class Service:\n    @decorate\n    def huge(self):\n"
        + "        value = 1\n" * (CHUNK_LINES * 3)
        + "\n    def small(self):\n        return 2\n",
        encoding="utf-8",
    )
    chunks = chunk_file(path, tmp_path, strategy="symbols")

    assert all(chunk.end_line - chunk.start_line + 1 <= CHUNK_LINES for chunk in chunks)
    assert any(chunk.text.startswith("@decorate\n    def huge") for chunk in chunks)
    assert any(chunk.text.startswith("def small") for chunk in chunks)
    covered = {line for chunk in chunks for line in range(chunk.start_line, chunk.end_line + 1)}
    assert covered == set(range(1, 184)) | {185, 186}


@pytest.mark.parametrize(
    ("name", "source"),
    [
        ("broken.py", "def broken(:\n    pass\n"),
        ("a.ts", "export const f = () => 1\n"),
        ("a.js", "function f() { return 1; }\n"),
    ],
)
def test_parser_hatasi_ve_diger_diller_satirlara_doner(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    fallback = chunk_file(path, tmp_path, strategy="symbols")
    lines = chunk_file(path, tmp_path)

    assert [(c.start_line, c.end_line, c.text) for c in fallback] == [
        (c.start_line, c.end_line, c.text) for c in lines
    ]
    assert {c.id for c in fallback}.isdisjoint(c.id for c in lines)


def test_strateji_kimlikleri_ayrilir_ve_build_limit_korunur(tmp_path):
    path = tmp_path / "a.py"
    path.write_text("def first():\n    pass\n\ndef second():\n    pass\n", encoding="utf-8")
    assert chunk_file(path, tmp_path)[0].id != chunk_file(path, tmp_path, strategy="symbols")[0].id
    assert len(build_chunks(tmp_path, limit=1, strategy="symbols")) == 1
    assert build_chunks(tmp_path, limit=0, strategy="symbols") == []


def test_bilinmeyen_strateji_acik_hata_verir(tmp_path):
    path = tmp_path / "a.py"
    path.write_text("pass\n", encoding="utf-8")
    with pytest.raises(ValueError, match="strateji"):
        chunk_file(path, tmp_path, strategy="typo")


def _source_index(root, strategy="lines"):
    from fusion_cli.memory.code_index import ChromaCodeIndex

    index = object.__new__(ChromaCodeIndex)
    index._root = root.resolve()
    index._chunk_strategy = strategy
    return index


@pytest.mark.parametrize("swap", ["leaf", "parent"])
def test_tazelik_acma_yarisinda_kok_disi_bayt_okumaz(tmp_path, monkeypatch, swap):
    import os
    from pathlib import Path

    root = tmp_path / "project"
    parent = root / "pkg"
    parent.mkdir(parents=True)
    source = parent / "a.py"
    source.write_text("def initial():\n    pass\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "a.py"
    outside_file.write_text("def outsideSensitive():\n    pass\n", encoding="utf-8")
    outside_stat = outside_file.stat()
    real_stat, real_text, real_read = Path.stat, Path.read_text, os.read
    checks = []
    outside_reads = []

    def racing_stat(path, *args, **kwargs):
        observed = real_stat(path, *args, **kwargs)
        if path == source:
            checks.append(True)
            if len(checks) == 2:
                if swap == "leaf":
                    source.unlink()
                    source.symlink_to(outside_file)
                else:
                    parent.rename(root / "parked")
                    parent.symlink_to(outside, target_is_directory=True)
        return observed

    def observed_text(path, *args, **kwargs):
        content = real_text(path, *args, **kwargs)
        if "outsideSensitive" in content:
            outside_reads.append(True)
        return content

    def observed_read(descriptor, count):
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) == (outside_stat.st_dev, outside_stat.st_ino):
            outside_reads.append(True)
        return real_read(descriptor, count)

    monkeypatch.setattr(Path, "stat", racing_stat)
    monkeypatch.setattr(Path, "read_text", observed_text)
    monkeypatch.setattr(os, "read", observed_read)
    identifiers = _source_index(root)._source_ids("pkg/a.py")
    assert len(checks) >= 2
    assert outside_reads == []
    assert identifiers == set()


def test_tazelik_kontrol_sonrasi_buyumeyi_sinirli_okur(tmp_path, monkeypatch):
    import os
    from pathlib import Path

    from fusion_cli.memory.chunking import MAX_FILE_BYTES

    source = tmp_path / "a.py"
    source.write_text("def initial():\n    pass\n", encoding="utf-8")
    real_text, real_read = Path.read_text, os.read
    observed_bytes = []
    grown = []

    def grow():
        if not grown:
            source.write_bytes(b"#" * (MAX_FILE_BYTES + 19))
            grown.append(True)

    def growing_text(path, *args, **kwargs):
        grow()
        content = real_text(path, *args, **kwargs)
        observed_bytes.append(len(content.encode()))
        return content

    def growing_read(descriptor, count):
        grow()
        content = real_read(descriptor, count)
        observed_bytes.append(len(content))
        return content

    monkeypatch.setattr(Path, "read_text", growing_text)
    monkeypatch.setattr(os, "read", growing_read)
    identifiers = _source_index(tmp_path)._source_ids("a.py")
    assert grown
    assert sum(observed_bytes) <= MAX_FILE_BYTES + 1
    assert identifiers == set()


def test_tazelik_guvenli_descriptor_destegi_yoksa_okumaz(tmp_path, monkeypatch):
    import os
    from pathlib import Path

    source = tmp_path / "a.py"
    source.write_text("def initial():\n    pass\n", encoding="utf-8")

    def forbidden_read(*args, **kwargs):
        raise AssertionError("Güvenli açma desteği yokken kaynak okunmamalı")

    monkeypatch.setattr(os, "supports_dir_fd", set())
    monkeypatch.setattr(Path, "read_text", forbidden_read)
    assert _source_index(tmp_path)._source_ids("a.py") == set()


@pytest.mark.parametrize("strategy", ["lines", "symbols"])
def test_tazelik_normal_kaynak_kimligini_yeniden_acmadan_korur(tmp_path, monkeypatch, strategy):
    from pathlib import Path

    source = tmp_path / "a.py"
    source.write_text("def initial():\n    pass\n", encoding="utf-8")
    expected = {chunk.id for chunk in chunk_file(source, tmp_path, strategy=strategy)}
    if strategy == "lines":
        assert expected == {"11bb16b8886dc7a4"}

    def forbidden_reopen(*args, **kwargs):
        raise AssertionError("Doğrulanmış metin path üzerinden yeniden açılmamalı")

    monkeypatch.setattr(Path, "read_text", forbidden_reopen)
    assert _source_index(tmp_path, strategy)._source_ids("a.py") == expected
