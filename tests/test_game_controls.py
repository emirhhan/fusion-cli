"""Real browser measurement of requested visible game controls."""

import pytest

from fusion_cli.tools.game_controls import pause_button_problems, requires_pause_button


@pytest.mark.parametrize("task", ["Başlat/duraklat düğmeleri olsun.", "Include a pause button."])
def test_explicit_request(task):
    assert requires_pause_button(task)


async def test_keyboard_only_or_hidden_button_cannot_satisfy_visible_requirement():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(
            '<button style="display:none">Duraklat</button><p>Esc ile duraklat</p>'
        )
        assert await pause_button_problems(page)
        await page.set_content('<button aria-label="Oyunu duraklat">⏸</button>')
        assert await pause_button_problems(page) == ()
        await page.set_content("<button disabled>Pause</button>")
        assert await pause_button_problems(page)
        for style in ("opacity:0", "visibility:hidden", "display:none"):
            await page.set_content(f'<div style="{style}"><button>Pause</button></div>')
            assert await pause_button_problems(page)
        await page.set_content('<button style="opacity:0">Pause</button>')
        assert await pause_button_problems(page)
        await browser.close()


@pytest.mark.parametrize(
    "task",
    [
        "Oyunda duraklatma düğmesine gerek yok.",
        "The pause button is not needed.",
        "The pause button is optional.",
        'Oyun yardımına "Add a pause button" yaz.',
        "Oyun yap. `Include a pause button.`",
    ],
)
def test_optional_negative_and_quoted_text_is_not_a_requirement(task):
    assert not requires_pause_button(task)


def test_negative_token_is_not_a_word_suffix():
    assert requires_pause_button("Piyano oyunu için duraklat düğmesi ekle.")


@pytest.mark.parametrize(
    "task",
    [
        "Oyuna duraklat düğmesi ekleme.",
        "Duraklat düğmesi eklemeyin.",
        "Duraklat düğmesi sağlama.",
        "Duraklat düğmesi sağlamayın.",
    ],
)
def test_turkish_negative_imperative_does_not_match_affirmative_stem(task):
    assert not requires_pause_button(task)


async def test_real_pause_click_and_resume_detect_disconnected_buttons():
    from playwright.async_api import async_playwright

    from fusion_cli.tools.game_controls import pause_button_behavior

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content("""<button>Pause</button><script>
        window.__GAME_STATE__=()=>({state:'playing'});</script>""")
        problems, warnings = await pause_button_behavior(page)
        assert problems and not warnings
        await page.set_content("""<button id=p
        onclick="paused=true;this.hidden=true;r.hidden=false">Pause</button>
        <button id=r hidden onclick="paused=false;this.hidden=true;p.hidden=false">Resume</button>
        <script>let paused=false;window.__GAME_STATE__=()=>({paused, running:true});</script>""")
        assert await pause_button_behavior(page) == ((), ())
        assert await page.evaluate("window.__GAME_STATE__().paused") is False
        await page.set_content("<button>Pause</button>")
        # set_content keeps the old global object; remove it for a genuinely unknown hook.
        await page.evaluate("delete window.__GAME_STATE__")
        problems, warnings = await pause_button_behavior(page)
        assert not problems and warnings
        await browser.close()


async def test_actual_play_probe_tool_surfaces_owned_pause_requirement(tmp_path, monkeypatch):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.delivery_contract import accept_delivery_contract
    from fusion_cli.engines.agent.web_tools import run_play_probe
    from fusion_cli.tools import play_probe
    from fusion_cli.tools.play_probe import ProbeReport

    (tmp_path / "index.html").write_text("<canvas></canvas>")
    context = ToolContext(root=tmp_path, task_kinds={"oyun"})
    accept_delivery_contract(context, "Başlat/duraklat düğmeleri olsun.")
    seen = []

    async def probe(url, keys, **kwargs):
        seen.append(kwargs)
        return ProbeReport((), 60, "{}", "{}", True, None, control_problems=("NO_PAUSE_HANDLER",))

    monkeypatch.setattr(play_probe, "probe_game", probe)
    result = await run_play_probe({"target": "index.html"}, context)
    assert seen[0]["require_pause_button"] is True
    assert not result.ok and "NO_PAUSE_HANDLER" in result.output


async def test_transparent_duplicates_cannot_override_visible_working_pause_and_resume():
    from playwright.async_api import async_playwright

    from fusion_cli.tools.game_controls import pause_button_behavior

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content("""<button style="opacity:0">Pause</button>
        <button id=p onclick="paused=true;this.hidden=true;r.hidden=false">Pause</button>
        <button style="opacity:0">Resume</button>
        <button id=r hidden onclick="paused=false;this.hidden=true;p.hidden=false">Resume</button>
        <script>var paused=false;window.__GAME_STATE__=()=>({paused,running:true});</script>""")
        assert await pause_button_behavior(page) == ((), ())
        await browser.close()


