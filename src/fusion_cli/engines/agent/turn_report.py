"""Tur raporu: başarı beyanı gerçek araç kaydına ve komut çıktısına bağlanır.

Ölçülen sorun: agent "tüm testler geçti" ya da "hiçbir dosya değiştirmedim"
diyebiliyordu ve bu cümle modelin kendi beyanıydı — gerçek değişiklik kaydına
(`ChangeSet`) ya da gerçekten çalışan bir komuta bakılmıyordu. Bu modül modelin
sözünü değil, turda GERÇEKTEN dokunulan dosyaları ve GERÇEKTEN çalışan kabuk
komutlarının çıkış kodunu okur.

Saf modül: ağır bağımlılık yok, yalnızca `ToolUse`/`VerificationResult`
tiplerini, `core.tools.tool_family` sınıflandırmasını ve
`verify_discovery.is_behavioral_command` sınıflandırıcısını tüketir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ...core.evidence import ToolUse
from ...core.tools import ToolFamily, tool_family
from ...core.verification import VerificationResult
from .verify_discovery import is_behavioral_command

#: Kabuk komutu çalıştıran KANONİK araç adı — yalnız görüntüleme/dokümantasyon
#: amaçlı. Bir çağrının kabuk aracı OLUP OLMADIĞI artık bu sabitle birebir
#: string karşılaştırmasıyla değil `_is_shell_call` ile (bkz. aşağı) tespit
#: edilir.
RUN_SHELL_TOOL = "run_shell"


def _is_shell_call(name: str) -> bool:
    """Bu çağrı `run_shell`'in KENDİSİ ya da bir takma adı mı.

    Ölçülen hata (masaüstü uygulaması, API model): model `run_shell`'i
    `bash` takma adıyla çağırdı (bkz. `tools/builtin.py::_ALIASES`) — komut
    onaylandı, sıfır çıkış koduyla bitti, ama rapor `use.name == "run_shell"`
    birebir karşılaştırmasında `"bash" != "run_shell"` olduğu için bu çağrıyı
    HİÇ GÖRMEDİ ve "doğrulama komutu çalıştırılmadı" dedi — komut gerçekten
    çalışmışken.

    Takma ad listesi burada YİNELENMEZ: `core.tools.tool_family` zaten TEK
    KAYNAK olarak `run_shell`/`shell`/`bash`/`execute_command` adlarının
    tümünü `ToolFamily.SHELL` altında topluyor (aynı liste onay ve araç ailesi
    sınıflandırmasında da kullanılıyor); ikinci bir takma ad listesi açmak
    RULES "aynı işi yapan ikinci bir yol açılmaz" ilkesini ihlal ederdi.
    """
    return tool_family(name) is ToolFamily.SHELL


#: `run_shell` çıktısının başındaki çıkış kodu öneki — TEK KAYNAK (`tools/shell.py`
#: ile aynı biçim). Üreten taraf değiştirilirse bu sabit de güncellenmelidir.
_EXIT_CODE_PREFIX = "(çıkış kodu "

_NO_CHANGE_CLAIMS = re.compile(
    r"(?:hiçbir|herhangi bir) dosya(?:da|yı|yı\s+doğrudan)?\s+"
    r"(?:değiştir(?:medim|emedim)|düzenle(?:medim|yemedim))"
    r"|dosya(?:da|larda)?\s+değişiklik\s+yap(?:madım|amadım)"
    r"|(?:no files? (?:was|were) (?:changed|modified)"
    r"|i (?:did not|could not) (?:change|edit) files?)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class CommandRun:
    """Turda denenen tek `run_shell` çağrısının doğrulama açısından kaydı."""

    command: str
    #: Çıkış kodu okunabildiyse; okunamadıysa (zaman aşımı, ayrıştırılamayan
    #: çıktı) `None` — bu bir başarı KANITI değildir.
    exit_code: int | None
    #: Bu komut, turdaki SON dosya mutasyonundan SONRA mı çalıştı?
    #:
    #: Sıra önemlidir: mutasyondan ÖNCE geçen bir test, o mutasyonu kanıtlamaz.
    after_last_mutation: bool


@dataclass(frozen=True, slots=True)
class TurnReport:
    """Bir turun (ya da bir plan yürütmesinin) doğrulanabilir özeti."""

    changed_paths: tuple[str, ...] = ()
    command_runs: tuple[CommandRun, ...] = ()
    #: Deterministik kalite kapısının (ruff/mypy/verifier) sonucu; yoksa `None`.
    gate: VerificationResult | None = None
    #: Çok dosyalı uzun kod görevinde son değişiklikten sonra davranış kanıtı zorunludur.
    require_behavioral_evidence: bool = False

    @property
    def _behavioral_evidence(self) -> tuple[CommandRun, ...]:
        """Son mutasyondan SONRA çalışan, davranışı KANITLAYAN komutlar."""
        return tuple(
            run
            for run in self.command_runs
            if run.after_last_mutation and is_behavioral_command(run.command)
        )

    @property
    def is_verified(self) -> bool | None:
        """`None` = değişiklik yok, sorulacak bir şey yok.

        Değişiklik varsa: son mutasyondan sonra çalışan davranış kanıtı YOKSA
        veya kanıtlardan biri başarısızsa `False`; hepsi başarılıysa `True`.
        """
        if not self.changed_paths:
            return None
        evidence = self._behavioral_evidence
        if not evidence:
            return False
        return all(run.exit_code == 0 for run in evidence)

    @property
    def blocks_success(self) -> bool:
        """Turu BAŞARISIZ ilan etmeyi gerektiren somut bir kanıt var mı.

        Basit değişikliklerde eksik kanıt uyarıdır. Uzun kod görevinde son
        değişiklikten sonra test yoksa başarı iddiası için gereken kanıt eksiktir.
        """
        if self.gate is not None and not self.gate.ok:
            return True
        if self.require_behavioral_evidence and self.is_verified is False:
            return True
        return any(run.exit_code not in (None, 0) for run in self._behavioral_evidence)

    def render(self) -> str:
        """Türkçe, kısa bir rapor metni üret; değişiklik yoksa boş döner (D4)."""
        if not self.changed_paths:
            return ""
        blocks = [*self._gate_blocks(), self._evidence_block()]
        return "\n\n".join(block for block in blocks if block) + "\n\n"

    def render_with_model_text(self, model_text: str) -> str:
        """Eksik veya başarısız kanıtta modelin özeti doğrulanmış gibi görünmesin."""
        report = self.render()
        if not report:
            return model_text
        if self.changed_paths and _NO_CHANGE_CLAIMS.search(model_text):
            return (
                report + "⚠ Ajanın dosya değişikliği beyanı araç kaydıyla çeliştiği için "
                "açıklaması gösterilmedi."
            )
        if self.is_verified is False and model_text.strip():
            return report + "Ajanın açıklaması (doğrulanmamış):\n\n" + model_text
        return report + model_text

    def _gate_blocks(self) -> tuple[str, ...]:
        gate = self.gate
        if gate is None:
            return ()
        if not gate.ok:
            findings = "\n".join(f"- {finding}" for finding in gate.findings[:5])
            return (
                "⚠ DOĞRULAMA GEÇMEDİ — yapılan değişiklikler projeyi kırıyor olabilir.\n"
                f"{gate.summary}\n{findings}\n"
                "Değişiklikleri gözden geçir; gerekirse `/undo` ile geri al.",
            )
        if gate.has_notes:
            notes = "\n".join(
                (
                    *(f"- [uyarı] {finding}" for finding in gate.warnings[:5]),
                    *(f"- [öneri] {finding}" for finding in gate.advisories[:5]),
                )
            )
            return (f"⚠ Doğrulama notları — işi engellemiyor:\n{notes}",)
        return ()

    def _evidence_block(self) -> str:
        dosyalar = ", ".join(self.changed_paths)
        evidence = self._behavioral_evidence
        if not evidence:
            return (
                f"ⓘ Değişen dosyalar: {dosyalar}\n"
                "Son değişiklikten sonra bir doğrulama komutu ÇALIŞTIRILMADI; "
                "sonuç doğrulanmadı."
            )
        basarisiz = tuple(run for run in evidence if run.exit_code != 0)
        if basarisiz:
            komutlar = "; ".join(f"`{run.command}` (çıkış {run.exit_code})" for run in basarisiz)
            return f"✗ Doğrulama başarısız: {komutlar}\nDeğişen dosyalar: {dosyalar}"
        komutlar = "; ".join(f"`{run.command}`" for run in evidence)
        return f"✓ Doğrulandı: {komutlar} başarıyla çalıştı.\nDeğişen dosyalar: {dosyalar}"


def build_turn_report(
    changed_paths: tuple[str, ...],
    tool_uses: tuple[ToolUse, ...],
    gate: VerificationResult | None,
    *,
    require_behavioral_evidence: bool = False,
) -> TurnReport:
    """Turda denenen araç çağrılarından ve değişiklik kaydından raporu kur."""
    last_mutation = _last_mutation_index(tool_uses)
    command_runs = tuple(
        _command_run(use, after=last_mutation is not None and index > last_mutation)
        for index, use in enumerate(tool_uses)
        if _is_shell_call(use.name)
    )
    return TurnReport(
        changed_paths=changed_paths,
        command_runs=command_runs,
        gate=gate,
        require_behavioral_evidence=require_behavioral_evidence,
    )


def _last_mutation_index(tool_uses: tuple[ToolUse, ...]) -> int | None:
    """Son BAŞARILI dosya mutasyonunun sırası; `run_shell` mutasyon SAYILMAZ.

    `run_shell` onay gerektirdiği için `mutating=True` işaretlidir ama bir dosya
    DEĞİŞTİRDİĞİNİN kanıtı değildir (ör. `pytest -q`). Onu mutasyon sayarsak
    doğrulama komutunun kendisi "son mutasyon" olur ve hiçbir komut ondan SONRA
    saymaz.
    """
    for index in range(len(tool_uses) - 1, -1, -1):
        use = tool_uses[index]
        if use.mutating and use.ok and not _is_shell_call(use.name):
            return index
    return None


def _command_run(use: ToolUse, *, after: bool) -> CommandRun:
    return CommandRun(
        command=_command_text(use), exit_code=_exit_code(use), after_last_mutation=after
    )


def _command_text(use: ToolUse) -> str:
    value = use.arguments.get("command") if isinstance(use.arguments, dict) else None
    return value if isinstance(value, str) else ""


def _exit_code(use: ToolUse) -> int | None:
    """`run_shell` çıktısındaki `(çıkış kodu N)` önekinden çıkış kodunu oku.

    TEK yardımcı: çıkış kodu tespiti burada toplanır, ikinci bir ayrıştırma
    yolu açılmaz (RULES "hata tespiti tek yardımcı fonksiyondan geçer").
    """
    output = use.output
    if not output.startswith(_EXIT_CODE_PREFIX):
        return None
    closing = output.find(")", len(_EXIT_CODE_PREFIX))
    if closing == -1:
        return None
    try:
        return int(output[len(_EXIT_CODE_PREFIX) : closing])
    except ValueError:
        return None
