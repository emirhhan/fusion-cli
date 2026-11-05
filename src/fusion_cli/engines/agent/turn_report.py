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

from ...core.artifact_kind import artifact_only
from ...core.constants import (
    EXIT_CODE_PREFIX,
    TOOL_CALL_BLOCKED_PREFIX,
    TOOL_CALL_DUPLICATE_PREFIX,
)
from ...core.evidence import CriterionEvidence, EvidenceStatus, ToolUse, summarize_criteria
from ...core.execution_plan import VerificationCheckKind
from ...core.job_evidence import JobCurrentSnapshot, JobPhase
from ...core.tools import ToolFamily, tool_family
from ...core.verification import UNVERIFIABLE_COMMAND_PREFIX, VerificationResult
from ...ui.text import strip_thinking
from .browser_verify import NOT_MEASURED_PREFIX
from .completion_evidence import evidence_payload as evidence_payload
from .job_delivery import JobDelivery, collect_job_deliveries
from .shell_mutation import shell_may_change_files
from .tamper_check import TamperFinding, has_weakening, render_findings
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


_EXIT_CODE_PREFIX = EXIT_CODE_PREFIX

_NO_CHANGE_CLAIMS = re.compile(
    r"(?:hiçbir|herhangi bir) dosya(?:da|yı|yı\s+doğrudan)?\s+"
    r"(?:değiştir(?:medim|emedim)|düzenle(?:medim|yemedim))"
    r"|dosya(?:da|larda)?\s+değişiklik\s+yap(?:madım|amadım)"
    r"|(?:no files? (?:was|were) (?:changed|modified)"
    r"|i (?:did not|could not) (?:change|edit) files?)",
    re.IGNORECASE,
)


#: İddianın kapsamını daraltan sözcükler: "src/ dışında değişiklik yapmadım" tüm değişikliği
#: inkâr etmez (A4-27), açıklama gizlenmemeli.
_CLAIM_SCOPE_AFTER = re.compile(r"dışında|hariç|outside|except|other than", re.IGNORECASE)
_CLAIM_SCOPE_BEFORE = re.compile(r"(\w+)\s+$")
_GLOBAL_QUALIFIERS = frozenset({"hiçbir", "herhangi", "bir", "no"})


def _claims_no_change(text: str) -> bool:
    """Metin TÜM dosyalarda değişiklik yok diyor mu (kapsamlı iddia sayılmaz).

    Ölçüldü (29 Ekim, A4-27): "config dosyasında değişiklik yapmadım" gibi kapsamlı bir
    cümle eşleşince modelin bütün açıklaması kullanıcıdan saklanıyordu.
    """
    for eslesme in _NO_CHANGE_CLAIMS.finditer(text):
        sonra = text[eslesme.end() : eslesme.end() + 40]
        if _CLAIM_SCOPE_AFTER.search(sonra):
            continue
        onceki = _CLAIM_SCOPE_BEFORE.search(text[max(0, eslesme.start() - 40) : eslesme.start()])
        if onceki is not None and onceki.group(1).casefold() not in _GLOBAL_QUALIFIERS:
            continue
        return True
    return False


#: Modelin "doğruladım" iddiası. Kanıt yokken bu cümleler kullanıcıya gerçek gibi
#: gitmemeli. Ölçüldü (1 Ekim, WordPress sohbeti): hiçbir komut çalışmadan "Tema
#: dosyaları tamamlandı ve doğrulandı ... tüm PHP dosyaları" dendi.
_VERIFY_CLAIMS = re.compile(
    r"doğrula(?:ndı|dım|nmıştır|ndılar)|test (?:edildi|ettim|edilmiştir)|testler(?:i)? geç"
    r"|hatasız|sorunsuz çalış|sözdizimi (?:temiz|hatası yok|doğru)|hiçbir (?:sözdizimi )?hata yok"
    r"|lint (?:temiz|geçti)|\bverified\b|tests? pass(?:ed|es)?|all tests|no (?:syntax )?errors",
    re.IGNORECASE,
)

#: Kanıtsız iddia uyarısı (raporda ajanın metninin üstünde durur).
UNVERIFIED_CLAIM_WARNING = (
    "⚠ Ajan doğrulama yaptığını söylüyor ama bu turda hiçbir doğrulama başarıyla "
    "çalışmadı; bu iddia GEÇERSİZ."
)


