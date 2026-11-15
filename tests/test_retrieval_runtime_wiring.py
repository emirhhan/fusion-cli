"""Deneysel arama ayarları gerçek yapılandırmadan indeks ve agent bağlamına ulaşır."""

from __future__ import annotations

from dataclasses import fields, replace

import pytest
import yaml

from fusion_cli.config import loader
from fusion_cli.config.paths import bundled_defaults
from fusion_cli.core.errors import ConfigError
from fusion_cli.core.events import RepoMapBuilt
from fusion_cli.memory import factory

from .fakes import RecordingSink, ScriptedProvider, model_result
from .test_agent_loop import TAM_CEVAP, _deps, _kur
from .test_hybrid_retrieval import LocalRetrievalEmbedding, local_retrieval_project

_PROSE_TASK = (
    "Bu projede kullanıcı oturumu kapanırken oluşan hata için mevcut akışı ve kayıt "
    "mantığını dikkatlice kontrol ederek `FocusTarget` fonksiyonunu düzelt."
)


@pytest.fixture
def typed_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(loader, "load_environment", lambda: None)

    def build(**runtime):
        path = tmp_path / "config.yaml"
        path.write_text(yaml.safe_dump({"runtime": runtime}), encoding="utf-8")
        config = loader.load_config(path)
        return replace(config, memory_dir=tmp_path / "memory")

    return build


def test_typed_retrieval_defaults_keep_existing_product_behavior(typed_config):
    runtime = typed_config().runtime
    assert runtime.code_lexical_candidates == 0
    assert runtime.code_chunk_strategy == "lines"
    assert runtime.repo_map_focused is False
    bundled = yaml.safe_load(bundled_defaults().read_text(encoding="utf-8"))["runtime"]
    defaults = {field.name: field.default for field in fields(runtime)}
    for name in ("code_lexical_candidates", "code_chunk_strategy", "repo_map_focused"):
        assert defaults[name] == bundled[name] == getattr(runtime, name)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("code_lexical_candidates", -1),
        ("code_lexical_candidates", True),
        ("code_lexical_candidates", 1.5),
        ("code_chunk_strategy", "symbol"),
        ("code_chunk_strategy", "unknown"),
        ("repo_map_focused", "true"),
    ],
)
def test_typed_retrieval_config_rejects_invalid_values(typed_config, field, value):
    with pytest.raises(ConfigError, match=field):
        typed_config(**{field: value})


def test_typed_config_enables_lexical_union_in_real_factory_index(
    tmp_path, monkeypatch, typed_config
):
    monkeypatch.setattr(
        factory, "build_embedding_function", lambda *a, **k: (LocalRetrievalEmbedding(), "")
    )
    root = local_retrieval_project(tmp_path / "project")
    baseline = factory.build_memory(typed_config(), root=root)
    assert baseline.enabled
    baseline.code_index.reindex()
    assert all(
        match.path != "target00.py"
        for match in baseline.code_index.search("UnicornDispatch00", limit=5)
    )
    enabled = factory.build_memory(typed_config(code_lexical_candidates=4), root=root)
    assert enabled.code_index.search("UnicornDispatch00", limit=5)[0].path == "target00.py"
    explicit = factory.build_memory(
        typed_config(code_lexical_candidates=4), root=root, code_lexical_candidates=0
    )
    assert all(
        match.path != "target00.py"
        for match in explicit.code_index.search("UnicornDispatch00", limit=5)
    )


def test_typed_config_symbol_strategy_changes_real_factory_index_chunks(
    tmp_path, monkeypatch, typed_config
):
    monkeypatch.setattr(
        factory, "build_embedding_function", lambda *a, **k: (LocalRetrievalEmbedding(), "")
    )
    root = tmp_path / "project"
    root.mkdir()
    (root / "handlers.py").write_text(
        "def first_handler():\n    return 1\n\ndef second_handler():\n    return 2\n",
        encoding="utf-8",
    )
    symbols = factory.build_memory(typed_config(code_chunk_strategy="symbols"), root=root)
    assert symbols.code_index.reindex().added == 2
    matches = symbols.code_index.search("second_handler")
    assert {(match.start_line, match.end_line) for match in matches} == {(1, 2), (4, 5)}
    assert all("first_handler" not in match.snippet for match in matches if match.start_line == 4)
    lines = factory.build_memory(
        typed_config(code_chunk_strategy="symbols"), root=root, code_chunk_strategy="lines"
    )
    assert lines.code_index.search("second_handler") == ()
    assert lines.code_index.reindex().added == 1
    assert "first_handler" in lines.code_index.search("second_handler")[0].snippet


@pytest.fixture
def map_project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    for path, symbol in (
        ("a_general.py", "common"),
        ("z_target.py", "FocusTarget"),
        ("zz_other.py", "OtherTarget"),
    ):
        (root / path).write_text(f"def {symbol}():\n    return 1\n", encoding="utf-8")
    return root


