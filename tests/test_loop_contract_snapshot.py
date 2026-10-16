"""E35 ayrıştırması: mevcut araç/onarım mesajlarının davranış özeti değişmez."""

import hashlib
import json

from fusion_cli.engines.agent import loop_contract as contract


def test_contract_helpers_preserve_pre_refactor_snapshot():
    cases = {
        "encode": contract._encode_arguments({"b": 2, "a": "ışık"}),
        "parse": contract._parse_arguments_checked('{"x":1}'),
        "parse_invalid": contract._parse_arguments_checked("[]"),
        "failure": contract._failure_signature(
            "(çıkış kodu 1)\n[stderr]\nError: missing file\nmore"
        ),
        "duplicate": contract._duplicate_call_message(),
        "abort": contract._tool_contract_abort_message("bad args"),
        "correction": contract._correction_task("Eksik çıktı"),
        "contract": contract._tool_contract_failure("tool", ["bad args"], None),
    }
    digest = hashlib.sha256(
        json.dumps(cases, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    assert digest == "e67e0eceae3efc4a04a9d9bf69b25c995be03c2c1aa6cc36222650c15de37612"