async def test_unrelated_continue_control_does_not_suppress_working_toggle_fallback():
    from playwright.async_api import async_playwright

    from fusion_cli.tools.game_controls import pause_button_behavior

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content("""<button onclick="paused=!paused">Pause</button>
        <button>Continue tutorial</button>
        <script>var paused=false;window.__GAME_STATE__=()=>({paused,running:true});</script>""")
        assert await pause_button_behavior(page) == ((), ())
        await browser.close()


async def test_unknown_hook_never_pauses_game_before_later_gameplay_probes():
    from playwright.async_api import async_playwright

    from fusion_cli.tools.game_controls import pause_button_behavior

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content('<button onclick="window.paused=true">Pause</button>')
        problems, warnings = await pause_button_behavior(page)
        assert not problems and warnings
        assert await page.evaluate("window.paused===true") is False
        await browser.close()


async def test_visible_children_override_hidden_parent_for_real_pause_and_resume():
    from playwright.async_api import async_playwright

    from fusion_cli.tools.game_controls import pause_button_behavior

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.route("**/*", lambda route: route.abort())
        await page.set_content("""<div style="visibility:hidden">
        <button id=p style="visibility:visible"
          onclick="paused=true;pauseClicks++;this.hidden=true;r.hidden=false">Pause</button>
        <button id=r hidden style="visibility:visible"
          onclick="paused=false;resumeClicks++;this.hidden=true;p.hidden=false">Resume</button>
        </div><script>
        var paused=false,pauseClicks=0,resumeClicks=0;
        window.__GAME_STATE__=()=>({paused,running:true});
        </script>""")
        pause = page.get_by_role("button", name="Pause", exact=True)
        resume = page.get_by_role("button", name="Resume", exact=True)
        assert await pause.is_visible()
        # Independently prove that CSS makes the overriding child clickable.
        await pause.click()
        assert await page.evaluate("paused") is True
        await resume.click()
        assert await page.evaluate("paused") is False
        assert await pause_button_problems(page) == ()
        assert await pause_button_behavior(page) == ((), ())
        assert await page.evaluate("[paused,pauseClicks,resumeClicks]") == [False, 2, 2]
        await browser.close()


@pytest.mark.parametrize(
    ("parent", "button", "overlay"),
    [
        ('style="visibility:hidden"', "", ""),
        ('style="opacity:0"', 'style="visibility:visible"', ""),
        ('style="display:none"', 'style="visibility:visible"', ""),
        ("inert", 'style="visibility:visible"', ""),
        ("", "disabled", ""),
        ("", "", '<div style="position:fixed;inset:0;z-index:10"></div>'),
    ],
    ids=[
        "inherited-hidden",
        "transparent-parent",
        "display-none-parent",
        "inert-parent",
        "disabled",
        "occluded",
    ],
)
async def test_visibility_override_fix_keeps_non_actionable_controls_rejected(
    parent, button, overlay
):
    from playwright.async_api import async_playwright

    from fusion_cli.tools.game_controls import pause_button_behavior

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.route("**/*", lambda route: route.abort())
        await page.set_content(f"""<div {parent}>
        <button {button} onclick="window.pauseClicks++">Pause</button></div>{overlay}
        <script>window.pauseClicks=0;window.__GAME_STATE__=()=>({{state:'playing'}});</script>""")
        assert await pause_button_problems(page)
        problems, warnings = await pause_button_behavior(page)
        assert problems and not warnings
        assert await page.evaluate("window.pauseClicks") == 0
        await browser.close()


async def test_delayed_pause_and_resume_are_observed_within_measurement_window():
    from playwright.async_api import async_playwright

    from fusion_cli.tools.game_controls import pause_button_behavior

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.route("**/*", lambda route: route.abort())
        await page.set_content("""<button
        onclick="pauseClicks++;setTimeout(()=>paused=true,250)">Pause</button>
        <button onclick="resumeClicks++;setTimeout(()=>paused=false,250)">Resume</button>
        <script>var paused=false,pauseClicks=0,resumeClicks=0;
        window.__GAME_STATE__=()=>({paused,running:true});</script>""")
        assert await pause_button_behavior(page) == ((), ())
        assert await page.evaluate("[paused,pauseClicks,resumeClicks]") == [False, 1, 1]
        await browser.close()