def stale_claim_warning(shell_command: str, changed: tuple[str, ...] | None) -> str:
    """Kanıt YALNIZ bayatladığında (test daha önce geçmişti) iddia uyarısı.

    Ölçüldü (30 Ekim, y3): testler geçmişti, sonra tanınmayan bir kabuk komutu mutasyon
    sayıldı; rapor "hiçbir doğrulama başarıyla çalışmadı; bu iddia GEÇERSİZ" yazdı.
    Bu yanlış ve sert: doğrulama çalışmıştı, yalnız son değişiklikten ÖNCE.
    """
    if not shell_command:
        return (
            "⚠ Ajanın doğrulama beyanı güncel değil: testler daha önce geçmişti ama sonra "
            "dosyalar yeniden değişti; doğrulama yeniden çalıştırılmalı."
        )
    etki = "dosyaları değiştirdi" if changed else "dosyaları değiştirmiş olabilir"
    return (
        f"⚠ Ajanın doğrulama beyanı güncel değil: testler daha önce geçmişti ama sonra "
        f"`{shell_command}` çalıştı ve {etki}; doğrulama yeniden çalıştırılmalı."
    )


#: Komut çalıştırmadan söylenemeyecek SOMUT başarı iddiası (test/lint/sözdizimi).
#: Genel "doğrulandı" dosyayı okuyarak da söylenebilir; yalnız uyarı alır. Bunlar
#: ise kanıtsızsa yalandır ve turu başarısız yapar.
_COMMAND_CLAIMS = re.compile(
    r"test (?:edildi|ettim|edilmiştir)|testler(?:i)? geç|lint (?:temiz|geçti)"
    r"|sözdizimi (?:temiz|hatası yok)|tests? pass(?:ed|es)?|all tests",
    re.IGNORECASE,
)


def claims_verification(text: str) -> bool:
    """Metin bir doğrulama/test başarısı iddia ediyor mu?"""
    return bool(_VERIFY_CLAIMS.search(text))


def claims_command_success(text: str) -> bool:
    """Metin, ancak bir komut çalıştırılarak bilinebilecek bir başarı iddia ediyor mu?"""
    return bool(_COMMAND_CLAIMS.search(text))


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
    #: Çıktıdan okunabilen test sayısı ("4/4"); okunamadıysa boş.
    test_counts: str = ""


