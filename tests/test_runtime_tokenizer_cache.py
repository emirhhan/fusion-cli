"""Build-time tokenizer data integrity and offline frozen bootstrap contracts."""

from __future__ import annotations

import ast
import hashlib
import inspect
import io
import runpy
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "desktop_build/runtime/tokenizer_cache.py"
URL = "https://openaipublic.blob.core.windows.net/encodings/unit.tiktoken"
DATA = b"offline public tokenizer fixture\n"


def helper():
    return runpy.run_path(str(HELPER))


def configure(monkeypatch, helper, data=DATA):
    scope = helper["stage_tokenizer_cache"].__globals__
    monkeypatch.setitem(scope, "RESOURCES", ((URL, hashlib.sha256(data).hexdigest()),))
    return scope


def test_stages_verified_public_cache_without_mutating_it(monkeypatch, tmp_path):
    api = helper()
    configure(monkeypatch, api)
    cache = tmp_path / "user-cache"
    cache.mkdir()
    key = hashlib.sha1(URL.encode()).hexdigest()
    source = cache / key
    source.write_bytes(DATA)
    source.chmod(0o444)
    result = Path(api["stage_tokenizer_cache"](str(tmp_path / "build"), cache_dirs=(cache,)))
    assert (result / key).read_bytes() == DATA
    assert source.read_bytes() == DATA
    assert sorted(p.name for p in cache.iterdir()) == [key]


def test_invalid_user_cache_fails_closed_without_deleting_or_rewriting(monkeypatch, tmp_path):
    api = helper()
    configure(monkeypatch, api)
    cache = tmp_path / "user-cache"
    cache.mkdir()
    source = cache / hashlib.sha1(URL.encode()).hexdigest()
    source.write_bytes(b"bad-cache")
    with pytest.raises(ValueError, match="hash"):
        api["stage_tokenizer_cache"](str(tmp_path / "build"), cache_dirs=(cache,))
    assert source.read_bytes() == b"bad-cache"


class Response(io.BytesIO):
    def geturl(self):
        return URL


def test_download_stages_valid_bytes_and_enforces_byte_limit(monkeypatch, tmp_path):
    api = helper()
    scope = configure(monkeypatch, api)
    monkeypatch.setattr(
        scope["urllib"].request.OpenerDirector, "open", lambda self, url, timeout: Response(DATA)
    )
    result = Path(api["stage_tokenizer_cache"](str(tmp_path / "valid"), cache_dirs=()))
    assert (result / hashlib.sha1(URL.encode()).hexdigest()).read_bytes() == DATA
    monkeypatch.setitem(scope, "MAX_RESOURCE_BYTES", 8)
    with pytest.raises(ValueError, match="size"):
        api["stage_tokenizer_cache"](str(tmp_path / "too-large"), cache_dirs=())


def test_bad_download_hash_and_timeout_cannot_publish_bundle(monkeypatch, tmp_path):
    api = helper()
    scope = configure(monkeypatch, api)
    monkeypatch.setattr(
        scope["urllib"].request.OpenerDirector, "open", lambda self, url, timeout: Response(b"bad")
    )
    with pytest.raises(ValueError, match="hash"):
        api["stage_tokenizer_cache"](str(tmp_path / "hash"), cache_dirs=())
    assert not (tmp_path / "hash/fusion-tokenizer-cache").exists()

    def timeout(self, url, timeout):
        raise TimeoutError("public build resource timeout")

    monkeypatch.setattr(scope["urllib"].request.OpenerDirector, "open", timeout)
    with pytest.raises(TimeoutError):
        api["stage_tokenizer_cache"](str(tmp_path / "timeout"), cache_dirs=())
    assert not (tmp_path / "timeout/fusion-tokenizer-cache").exists()


def test_pinned_origins_cover_installed_official_tiktoken_resources():
    from tiktoken_ext import openai_public

    tree = ast.parse(inspect.getsource(openai_public))
    expected = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "load_tiktoken_bpe":
            hashes = [kw.value.value for kw in node.keywords if kw.arg == "expected_hash"]
            expected.add((node.args[0].value, hashes[0]))
        if isinstance(node.func, ast.Name) and node.func.id == "data_gym_to_mergeable_bpe_ranks":
            values = {kw.arg: kw.value.value for kw in node.keywords}
            expected.add((values["vocab_bpe_file"], values["vocab_bpe_hash"]))
            expected.add((values["encoder_json_file"], values["encoder_json_hash"]))
    assert set(helper()["RESOURCES"]) == expected
    assert len(expected) == 6


def test_repeated_build_reuses_only_an_exact_verified_staged_cache(monkeypatch, tmp_path):
    api = helper()
    configure(monkeypatch, api)
    cache = tmp_path / "user-cache"
    cache.mkdir()
    (cache / hashlib.sha1(URL.encode()).hexdigest()).write_bytes(DATA)
    work = str(tmp_path / "build")
    staged = Path(api["stage_tokenizer_cache"](work, cache_dirs=(cache,)))
    assert api["stage_tokenizer_cache"](work, cache_dirs=()) == str(staged)
    (staged / hashlib.sha1(URL.encode()).hexdigest()).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="hash"):
        api["stage_tokenizer_cache"](work, cache_dirs=())


def test_public_resource_redirect_is_rejected_before_contacting_second_origin(
    monkeypatch, tmp_path
):
    from email.message import Message
    from urllib.error import HTTPError
    from urllib.response import addinfourl

    api = helper()
    scope = configure(monkeypatch, api)
    contacted = []

    def response(handler, request):
        contacted.append(request.full_url)
        headers = Message()
        headers["Location"] = "https://127.0.0.1/private-resource"
        result = addinfourl(io.BytesIO(b""), headers, request.full_url, 302)
        result.msg = "Found"
        return result

    monkeypatch.setattr(scope["urllib"].request.HTTPSHandler, "https_open", response)
    with pytest.raises(HTTPError, match="302"):
        api["stage_tokenizer_cache"](str(tmp_path / "build"), cache_dirs=())
    assert contacted == [URL]
    assert not (tmp_path / "build/fusion-tokenizer-cache").exists()
