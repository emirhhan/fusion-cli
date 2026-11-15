"""Yerel ses protokolünü model indirmeden ve MLX yüklemeden doğrula."""

from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "speech_worker", Path(__file__).with_name("kits-speech-worker.py")
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SpeechProtocolTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.calls = []

        def synthesize(text, output):
            self.calls.append(text)
            output.write_bytes(b"RIFF-test-audio")

        self.worker = module.SpeechWorker(synthesize, Path(self.directory.name), 100)
        self.addCleanup(self.worker.close)

    def test_produces_owned_file_and_release_is_idempotent(self):
        result = self.worker.handle(
            {"id": "../../outside", "action": "synthesize", "text": "Merhaba"}
        )
        self.assertTrue(result["ok"])
        self.assertEqual(Path(result["path"]).parent, Path(self.directory.name))
        self.assertEqual(self.calls, ["Merhaba"])
        self.assertFalse(
            self.worker.handle({"id": "next", "action": "synthesize", "text": "Yeni"})[
                "ok"
            ]
        )
        self.assertTrue(
            self.worker.handle({"id": "../../outside", "action": "release"})["released"]
        )
        self.assertFalse(Path(result["path"]).exists())
        self.assertFalse(
            self.worker.handle({"id": "../../outside", "action": "release"})["released"]
        )

    def test_bad_input_does_not_reach_engine(self):
        for request in [
            None,
            {},
            {"id": "x", "action": "synthesize", "text": " "},
            {"id": "x", "action": "synthesize", "text": "a" * 101},
        ]:
            self.assertFalse(self.worker.handle(request)["ok"])
        self.assertEqual(self.calls, [])

    def test_failed_generation_cleans_partial_file(self):
        def failing(text, output):
            output.write_bytes(b"partial")
            raise RuntimeError("Motor başarısız")

        self.worker.synthesize = failing
        self.assertFalse(
            self.worker.handle({"id": "x", "action": "synthesize", "text": "Merhaba"})[
                "ok"
            ]
        )
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_deep_json_is_visible_error_and_next_request_survives(self):
        source = io.StringIO(
            "[" * 2000
            + "0"
            + "]" * 2000
            + "\n"
            + json.dumps({"id": "x", "action": "release"})
            + "\n"
        )
        target = io.StringIO()
        module.serve(self.worker, source, target)
        results = [json.loads(line) for line in target.getvalue().splitlines()]
        self.assertFalse(results[0]["ok"])
        self.assertTrue(results[1]["ok"])

    def test_oversized_line_is_rejected_and_next_request_survives(self):
        source = io.StringIO(
            "x" * (module.MAX_REQUEST_CHARS + 10)
            + "\n"
            + json.dumps({"id": "x", "action": "release"})
            + "\n"
        )
        target = io.StringIO()
        module.serve(self.worker, source, target)
        results = [json.loads(line) for line in target.getvalue().splitlines()]
        self.assertFalse(results[0]["ok"])
        self.assertTrue(results[1]["ok"])

    def test_json_error_is_visible_and_eof_cleans_files(self):
        source = io.StringIO(
            "bad\n"
            + json.dumps({"id": "x", "action": "synthesize", "text": "Merhaba"})
            + "\n"
        )
        target = io.StringIO()
        module.serve(self.worker, source, target)
        results = [json.loads(line) for line in target.getvalue().splitlines()]
        self.assertFalse(results[0]["ok"])
        self.assertTrue(results[1]["ok"])
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