@dataclass(frozen=True, slots=True)
class TurnReport:
    """Bir turun (ya da bir plan yürütmesinin) doğrulanabilir özeti."""

    changed_paths: tuple[str, ...] = ()
    command_runs: tuple[CommandRun, ...] = ()
    #: Deterministik kalite kapısının (ruff/mypy/verifier) sonucu; yoksa `None`.
    gate: VerificationResult | None = None
    #: Çok dosyalı uzun kod görevinde son değişiklikten sonra davranış kanıtı zorunludur.
    require_behavioral_evidence: bool = False
    #: Model kanıt yokken doğrulama iddia etti mi? (`build_turn_report` doldurur.)
    false_claim: bool = False
    job_deliveries: tuple[JobDelivery, ...] = ()
    #: Turda var olan teste/CI'a dokunuş (bkz. `tamper_check.py`). Zayıflatan bulgu varken
    #: geçen komut tek başına doğrulama sayılmaz; yalnız dokunuş ise uyarıdır.
    test_tamper: tuple[TamperFinding, ...] = ()
    #: Değişen dosyaların GERÇEK fark özeti (bkz. `change_digest.py`); modelin anlatımı değil.
    change_lines: tuple[str, ...] = ()
    #: Turdaki SON dosya mutasyonu bir kabuk komutuysa onun metni. "Komut çalıştırılmadı"
    #: raporu bunu söyler: kabuk komutu dosya değiştirmiş SAYILDIĞI için önceki test eskidir.
    last_shell_mutation: str = ""
    #: O kabuk komutunun parmak izinde ÖLÇÜLEN değişen dosyaları; `None` = ölçülemedi
    #: ("değiştirmiş olabilir" varsayımı).
    last_shell_changes: tuple[str, ...] | None = None
    criteria: tuple[CriterionEvidence, ...] = ()
    #: Presentation only: trusted implicit captures remain in changed_paths/verification.
    internal_observation_paths: tuple[str, ...] = ()

    @property
    def presentation_paths(self) -> tuple[str, ...]:
        internal = frozenset(self.internal_observation_paths)
        return tuple(path for path in self.changed_paths if path not in internal)

    @property
    def _behavioral_evidence(self) -> tuple[CommandRun, ...]:
        """Son mutasyondan SONRA çalışan, davranışı KANITLAYAN komutlar."""
        return tuple(
            run
            for run in self.command_runs
            if run.after_last_mutation and is_behavioral_command(run.command)
        )

    @property
    def _unresolved_evidence(self) -> tuple[CommandRun, ...]:
        """Kanıt komutları; AYNI komutun sonradan geçen koşusuyla aşılan başarısızlar çıkar.

        Ölçüldü (18 Ekim): `pytest` "komut bulunamadı" (127) verdi, model `python3 -m pytest`
        ile aynı testi geçirdi; rapor yine de "başarısız" yazıp doğru iddiayı GEÇERSİZ saydı.
        Yalnız AYNI komut aşar: farklı bir komutun geçmesi başarısız testi gizlemez.
        """
        evidence = self._behavioral_evidence
        return tuple(
            run
            for index, run in enumerate(evidence)
            if run.exit_code == 0 or not _passed_later(run, evidence[index + 1 :])
        )

    @property
    def is_verified(self) -> bool | None:
        """`None` = değişiklik yok, sorulacak bir şey yok.

        Değişiklik varsa: son mutasyondan sonra çalışan davranış kanıtı YOKSA
        veya kanıtlardan biri başarısızsa `False`; hepsi başarılıysa `True`.
        """
        if any(
            item.status is not EvidenceStatus.PASSED for item in summarize_criteria(self.criteria)
        ):
            return False
        if self.gate is not None and not self.gate.ok:
            return False
        if any(item.problem for item in self.job_deliveries):
            return False
        # Test/CI zayıflatıldıysa geçen test kanıt değildir: ajan sınavı kendi yazmış olabilir.
        # (Kabuk `rm tests/x.py` gibi izlenmeyen değişiklikte `changed_paths` boş olabilir.)
        if has_weakening(self.test_tamper):
            return False
        if not self.changed_paths:
            return None
        evidence = self._unresolved_evidence
        if not evidence:
            return self._gate_passed_evidence is not None
        return all(run.exit_code == 0 for run in evidence)

    @property
    def _gate_passed_evidence(self) -> str | None:
        """Kapının KENDİSİNİN çalıştırıp geçtiği davranış kontrolü (ör. sayfaları
        tarayıcıda açmak). Ölçüldü (26 Eylül): statik site 5 sayfası tarayıcıda
        açılıp denetlendiği hâlde "doğrulama komutu çalıştırılmadı" deniyordu."""
        gate = self.gate
        if gate is None or not gate.ok or not gate.evidence:
            return None
        if any(item.status is not EvidenceStatus.PASSED for item in gate.evidence):
            return None
        if not any(item.behavioral for item in gate.evidence):
            # Yalnız sözdizimi denetlendi: iş ÇALIŞTIRILIP görülmedi.
            return None
        return "; ".join(item.summary for item in gate.evidence)

    @property
    def _static_only_evidence(self) -> str | None:
        """Kapı geçti ama yalnız biçim denetledi (ör. `php -l`); özeti, yoksa None."""
        gate = self.gate
        if gate is None or not gate.ok or not gate.evidence:
            return None
        if any(item.behavioral for item in gate.evidence):
            return None
        return "; ".join(item.summary for item in gate.evidence)

    @property
    def blocks_success(self) -> bool:
        """Turu BAŞARISIZ ilan etmeyi gerektiren somut bir kanıt var mı.

        Basit değişikliklerde eksik kanıt uyarıdır. Uzun kod görevinde son
        değişiklikten sonra test yoksa başarı iddiası için gereken kanıt eksiktir.
        """
        if any(item.status is EvidenceStatus.FAILED for item in summarize_criteria(self.criteria)):
            return True
        if any(item.problem for item in self.job_deliveries):
            return True
        if self.gate is not None and not self.gate.ok:
            return True
        if self.require_behavioral_evidence and self.is_verified is False:
            return True
        if self.false_claim:
            return True
        # Çıkış kodu okunamayan (zaman aşımı) davranış komutu da başarı iddiasını engeller:
        # `None` bir başarı kanıtı değildir (A4-26).
        return any(run.exit_code not in (None, 0) for run in self._unresolved_evidence) or any(
            run.exit_code is None for run in self._unresolved_evidence
        )

    def render(self) -> str:
        """Türkçe, kısa bir rapor metni üret; değişiklik yoksa boş döner (D4)."""
        if (
            not self.presentation_paths
            and not self.job_deliveries
            and not self.test_tamper
            and not (self.changed_paths and (self._gate_blocks() or self.blocks_success))
        ):
            return ""
        jobs = tuple(
            (
                f"İş {item.completion.job_id} önceki denemesi taze aynı kapsamla çözüldü."
                if item.is_superseded
                else item.problem
            )
            or f"İş {item.completion.job_id} tamamlandı "
            f"(çıkış {item.completion.exit_code}); görsel kalite ayrıca doğrulanmalı."
            for item in self.job_deliveries
        )
        blocks = [*jobs, *self._gate_blocks()]
        if self.presentation_paths or (self.changed_paths and self.blocks_success):
            blocks.append(self._evidence_block())
        if self.change_lines and self.presentation_paths:
            blocks.append("Değişen satırlar (gerçek fark):\n" + "\n".join(self.change_lines))
        blocks.append(render_findings(self.test_tamper))
        return "\n\n".join(block for block in blocks if block) + "\n\n"

    def render_with_model_text(self, model_text: str) -> str:
        """Eksik veya başarısız kanıtta modelin özeti doğrulanmış gibi görünmesin."""
        # Düşünme, rapor eklenmeden ÖNCE ayıklanır: açılışsız `</think>` sonradan
        # ayıklansaydı kapanıştan önceki rapor da düşünme sanılıp silinirdi.
        model_text = strip_thinking(model_text).strip()
        report = self.render()
        if not report:
            return model_text
        if self.changed_paths and _claims_no_change(model_text):
            return (
                report + "⚠ Ajanın dosya değişikliği beyanı araç kaydıyla çeliştiği için "
                "açıklaması gösterilmedi."
            )
        if (self.is_verified is False or self.false_claim) and model_text.strip():
            if self.false_claim and self.unsupported_contact_delivery_claim(model_text):
                uyari = (
                    "⚠ Mesaj teslimatı doğrulanmadı; alındı/gönderildi beyanı desteklenmiyor.\n\n"
                )
            else:
                uyari = f"{self._claim_warning()}\n\n" if claims_verification(model_text) else ""
            return report + uyari + "Ajanın açıklaması (doğrulanmamış):\n\n" + model_text
        return report + model_text

    @property
    def _passed_behavioral_criteria(self) -> tuple[CriterionEvidence, ...]:
        return tuple(
            item
            for item in summarize_criteria(self.criteria)
            if item.status is EvidenceStatus.PASSED and item.behavioral
        )

    def unsupported_contact_delivery_claim(self, text: str) -> bool:
        """Çevrimdışı form ölçümü gerçek mesajın teslim edildiğini kanıtlamaz."""
        from .contact_form_probe import _claims_receipt

        if not any(item.criterion_id == "contact_receipt_truth" for item in self.criteria):
            return False
        prose = re.sub(r'```.*?```|`[^`]*`|["“][^"”\n]*["”]', " ", text, flags=re.S)
        return _claims_receipt(prose)

    def unsupported_command_claim(self, text: str) -> bool:
        """Geçen tarayıcı kontrolü, yalnız o kapsamdaki test beyanını destekler."""
        browser_passed = any(
            item.criterion_id == "tarayici_sayfalari" for item in self._passed_behavioral_criteria
        )
        if browser_passed:
            text = re.sub(
                r"(?:tarayıcıda|browser|website|web sitesi|site|sayfa)"
                r"[^.!?;\n]{0,60}?\btest (?:edildi|ettim|edilmiştir)\b",
                lambda match: re.sub(
                    r"\btest (?:edildi|ettim|edilmiştir)\b", "", match.group(), flags=re.I
                ),
                text,
                flags=re.IGNORECASE,
            )
        if not self.changed_paths or not claims_command_success(text):
            return False
        if self.is_verified is False:
            return True
        command_proven = any(run.exit_code == 0 for run in self._unresolved_evidence) or any(
            item.kind is VerificationCheckKind.COMMAND and item.status is EvidenceStatus.PASSED
            for item in self.criteria
        )
        return not command_proven

    def _claim_warning(self) -> str:
        """Kanıt hiç yoksa sert uyarı; yalnız bayatladıysa (önceden geçmişti) doğru olanı."""
        if self._passed_behavioral_criteria or any(
            run.exit_code == 0 for run in self._unresolved_evidence
        ):
            return (
                "ⓘ Bazı kontroller geçti; doğrulanmayan ölçütler için "
                "genel başarı beyanı desteklenmiyor."
            )
        if self._passed_before_last_mutation and not self._unresolved_evidence:
            return stale_claim_warning(self.last_shell_mutation, self.last_shell_changes)
        return UNVERIFIED_CLAIM_WARNING

    @property
    def _passed_before_last_mutation(self) -> bool:
        """Son mutasyondan ÖNCE geçen bir davranış kanıtı var mı (bayat ama gerçek)?"""
        return any(
            run.exit_code == 0
            and is_behavioral_command(run.command)
            and not run.after_last_mutation
            for run in self.command_runs
        )

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
        block = self._evidence_block_text()
        if has_weakening(self.test_tamper) and block.startswith("✓ Doğrulandı"):
            return block.replace(
                "✓ Doğrulandı",
                "ⓘ Komutlar geçti ama doğrulanmış SAYILMAZ (şüpheli test değişikliği)",
                1,
            )
        return block

    def _evidence_block_text(self) -> str:
        dosyalar = ", ".join(self.presentation_paths or self.changed_paths)
        evidence = self._unresolved_evidence
        kapi_kaniti = self._gate_passed_evidence
        if not evidence and kapi_kaniti:
            return f"✓ Doğrulandı: {kapi_kaniti}.\nDeğişen dosyalar: {dosyalar}"
        bicim = self._static_only_evidence
        if not evidence and bicim:
            return (
                f"ⓘ Yalnız sözdizimi denetlendi: {bicim}.\nDeğişen dosyalar: {dosyalar}\n"
                "Site çalıştırılıp açılmadı; çalıştığı DOĞRULANMADI (start_preview ile görülür)."
            )
        if not evidence and self._passed_behavioral_criteria:
            passed = "; ".join(item.summary for item in self._passed_behavioral_criteria)
            pending = "; ".join(
                item.summary
                for item in summarize_criteria(self.criteria)
                if item.status is not EvidenceStatus.PASSED
            )
            return (
                f"ⓘ Geçen alt kontroller: {passed}.\n"
                f"Diğer ölçütler: {pending or 'toplam doğrulama tamamlanmadı'}.\n"
                f"Değişen dosyalar: {dosyalar}"
            )
        if not evidence and artifact_only(self.presentation_paths):
            return (
                f"ⓘ Görsel / belge çıktıları: {dosyalar}\n"
                "Dosyanın kaydedilmesi görev sonucunun doğrulandığı anlamına gelmez; "
                "görsel veya içerik kontrolü ayrıca ölçülmeli."
            )
        if not evidence:
            return (
                f"ⓘ Değişen dosyalar: {dosyalar}\n"
                "Son değişiklikten sonra bir doğrulama komutu ÇALIŞTIRILMADI; "
                "sonuç doğrulanmadı." + self._stale_note()
            )
        basarisiz = tuple(run for run in evidence if run.exit_code != 0)
        if basarisiz:
            komutlar = "; ".join(
                f"`{run.command}` ({_exit_text(run.exit_code)})" for run in basarisiz
            )
            return f"✗ Doğrulama başarısız: {komutlar}\nDeğişen dosyalar: {dosyalar}"
        komutlar = "; ".join(f"`{run.command}`" for run in evidence)
        if self.gate is not None and not self.gate.ok:
            return (
                f"ⓘ Geçen alt kontroller: {komutlar}. Toplam doğrulama başarısız.\n"
                f"Değişen dosyalar: {dosyalar}"
            )
        if self.is_verified is False:
            return (
                f"ⓘ Geçen alt kontroller: {komutlar}. Diğer kabul ölçütleri doğrulanmadı.\n"
                f"Değişen dosyalar: {dosyalar}"
            )
        return f"✓ Doğrulandı: {komutlar} başarıyla çalıştı.\nDeğişen dosyalar: {dosyalar}"

    def _stale_note(self) -> str:
        """Test koşmuş ama SONRA bir kabuk komutu "dosya değiştirmiş olabilir" sayılmışsa söyle.

        Ölçüldü (30 Ekim, g3): `pytest` geçti, ardından modelin elle denediği
        `python3 -m paket.cli listele` tanınmayan program olduğu için temkinli olarak
        mutasyon sayıldı; rapor yalnız "komut çalıştırılmadı" diyordu ve kullanıcı
        testin koştuğunu bilmiyordu.
        """
        if not self.last_shell_mutation or not self._passed_before_last_mutation:
            return ""
        if self.last_shell_changes:
            degisen = ", ".join(self.last_shell_changes[:_STALE_NAMED_FILES])
            return (
                f"\nTest bundan önce geçmişti ama sonra `{self.last_shell_mutation}` çalıştı ve "
                f"dosyaları değiştirdi ({degisen}); testi yeniden çalıştır."
            )
        return (
            f"\nTest bundan önce geçmişti ama sonra `{self.last_shell_mutation}` çalıştı; "
            "kabuk komutu dosya değiştirmiş olabileceği için testi yeniden çalıştır."
        )


