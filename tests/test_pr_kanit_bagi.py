"""PR beyanlarının kanıt kapısı ve oturumun PR'a bağlanması (P-057).

Ölçüldü (31 Ekim): model "PR'ı açtım" dediğinde turda `gh pr create` çağrısı olup olmadığına
bakılmıyordu; kullanıcı açılmamış PR'ı açılmış sanabiliyordu. Oturum PR'a bağlanmıyor, REPL
durum satırı ve masaüstü bağlı PR'ı göstermiyordu.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core.evidence import ToolUse
from fusion_cli.core.pull_request import PullRequestLink, pr_links_in
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.effects.pull_request import (
    UNVERIFIED_COMMENT,
    UNVERIFIED_CREATE,
    created_pull_requests,
    disclose_unverified_pr,
    session_pull_request,
    unverified_pr_notes,
)
from fusion_cli.memory.factory import null_memory

from .fakes import make_config

URL = "https://github.com/acme/web/pull/42"


def _shell(command: str, output: str, *, ok: bool = True) -> ToolUse:
    return ToolUse(name="run_shell", ok=ok, arguments={"command": command}, output=output)


def test_pr_adresleri_ayristirilir():
    links = pr_links_in(f"Açıldı: {URL} ve yine {URL}; ayrıca https://ghe.local/x/y/pull/7")

    assert links == (
        PullRequestLink("acme/web", 42, URL),
        PullRequestLink("x/y", 7, "https://ghe.local/x/y/pull/7"),
    )


def test_basarili_gh_pr_create_kanit_ve_oturum_bagi_olur():
    uses = (
        ToolUse(
            name="gh", arguments={"args": "pr view 3"}, output="url: https://github.com/a/b/pull/3"
        ),
        _shell("git push -u origin x && gh pr create --title T --body B", f"{URL}\n"),
    )

    assert created_pull_requests(uses) == (PullRequestLink("acme/web", 42, URL),)
    assert session_pull_request(uses) == PullRequestLink("acme/web", 42, URL)
    # Okunan PR, açılan yoksa bağ olur; başarısız create kanıt sayılmaz.
    assert session_pull_request(uses[:1]) == PullRequestLink(
        "a/b", 3, "https://github.com/a/b/pull/3"
    )
    assert created_pull_requests((_shell("gh pr create", URL, ok=False),)) == ()


def test_kanitsiz_pr_beyani_not_alir_kanitli_almaz():
    claim = "Değişiklikleri push ettim ve PR'ı açtım: #42."
    english = "I have opened a pull request for the fix."

    assert unverified_pr_notes(claim, ()) == (UNVERIFIED_CREATE,)
    assert unverified_pr_notes(english, ()) == (UNVERIFIED_CREATE,)
    assert unverified_pr_notes(claim, (_shell("gh pr create -f", URL),)) == ()
    assert unverified_pr_notes("PR açmak için /pr yaz.", ()) == ()
    assert unverified_pr_notes("PR'a yorum yazdım.", ()) == (UNVERIFIED_COMMENT,)
    assert unverified_pr_notes("PR'a yorum yazdım.", (_shell("gh pr comment 4 -b x", "ok"),)) == ()


def test_not_cevaba_bir_kez_eklenir():
    outcome = AgentOutcome(final_text="PR oluşturuldu.", messages=[], ok=True)

    disclose_unverified_pr(outcome)
    disclose_unverified_pr(outcome)

    assert outcome.final_text.count(UNVERIFIED_CREATE) == 1


def test_oturum_bagi_korunur_ve_durum_satirinda_gorunur(tmp_path: Path):
    from fusion_cli.cli.repl.loop import _sync_status_bar

    state = ReplState(config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path)
    link = PullRequestLink("acme/web", 42, URL)
    state.bind_pull_request(link)
    state.bind_pull_request(None)  # PR'sız tur bağı silmez
    reader = SimpleNamespace(context="")

    _sync_status_bar(reader, state)  # type: ignore[arg-type]

    assert state.linked_pr == link
    assert reader.context.endswith("PR #42")


async def test_masaustu_tur_sonrasi_pr_oturum_durumunda(tmp_path: Path, monkeypatch):
    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession
    from fusion_cli.cli import session as cli_session

    from .test_appserver_session import _sonuc

    async def _sahte(_task, _config, **kwargs):
        return AgentOutcome(
            final_text="PR açıldı",
            messages=[],
            ok=True,
            tool_uses=(_shell("gh pr create --fill", URL),),
        )

    monkeypatch.setattr(cli_session, "run_agent_task", _sahte)
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")

    await oturum.handle(Request(id="1", name="oturum.durum", data={}))
    assert _sonuc(satirlar, "1")["pr"] is None
    await oturum.handle(Request(id="2", name="tur.calistir", data={"gorev": "PR aç"}))
    await oturum.handle(Request(id="3", name="oturum.durum", data={}))

    assert _sonuc(satirlar, "3")["pr"] == {"numara": 42, "url": URL, "depo": "acme/web"}
    await oturum.close()