async def test_actual_agent_task_focus_changes_map_and_retains_discovery(
    tmp_path, monkeypatch, typed_config, map_project
):
    from fusion_cli.engines.agent.loop import run_agent

    async def map_for(task, focused):
        provider = _kur(monkeypatch, ScriptedProvider([model_result(TAM_CEVAP)]))
        sink = RecordingSink()
        deps = _deps(map_project, sink, home=tmp_path / "home")
        config = typed_config(
            repo_map_chars=600, **({"repo_map_focused": focused} if focused is not None else {})
        )
        deps = replace(
            deps,
            config=replace(
                deps.config,
                runtime=replace(
                    deps.config.runtime,
                    repo_map_focused=config.runtime.repo_map_focused,
                    repo_map_chars=config.runtime.repo_map_chars,
                    project_instructions=False,
                ),
            ),
        )
        await run_agent(task, deps)
        system_text = "\n".join(
            message.content for message in provider.seen_messages[0] if message.role == "system"
        )
        map_text = system_text.split("# Depo haritası", 1)[1]
        map_events = [event for event in sink.events if isinstance(event, RepoMapBuilt)]
        assert len(map_events) == 1
        assert "RAW_TASK_SENTINEL" not in repr(map_events)
        assert task not in repr(map_events)
        assert "FocusTarget" not in repr(map_events)
        assert map_events[0].budget_chars == 600
        return map_text

    disabled = await map_for("z_target.py RAW_TASK_SENTINEL", False)
    assert disabled.index("a_general.py: common") < disabled.index("z_target.py: FocusTarget")
    by_path = await map_for("z_target.py RAW_TASK_SENTINEL", True)
    assert by_path.index("z_target.py: FocusTarget") < by_path.index("a_general.py: common")
    by_symbol = await map_for("OtherTarget RAW_TASK_SENTINEL", True)
    assert by_symbol.index("zz_other.py: OtherTarget") < by_symbol.index("a_general.py: common")
    assert "z_target.py: FocusTarget" in by_symbol
    prose_default = await map_for(_PROSE_TASK, None)
    assert prose_default.index("a_general.py: common") < prose_default.index(
        "z_target.py: FocusTarget"
    )
    prose_disabled = await map_for(_PROSE_TASK, False)
    assert prose_disabled.index("a_general.py: common") < prose_disabled.index(
        "z_target.py: FocusTarget"
    )
    prose_focused = await map_for(_PROSE_TASK, True)
    assert prose_focused.index("z_target.py: FocusTarget") < prose_focused.index(
        "a_general.py: common"
    )
    assert "zz_other.py: OtherTarget" in prose_focused
    general = await map_for("Bu projeyi dikkatlice incele.", True)
    assert general.index("a_general.py: common") < general.index("z_target.py: FocusTarget")


def test_task_focus_rejects_root_escape_and_bounds_untrusted_input(tmp_path):
    from fusion_cli.engines.agent.repo_context import task_focus

    root = tmp_path / "project"
    root.mkdir()
    (root / "escape").symlink_to(tmp_path, target_is_directory=True)
    focus = task_focus(
        root,
        f"../outside.py {tmp_path}/outside.py escape/outside.py "
        f"`./src/inside.py:12:2` {root}/src/also.py `KnownSymbol`",
    )
    assert focus.paths == ("src/inside.py", "src/also.py")
    assert focus.symbols == ("KnownSymbol",)
    bounded = task_focus(root, " ".join(f"file{number}.py" for number in range(1000)))
    assert len(bounded.paths) <= 16
    assert len(bounded.symbols) <= 16
    assert task_focus(root, " " * 8192 + "late.py LateSymbol").paths == ()
    assert task_focus(root, " " * 8192 + "late.py LateSymbol").symbols == ()


@pytest.mark.parametrize(
    "symbol", ["`FocusTarget`", "`handler`", "FocusTarget", "last_handler", "dispatch()"]
)
def test_task_focus_prioritizes_code_symbols_over_prose_with_same_bounds(tmp_path, symbol):
    from fusion_cli.engines.agent.repo_context import task_focus

    prose = " ".join(f"word{number}" for number in range(30))
    focus = task_focus(tmp_path, f"{prose} {symbol}")
    assert focus.symbols[0] == symbol.strip("`()")
    assert len(focus.symbols) == 16
    assert focus.paths == ()
    token_limit = " ".join(f"word{number}" for number in range(128))
    assert task_focus(tmp_path, f"{token_limit} `LateSymbol`").symbols == tuple(
        f"word{number}" for number in range(16)
    )


def test_task_focus_promotes_duplicate_prose_symbol_and_keeps_explicit_quota(tmp_path):
    from fusion_cli.engines.agent.repo_context import task_focus

    prose = " ".join(f"word{number}" for number in range(30))
    promoted = task_focus(tmp_path, f"word0 handler {prose} `handler`")
    assert promoted.symbols[0] == "handler"
    assert promoted.symbols.count("handler") == 1
    assert len(promoted.symbols) == 16
    explicit = " ".join(f"`symbol{number}`" for number in range(30))
    assert task_focus(tmp_path, explicit).symbols == tuple(
        f"symbol{number}" for number in range(16)
    )