_STALE_NAMED_FILES = 3


def _exit_text(code: int | None) -> str:
    return f"çıkış {code}" if code is not None else "çıkış kodu okunamadı / zaman aşımı"


_RUNNER_PREFIX = re.compile(r"^\s*python[\d.]*\s+-m\s+")


def _same_command(first: str, second: str) -> bool:
    """`pytest x` ile `python3 -m pytest x` aynı komuttur (yalnız çalıştırıcı farklı)."""
    return _RUNNER_PREFIX.sub("", first).strip() == _RUNNER_PREFIX.sub("", second).strip()


def _passed_later(failed: CommandRun, later: tuple[CommandRun, ...]) -> bool:
    return any(run.exit_code == 0 and _same_command(failed.command, run.command) for run in later)


def build_turn_report(
    changed_paths: tuple[str, ...],
    tool_uses: tuple[ToolUse, ...],
    gate: VerificationResult | None,
    *,
    require_behavioral_evidence: bool = False,
    current_jobs: tuple[JobCurrentSnapshot, ...] = (),
    test_tamper: tuple[TamperFinding, ...] = (),
    change_lines: tuple[str, ...] = (),
    internal_observation_paths: tuple[str, ...] = (),
) -> TurnReport:
    """Turda denenen araç çağrılarından ve değişiklik kaydından raporu kur."""
    last_mutation = _last_mutation_index(tool_uses)
    last_shell_use = (
        tool_uses[last_mutation]
        if last_mutation is not None and _is_shell_call(tool_uses[last_mutation].name)
        else None
    )
    last_shell = _command_text(last_shell_use) if last_shell_use is not None else ""
    last_shell_changes = (
        last_shell_use.workspace_effect.changed
        if last_shell_use is not None and last_shell_use.workspace_effect is not None
        else None
    )
    changed_paths = _with_shell_changes(changed_paths, tool_uses)
    jobs = collect_job_deliveries(tool_uses, current_jobs)
    command_runs = tuple(
        _command_run(use, after=last_mutation is not None and index > last_mutation)
        for index, use in enumerate(tool_uses)
        if _is_shell_call(use.name) and not _never_ran(use) and use.job_completion is None
    )
    command_runs += tuple(
        CommandRun(
            item.completion.command,
            item.completion.exit_code,
            last_mutation is not None
            and item.launch_index is not None
            and item.launch_index > last_mutation,
        )
        for item in jobs
        if item.completion.phase is JobPhase.COMPLETED and not item.is_superseded
    )
    return TurnReport(
        changed_paths=changed_paths,
        command_runs=command_runs,
        gate=gate,
        criteria=gate.evidence if gate is not None else (),
        require_behavioral_evidence=require_behavioral_evidence,
        job_deliveries=jobs,
        test_tamper=test_tamper,
        change_lines=change_lines,
        last_shell_mutation=last_shell,
        last_shell_changes=last_shell_changes,
        internal_observation_paths=internal_observation_paths,
    )