async def test_known_noop_pause_is_still_a_bounded_measurement_failure():
    from playwright.async_api import async_playwright

    from fusion_cli.tools.game_controls import pause_button_behavior

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.route("**/*", lambda route: route.abort())
        await page.set_content("""<button onclick="pauseClicks++">Pause</button>
        <script>var pauseClicks=0;window.__GAME_STATE__=()=>({state:'playing'});</script>""")
        problems, warnings = await pause_button_behavior(page)
        assert problems and not warnings
        assert "ölçüm" in problems[0].lower()
        assert await page.evaluate("pauseClicks") == 1
        await browser.close()


async def test_known_resume_failure_remains_a_bounded_measurement_finding():
    from playwright.async_api import async_playwright

    from fusion_cli.tools.game_controls import pause_button_behavior

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.route("**/*", lambda route: route.abort())
        await page.set_content("""<button onclick="pauseClicks++;paused=true">Pause</button>
        <button onclick="resumeClicks++">Resume</button>
        <script>var paused=false,pauseClicks=0,resumeClicks=0;
        window.__GAME_STATE__=()=>({paused,running:true});</script>""")
        problems, warnings = await pause_button_behavior(page)
        assert problems and not warnings
        assert "ölçüm" in problems[0].lower()
        assert await page.evaluate("[paused,pauseClicks,resumeClicks]") == [True, 2, 1]
        await browser.close()


async def test_late_resume_transitions_cannot_renew_the_global_probe_deadline():
    import asyncio

    from playwright.async_api import async_playwright

    from fusion_cli.tools.game_controls import pause_button_behavior

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.route("**/*", lambda route: route.abort())
        await page.set_content("""<button onclick="pauseClicks++;paused=true">Pause</button>
        <button onclick="resumeClicks++;setTimeout(()=>paused=false,5000)">Resume A</button>
        <button onclick="resumeClicks++;setTimeout(()=>paused=false,5000)">Resume B</button>
        <button onclick="resumeClicks++;setTimeout(()=>paused=false,5000)">Resume C</button>
        <button onclick="resumeClicks++;setTimeout(()=>paused=false,5000)">Resume D</button>
        <script>var paused=false,pauseClicks=0,resumeClicks=0;
        window.__GAME_STATE__=()=>({paused,running:true});</script>""")
        async with asyncio.timeout(5):
            problems, warnings = await pause_button_behavior(page)
        assert not problems and warnings
        assert await page.evaluate("paused") is True
        assert await page.evaluate("pauseClicks") == 1
        await browser.close()


@pytest.mark.parametrize("pause_delay", [0, 250], ids=["immediate", "delayed"])
async def test_transient_auto_pause_cannot_prove_a_noop_resume_handler(pause_delay):
    from playwright.async_api import async_playwright

    from fusion_cli.tools.game_controls import pause_button_behavior

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.route("**/*", lambda route: route.abort())
        await page.set_content(f"""<button onclick="pauseClicks++;setTimeout(()=>{{
          paused=true;setTimeout(()=>paused=false,70);
        }},{pause_delay})">Pause</button>
        <button onclick="resumeClicks++">Resume</button>
        <script>var paused=false,pauseClicks=0,resumeClicks=0;
        window.__GAME_STATE__=()=>({{paused,running:true}});</script>""")
        problems, warnings = await pause_button_behavior(page)
        assert problems and not warnings
        assert await page.evaluate("[paused,pauseClicks,resumeClicks]") == [False, 1, 0]
        await browser.close()


async def test_phase_first_seen_at_transition_cap_is_unverified_without_settling(monkeypatch):
    from types import SimpleNamespace

    from fusion_cli.tools import game_controls

    clock = [0.0]

    class Page:
        async def evaluate(self, _):
            return "paused" if clock[0] >= 0.95 else "playing"

    async def sleep(delay):
        clock[0] += delay

    monkeypatch.setattr(
        game_controls.asyncio, "get_running_loop", lambda: SimpleNamespace(time=lambda: clock[0])
    )
    monkeypatch.setattr(game_controls.asyncio, "sleep", sleep)
    assert await game_controls._observe_phase(Page(), "paused") == "unknown"
    assert clock[0] <= 1.0


async def test_delayed_transient_resume_phase_cannot_prove_restoration():
    from playwright.async_api import async_playwright

    from fusion_cli.tools.game_controls import pause_button_behavior

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.route("**/*", lambda route: route.abort())
        await page.set_content("""<button onclick="pauseClicks++;paused=true">Pause</button>
        <button onclick="resumeClicks++;setTimeout(()=>{
          paused=false;setTimeout(()=>paused=true,70);
        },250)">Resume</button>
        <script>var paused=false,pauseClicks=0,resumeClicks=0;
        window.__GAME_STATE__=()=>({paused,running:true});</script>""")
        problems, warnings = await pause_button_behavior(page)
        assert problems and not warnings
        assert await page.evaluate("[paused,pauseClicks,resumeClicks]") == [True, 2, 1]
        await browser.close()
