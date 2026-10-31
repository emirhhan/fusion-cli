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


# --- Bağımsız inceleme düzeltmeleri (31 Ekim) -------------------------------------- #


def test_tool_use_olmayan_ogeler_bagi_dusurmez():
    """Ölçüldü: sahte sonuçtaki `tool_uses=("mutating",)` `AttributeError` ile turu düşürüyordu."""
    uses = ("mutating", _shell("gh pr create -f", URL))

    assert session_pull_request(uses) == PullRequestLink("acme/web", 42, URL)
    assert unverified_pr_notes("PR'ı açtım.", ("mutating",)) == (UNVERIFIED_CREATE,)


def test_okuma_bagi_yalniz_gecerli_depodaki_prin_kendi_adresi():
    """Ölçüldü: çıktıdaki SON adres alınıyordu (gövdedeki 'Fixes …/pull/3' ya da başka depo)."""
    view = _shell(
        "gh pr view 9",
        "title:\tDüzeltme\nurl:\thttps://github.com/acme/web/pull/9\n--\n"
        "Fixes https://github.com/o/r/pull/3",
    )
    other_repo = _shell(
        "gh pr view 5 --repo baska/depo --comments",
        "url:\thttps://github.com/baska/depo/pull/5",
    )

    assert session_pull_request((view,)) == PullRequestLink(
        "acme/web", 9, "https://github.com/acme/web/pull/9"
    )
    assert session_pull_request((other_repo,)) is None
    assert session_pull_request((view, other_repo)) == session_pull_request((view,))


def test_mcp_ve_gh_api_ile_acilan_pr_kanit_sayilir():
    mcp = ToolUse(
        name="github__create_pull_request",
        arguments={"owner": "acme", "repo": "web"},
        output='{"number": 42, "html_url": "' + URL + '"}',
    )
    api = _shell(
        "gh api repos/acme/web/pulls -f title=T -f head=x -f base=main",
        '{"url": "https://api.github.com/repos/acme/web/pulls/43", '
        '"html_url": "https://github.com/acme/web/pull/43"}',
    )
    comment = ToolUse(name="github__add_issue_comment", output="ok")

    assert created_pull_requests((mcp,)) == (PullRequestLink("acme/web", 42, URL),)
    assert created_pull_requests((api,))[0].number == 43
    assert unverified_pr_notes("PR'ı açtım.", (mcp,)) == ()
    assert unverified_pr_notes("PR'a yorum yazdım.", (comment,)) == ()
    # Okuma amaçlı `gh api` (alan/POST yok) oluşturma sayılmaz.
    assert created_pull_requests((_shell("gh api repos/acme/web/pulls", URL),)) == ()


def test_ucuncu_kisi_ve_onceki_is_cumleleri_uyari_uretmez():
    """Ölçüldü: bu üç cümlede eski regex True veriyordu."""
    for text in (
        "PR #5 zaten açıldı.",
        "Dependabot PR #12 opened.",
        "The PR was created by Alice.",
        "PR açmak için /pr yaz.",
    ):
        assert unverified_pr_notes(text, ()) == (), text
    assert unverified_pr_notes("We opened a PR for the fix.", ()) == (UNVERIFIED_CREATE,)


def test_onceki_turdaki_kanit_evet_actim_cevabini_uyarmaz():
    from fusion_cli.core.types import Message, ToolCall

    history = [
        Message("user", "PR aç"),
        Message(
            "assistant",
            "",
            tool_calls=(ToolCall("c1", "run_shell", '{"command": "gh pr create --fill"}'),),
        ),
        Message("tool", URL, tool_call_id="c1", name="run_shell", ok=True),
        Message("user", "PR'ı açtın mı?"),
    ]
    failed = [*history[:2], Message("tool", URL, tool_call_id="c1", name="run_shell", ok=False)]

    assert unverified_pr_notes("Evet, PR'ı açtım.", (), history) == ()
    assert unverified_pr_notes("Evet, PR'ı açtım.", (), failed) == (UNVERIFIED_CREATE,)