def _with_shell_changes(
    changed_paths: tuple[str, ...], tool_uses: tuple[ToolUse, ...]
) -> tuple[str, ...]:
    """Dosya araçlarının kaydına, kabuk komutlarının parmak izinde ÖLÇÜLEN değişikliklerini ekle.

    Yalnız turda zaten bir dosya değişikliği varsa: kabuk tek başına çalıştırılan bir betik
    (veri üretimi vb.) kullanıcıya yeni bir "doğrulanmadı" rapor yüzeyi açmaz.
    """
    if not changed_paths:
        return changed_paths
    extra = [
        path
        for use in tool_uses
        if _is_shell_call(use.name) and use.workspace_effect is not None
        for path in use.workspace_effect.changed or ()
        if path not in changed_paths
    ]
    return (*changed_paths, *dict.fromkeys(extra))


def _never_ran(use: ToolUse) -> bool:
    """Tekrar kapısı çağrıyı ÇALIŞTIRMADAN engelledi mi?

    Ölçüldü (29 Eylül, canlı uzun görev): aynı `pytest` komutunun değişikliksiz
    ikinci isteği engellendi; engel çıktısında çıkış kodu olmadığı için rapor
    "çıkış None" ile doğrulamayı başarısız saydı, oysa ilk koşu geçmişti.
    Zaman aşımı gibi GERÇEKTEN çalışmış komutlar bu kapsamda değildir.
    """
    return use.output.startswith((TOOL_CALL_DUPLICATE_PREFIX, TOOL_CALL_BLOCKED_PREFIX))


def _last_mutation_index(tool_uses: tuple[ToolUse, ...]) -> int | None:
    """Son dosya mutasyonunun sırası.

    `run_shell` onay gerektirdiği için `mutating=True` işaretlidir ama her kabuk
    çağrısı dosya değiştirmez (ör. `pytest -q`); doğrulama komutunun kendisini
    mutasyon saymak, hiçbir komutun ondan SONRA sayılmamasına yol açardı. Öte
    yandan dosya DEĞİŞTİREBİLEN kabuk komutu (`sed -i`, `> dosya`, `cp`, `npm
    install`) mutasyondur: ölçüldü (29 Ekim), test geçtikten sonra `sed -i` kodu
    değiştirdi ve eski test başarısı kanıt sayıldı.

    Tanınmayan program (`python3 -m paket.cli listele`) komut metninden ayırt edilemez;
    bu yüzden temkinli mutasyon sayılır. AMA çalışma alanı parmak izi (bkz.
    `core.workspace_fingerprint`) komutun hiçbir dosyayı değiştirmediğini ÖLÇTÜYSE mutasyon
    sayılmaz. Ölçüm yalnız gevşetir; ölçülemediyse (`None`) eski davranış korunur.
    Ölçüldü (30 Ekim, y3): dosya yazmayan `listele` testin kanıtını bayatlatıyordu.
    """
    for index in range(len(tool_uses) - 1, -1, -1):
        use = tool_uses[index]
        if not use.mutating or use.job_completion is not None:
            continue
        if _is_shell_call(use.name):
            if (
                not _never_ran(use)
                and shell_may_change_files(_command_text(use))
                and not _measured_unchanged(use)
            ):
                return index
        elif use.ok:
            return index
    return None


def _measured_unchanged(use: ToolUse) -> bool:
    """Komut proje kökünde GERÇEKTEN hiçbir dosyayı değiştirmedi mi (parmak izi aynı)?

    Ölçüm yalnız temkinli sınıflandırmayı GEVŞETİR: ölçülemeyen (`None`) komut eski
    davranışta kalır. Proje kökü DIŞINA yazma parmak izinde görünmez.
    """
    return use.workspace_effect is not None and use.workspace_effect.is_unchanged


def _command_run(use: ToolUse, *, after: bool) -> CommandRun:
    return CommandRun(
        command=_command_text(use),
        exit_code=_exit_code(use),
        after_last_mutation=after,
        test_counts=_test_counts(use.output),
    )


#: `pytest` özet satırı parçaları ("3 passed, 1 failed, 2 errors in 0.4s").
_PYTEST_COUNT = re.compile(r"(\d+) (passed|failed|errors?)\b")
#: jest: "Tests:       1 failed, 3 passed, 4 total".
_JEST_TOTAL = re.compile(r"Tests:\s+(?:.*?)(\d+) passed, (\d+) total")
#: vitest: "Tests  1 failed | 3 passed (4)".
_VITEST_TOTAL = re.compile(r"Tests\s+(?:.*?)(\d+) passed(?: \| \d+ \w+)* \((\d+)\)")


def _test_counts(output: str) -> str:
    """Komut çıktısından "geçen/toplam" test sayısı; okunamıyorsa boş.

    Yalnız bilinen koşturucuların ÖZET satırı okunur; tahmin edilmez.
    """
    for pattern in (_JEST_TOTAL, _VITEST_TOTAL):
        match = pattern.search(output)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
    sayilar = {"passed": 0, "failed": 0}
    bulundu = False
    for adet, tur in _PYTEST_COUNT.findall(output):
        bulundu = True
        sayilar["passed" if tur == "passed" else "failed"] += int(adet)
    if not bulundu or not sayilar["passed"] + sayilar["failed"]:
        return ""
    return f"{sayilar['passed']}/{sayilar['passed'] + sayilar['failed']}"


@dataclass(frozen=True, slots=True)
class EvidenceSummary:
    """Tur sonunda kullanıcıya tek satırla gösterilecek kanıt: geçenler ve ölçülemeyenler."""

    #: GERÇEKTEN çalışıp geçen kontroller ("tarayıcı (2 sayfa, konsol temiz)", "testler 4/4").
    verified: tuple[str, ...] = ()
    #: Çalışamayan ya da hiç koşmayan kontrollerin nedeni.
    unmeasured: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.verified and not self.unmeasured


_PAGE_COUNT = re.compile(r"^(\d+) sayfa")
#: Bir kontrolün ölçülemediğini söyleyen uyarılar (kapı çöktü, araç yok, tarayıcı açılmadı).
_UNMEASURED_MARKERS = ("doğrulanamad", "ölçülemed")
_REASON_CHARS = 160
_COMMAND_LABEL_CHARS = 50


def _short(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _unmeasured_reason(warning: str) -> str | None:
    """Uyarı bir kontrolün ölçülemediğini söylüyorsa nedenini ver; değilse None."""
    if warning.startswith(NOT_MEASURED_PREFIX):
        return _short(warning.removeprefix(NOT_MEASURED_PREFIX), _REASON_CHARS)
    lowered = warning.lower()
    if warning.startswith(UNVERIFIABLE_COMMAND_PREFIX) or any(
        marker in lowered for marker in _UNMEASURED_MARKERS
    ):
        return _short(warning, _REASON_CHARS)
    return None


def _gate_label(item: CriterionEvidence) -> str:
    """Geçen kapı kanıtını kullanıcı cümlesine çevir (tarayıcı: sayfa sayısı + konsol)."""
    summary = item.summary
    if item.criterion_id == "tarayici_sayfalari":
        match = _PAGE_COUNT.match(summary)
        if match:
            # Konsol hatası ENGELLEYİCİ bulgudur; kapı geçtiyse konsol temizdir.
            return f"tarayıcı ({match.group(1)} sayfa, konsol temiz)"
    return summary


def summarize_evidence(report: TurnReport) -> EvidenceSummary:
    """Raporun geçen ve ölçülemeyen kanıtlarını tek satırlık özete çevir.

    Saftır; yalnız rapora (gerçek araç kaydı + kapı sonucu) bakar. Değişiklik yoksa
    sorulacak bir şey yoktur, boş döner.
    """
    if not report.changed_paths:
        return EvidenceSummary()
    gate = report.gate
    verified: list[str] = []
    unmeasured: list[str] = []
    if gate is not None and gate.ok:
        verified.extend(
            _gate_label(item)
            for item in gate.evidence
            if item.status is EvidenceStatus.PASSED and item.behavioral
        )
    runs = [run for run in report._unresolved_evidence if run.exit_code == 0]
    verified.extend(
        f"testler {run.test_counts}"
        if run.test_counts
        else f"`{_short(run.command, _COMMAND_LABEL_CHARS)}`"
        for run in runs
    )
    if gate is not None:
        for warning in gate.warnings:
            reason = _unmeasured_reason(warning)
            if reason is not None:
                unmeasured.append(reason)
        if not runs and report._static_only_evidence is not None:
            unmeasured.append("yalnız sözdizimi denetlendi; sayfa çalıştırılıp görülmedi")
    if not verified and not unmeasured and report.is_verified is False:
        unmeasured.append("son değişiklikten sonra doğrulama komutu çalıştırılmadı")
    return EvidenceSummary(tuple(dict.fromkeys(verified)), tuple(dict.fromkeys(unmeasured)))


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
