"""Git push için deterministik, kanıt kapılı workflow.

LLM bu akışta shell komutu seçmez ve başarı ilan edemez. Workflow sabit adımları
çalıştırır; yalnızca ``git push`` exit code 0 VE local/remote HEAD eşitliği başarıdır.
"""

from __future__ import annotations

import hashlib
import re
import shlex
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .detect import extract_branch_reference, extract_repository_reference
from .model import (
    Evidence,
    EffectContract,
    EffectKind,
    EffectRunResult,
    WorkflowRecord,
    WorkflowStatus,
    missing_evidence,
    root_key,
)
from .store import WorkflowStore
from .tool_runner import EffectToolRunner

if TYPE_CHECKING:  # pragma: no cover
    from ...tools import ToolRegistry
    from ..agent.loop import AgentDeps


_SKIP_UNTRACKED_PATTERNS = (
    re.compile(r"(^|/)\.env(?:\.|$)", re.IGNORECASE),
    re.compile(r"(^|/)\.venv(?:/|$)", re.IGNORECASE),
    re.compile(r"(^|/)node_modules(?:/|$)", re.IGNORECASE),
    re.compile(r"(^|/)__pycache__(?:/|$)", re.IGNORECASE),
    re.compile(r"(^|/)\.pytest_cache(?:/|$)", re.IGNORECASE),
    re.compile(r"(^|/)(?:build|dist)(?:/|$)", re.IGNORECASE),
    re.compile(r"(^|/)\.fusion-[^/]*(?:/|$)", re.IGNORECASE),
    re.compile(r"(^|/)(?:browser_profiles?|credentials?|secrets?)(?:/|$)", re.IGNORECASE),
    re.compile(r"(?:^|/)fusion-.*(?:report|install|fix).*\.(?:txt|log)$", re.IGNORECASE),
    re.compile(r"\.(?:log|pyc|pyo|zip|tar|gz|7z|mov|mp4|mkv|avi|psd)$", re.IGNORECASE),
)
_MAX_AUTO_STAGE_FILE_BYTES = 10 * 1024 * 1024
_SENSITIVE_TRACKED_PATTERNS = (
    re.compile(r"(^|/)\.env(?:\.|$)", re.IGNORECASE),
    re.compile(r"(^|/)(?:credentials?|secrets?)(?:/|$)", re.IGNORECASE),
    re.compile(r"(^|/)(?:cookies?|sessions?)\.(?:json|txt|yaml|yml)$", re.IGNORECASE),
)
_NON_FAST_FORWARD_MARKERS = (
    "non-fast-forward",
    "fetch first",
    "rejected",
    "stale info",
    "failed to push some refs",
)


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    current_branch: str
    origin_url: str
    origin_repo: str | None
    default_branch: str | None
    local_head: str
    status_porcelain: str


class GitPushWorkflow:
    """Repo inceleme → hedef onayı → stage/commit → push → remote verify."""

    def __init__(
        self,
        task: str,
        deps: "AgentDeps",
        registry: "ToolRegistry",
        *,
        store: WorkflowStore,
        contract: EffectContract,
    ) -> None:
        self.task = task
        self.deps = deps
        self.tools = EffectToolRunner(deps, registry)
        self.store = store
        self.contract = contract
        self.root = deps.tool_context.root.expanduser().resolve()
        self.record = self._load_or_create_record()
        self.excluded_untracked: list[str] = []

    async def run(self) -> EffectRunResult:
        try:
            snapshot = await self._inspect_repository()
            if snapshot is None:
                return self._fail(
                    self.record.error or "Bu klasör geçerli bir Git çalışma ağacı değil."
                )

            self._status(WorkflowStatus.REPOSITORY_INSPECTED)
            self._evidence("repository_inspected", str(self.root), "git inspection")
            self.record.data.update(
                {
                    "current_branch": snapshot.current_branch,
                    "origin_url": snapshot.origin_url,
                    "origin_repo": snapshot.origin_repo,
                    "default_branch": snapshot.default_branch,
                    "local_head_before": snapshot.local_head,
                }
            )
            self._save()

            target_repo = await self._resolve_repository(snapshot)
            if target_repo is None:
                return self._cancelled_or_failed()

            target_branch = await self._resolve_branch(snapshot)
            if target_branch is None:
                return self._cancelled_or_failed()

            self.record.data["target_repo"] = target_repo or snapshot.origin_url
            self.record.data["target_branch"] = target_branch
            self._status(WorkflowStatus.TARGET_CONFIRMED)
            self._evidence(
                "target_confirmed",
                f"{target_repo or snapshot.origin_url}#{target_branch}",
                "user/task + git remote",
            )

            staged = await self._stage_safe_changes()
            if staged is None:
                return self._cancelled_or_failed()

            if staged:
                committed = await self._commit_staged_changes()
                if not committed:
                    return self._cancelled_or_failed()
            else:
                self._status(WorkflowStatus.NOTHING_TO_COMMIT)
                self._evidence(
                    "nothing_to_commit",
                    "working tree has no staged changes",
                    "git diff",
                )

            local_head = await self._git_output("rev-parse HEAD")
            if not local_head:
                return self._fail("Yerel HEAD okunamadı; push başlatılmadı.")
            local_head = local_head.strip().splitlines()[0]
            self.record.data["local_head"] = local_head
            self._evidence("local_head", local_head, "git rev-parse HEAD")

            remote_head_before = await self._remote_head(target_branch)
            self.record.data["remote_head_before"] = remote_head_before or ""
            self._save()

            normal_push = await self._push(target_branch, force_lease=None)
            if not normal_push:
                last_output = self.record.data.get("last_push_output", "")
                if not self._looks_non_fast_forward(str(last_output)):
                    return self._fail(
                        "Push başarısız oldu ve güvenli force senaryosu olarak "
                        "sınıflandırılamadı.\n"
                        f"Ayrıntı: {self._short(str(last_output))}"
                    )
                force_ok = await self._handle_force_push(
                    target_branch, local_head, remote_head_before
                )
                if not force_ok:
                    return self._cancelled_or_failed()

            self._status(WorkflowStatus.PUSHED)
            self._evidence("push_exit_zero", target_branch, "git push exit code 0")

            remote_head = await self._remote_head(target_branch)
            if not remote_head:
                return self._fail(
                    "Push komutu başarılı görünse de uzak branch HEAD okunamadı; "
                    "görev tamamlanmış sayılmadı."
                )
            self.record.data["remote_head"] = remote_head
            self._evidence("remote_head", remote_head, "git ls-remote")

            if remote_head != local_head:
                return self._fail(
                    "Push doğrulanamadı: yerel ve uzak commit hashleri eşleşmiyor.\n"
                    f"Local : {local_head}\nRemote: {remote_head}"
                )

            self._status(WorkflowStatus.REMOTE_VERIFIED)
            self._evidence("remote_verified", remote_head, "local HEAD == remote HEAD")
            self._assert_contract()
            self._status(WorkflowStatus.COMPLETED)

            skipped = ""
            if self.excluded_untracked:
                skipped = (
                    "\n\nGüvenlik nedeniyle commit'e eklenmeyen izlenmeyen dosyalar:\n- "
                    + "\n- ".join(self.excluded_untracked[:20])
                )
            return self._result(
                "Push tamamlandı ve uzak HEAD doğrulandı.\n"
                f"Remote : {self.record.data['origin_url']}\n"
                f"Branch : {target_branch}\n"
                f"Local  : {local_head}\n"
                f"Remote : {remote_head}\n"
                f"Workflow: {self.record.workflow_id}"
                + skipped,
                ok=True,
            )
        except Exception as exc:  # Son savunma: kanıtsız başarı yerine açık hata.
            return self._fail(
                "Git push workflow beklenmeyen hata verdi: "
                f"{type(exc).__name__}: {exc}"
            )

    def _load_or_create_record(self) -> WorkflowRecord:
        existing = self.store.find_open(self.root, EffectKind.GIT_PUSH.value)
        if existing is not None:
            existing.task = self.task
            existing.error = None
            return existing
        digest = hashlib.sha256(f"{root_key(self.root)}\0{self.task}".encode()).hexdigest()[:10]
        return WorkflowRecord(
            workflow_id=f"git-push-{digest}-{uuid.uuid4().hex[:8]}",
            kind=EffectKind.GIT_PUSH.value,
            root=root_key(self.root),
            task=self.task,
        )

    async def _inspect_repository(self) -> RepositorySnapshot | None:
        inside = await self._git_output("rev-parse --is-inside-work-tree")
        if not inside or inside.strip().lower() != "true":
            return None
        branch = (await self._git_output("branch --show-current") or "").strip()
        if not branch:
            return self._fail_snapshot("Detached HEAD durumunda otomatik push yapılmaz.")
        origin = (await self._git_output("remote get-url origin") or "").strip()
        if not origin:
            return self._fail_snapshot("'origin' remote tanımlı değil.")
        head = (await self._git_output("rev-parse HEAD") or "").strip()
        status = await self._git_output("status --porcelain=v1")
        if not head or status is None:
            return None
        default_branch = await self._default_branch()
        return RepositorySnapshot(
            current_branch=branch,
            origin_url=origin,
            origin_repo=_parse_remote_repository(origin),
            default_branch=default_branch,
            local_head=head.splitlines()[0],
            status_porcelain=status,
        )

    def _fail_snapshot(self, message: str) -> None:
        self.record.error = message
        self._status(WorkflowStatus.FAILED)
        return None

    async def _resolve_repository(self, snapshot: RepositorySnapshot) -> str | None:
        requested = extract_repository_reference(self.task)
        if not requested or not snapshot.origin_repo:
            return snapshot.origin_repo or snapshot.origin_url
        if _same_repo(requested, snapshot.origin_repo):
            return snapshot.origin_repo

        self._status(WorkflowStatus.AWAITING_TARGET_CONFIRMATION)
        answer = await self._ask(
            "Repo adı uyuşmuyor.\n"
            f"Mevcut origin : {snapshot.origin_repo}\n"
            f"İstekte geçen : {requested}\n"
            "Mevcut origin'i kullanmak için MEVCUT, origin'i istekteki GitHub reposuna "
            "değiştirmek için ISTEK, vazgeçmek için IPTAL yaz.",
            {"mevcut", "istek", "iptal"},
        )
        if answer == "iptal":
            return self._cancel("Repo hedefi kullanıcı tarafından iptal edildi.")
        if answer == "mevcut":
            return snapshot.origin_repo
        if answer != "istek":
            return self._fail_value("Repo hedefi kesinleştirilemedi.")

        new_url = f"https://github.com/{requested}.git"
        changed = await self.tools.execute(
            "run_shell", {"command": f"git remote set-url origin {shlex.quote(new_url)}"}
        )
        if not changed.result.ok:
            return self._fail_value(
                "Origin URL değiştirilemedi; herhangi bir push yapılmadı. "
                + self._short(changed.result.output)
            )
        verified = (await self._git_output("remote get-url origin") or "").strip()
        if _parse_remote_repository(verified) != requested:
            return self._fail_value("Origin değişikliği doğrulanamadı.")
        self.record.data["origin_url"] = verified
        self.record.data["origin_repo"] = requested
        self._evidence("origin_updated", requested, "git remote set-url + get-url")
        return requested

    async def _resolve_branch(self, snapshot: RepositorySnapshot) -> str | None:
        explicit = extract_branch_reference(self.task)
        if explicit:
            return explicit
        default = snapshot.default_branch
        if default and snapshot.current_branch != default and _looks_temporary_branch(
            snapshot.current_branch
        ):
            self._status(WorkflowStatus.AWAITING_TARGET_CONFIRMATION)
            answer = await self._ask(
                "Hedef branch belirsiz.\n"
                f"Aktif branch       : {snapshot.current_branch}\n"
                f"Uzak varsayılan    : {default}\n"
                "Aktif branch'i aynı adla pushlamak için MEVCUT, mevcut HEAD'i uzak "
                "varsayılan branch'e pushlamak için VARSAYILAN, vazgeçmek için IPTAL yaz.",
                {"mevcut", "varsayilan", "varsayılan", "iptal"},
            )
            if answer == "iptal":
                return self._cancel("Branch hedefi kullanıcı tarafından iptal edildi.")
            if answer == "mevcut":
                return snapshot.current_branch
            if answer in {"varsayilan", "varsayılan"}:
                return default
            return self._fail_value("Branch hedefi kesinleştirilemedi.")
        return snapshot.current_branch

    async def _stage_safe_changes(self) -> bool | None:
        status = await self._git_output("status --porcelain=v1")
        if status is None:
            return self._fail_value("Git status okunamadı.")

        tracked_sensitive = _sensitive_tracked_paths(status)
        if tracked_sensitive:
            return self._fail_value(
                "Hassas olabilecek izlenen dosyalar değişmiş; otomatik commit durduruldu:\n- "
                + "\n- ".join(tracked_sensitive)
            )

        has_tracked_changes = any(
            line and not line.startswith("??") for line in status.splitlines()
        )
        if has_tracked_changes:
            tracked = await self.tools.execute("run_shell", {"command": "git add -u"})
            if not tracked.result.ok:
                return self._fail_value(
                    "İzlenen değişiklikler stage edilemedi: "
                    + self._short(tracked.result.output)
                )

        untracked_raw = await self._git_output("ls-files --others --exclude-standard")
        if untracked_raw is None:
            return self._fail_value("İzlenmeyen dosyalar listelenemedi.")
        untracked = [line for line in untracked_raw.splitlines() if line.strip()]
        safe = [path for path in untracked if not _skip_untracked(path, self.root)]
        self.excluded_untracked = [
            path for path in untracked if _skip_untracked(path, self.root)
        ]

        for batch in _batches(safe, 80):
            command = "git add -- " + " ".join(shlex.quote(path) for path in batch)
            added = await self.tools.execute("run_shell", {"command": command})
            if not added.result.ok:
                return self._fail_value(
                    "Yeni dosyalar stage edilemedi: " + self._short(added.result.output)
                )

        staged_names = await self._git_output("diff --cached --name-only")
        if staged_names is None:
            return self._fail_value("Staged değişiklikler doğrulanamadı.")
        sensitive_staged = [
            path for path in staged_names.splitlines() if _sensitive_tracked(path.strip())
        ]
        if sensitive_staged:
            # Hassas dosyayı index'ten çıkar; çalışma ağacına dokunma.
            for batch in _batches(sensitive_staged, 50):
                command = "git restore --staged -- " + " ".join(
                    shlex.quote(path) for path in batch
                )
                await self.tools.execute("run_shell", {"command": command})
            return self._fail_value(
                "Hassas dosyalar stage alanına girdiği için commit durduruldu:\n- "
                + "\n- ".join(sensitive_staged)
            )

        staged = bool(staged_names.strip())
        if staged:
            self._status(WorkflowStatus.STAGED)
            self._evidence("changes_staged", staged_names.strip(), "git diff --cached")
        else:
            self._status(WorkflowStatus.NOTHING_TO_STAGE)
            self._evidence("nothing_to_stage", "no safe changes", "git diff --cached")
        return staged

    async def _commit_staged_changes(self) -> bool:
        commit = await self.tools.execute(
            "run_shell", {"command": "git commit -m 'chore: sync Fusion CLI state'"}
        )
        if not commit.result.ok:
            return bool(
                self._fail_value("Commit oluşturulamadı: " + self._short(commit.result.output))
            )
        head = (await self._git_output("rev-parse HEAD") or "").strip()
        if not head:
            return bool(self._fail_value("Commit sonrası HEAD doğrulanamadı."))
        self._status(WorkflowStatus.COMMITTED)
        self._evidence("commit_created", head, "git commit + rev-parse")
        return True

    async def _push(self, branch: str, *, force_lease: str | None) -> bool:
        destination = f"HEAD:refs/heads/{branch}"
        if force_lease:
            lease = f"--force-with-lease=refs/heads/{branch}:{force_lease}"
            command = f"git push {lease} origin {shlex.quote(destination)}"
        else:
            command = f"git push origin {shlex.quote(destination)}"
        pushed = await self.tools.execute("run_shell", {"command": command})
        self.record.data["last_push_output"] = pushed.result.output
        self.record.data["last_push_command"] = command
        self._save()
        return pushed.result.ok

    async def _handle_force_push(
        self, branch: str, local_head: str, remote_head_before: str | None
    ) -> bool:
        expected = remote_head_before or await self._remote_head(branch)
        if not expected:
            return bool(
                self._fail_value(
                    "Uzak HEAD okunamadığı için force-with-lease uygulanmadı."
                )
            )

        divergence = await self._divergence(branch)
        self._status(WorkflowStatus.AWAITING_FORCE_CONFIRMATION)
        question = (
            "Normal push uzak geçmiş farklı olduğu için reddedildi.\n"
            f"Branch       : {branch}\n"
            f"Local HEAD   : {local_head}\n"
            f"Remote HEAD  : {expected}\n"
            f"Fark         : {divergence}\n"
            "Yalnızca güvenli --force-with-lease çalıştırılabilir. Onaylıyorsan tam olarak "
            "FORCE-WITH-LEASE ONAYLIYORUM yaz; aksi her cevap işlemi iptal eder."
        )
        if self.deps.asker is None:
            return bool(self._fail_value(question))
        answer = (await self.deps.asker.ask(question)).strip()
        if answer != "FORCE-WITH-LEASE ONAYLIYORUM":
            return bool(self._cancel("Force-with-lease kullanıcı tarafından onaylanmadı."))
        return await self._push(branch, force_lease=expected)

    async def _divergence(self, branch: str) -> str:
        fetched = await self.tools.execute(
            "run_shell",
            {"command": f"git fetch --no-tags origin refs/heads/{shlex.quote(branch)}"},
        )
        if not fetched.result.ok:
            return "hesaplanamadı (fetch başarısız)"
        counts = await self._git_output("rev-list --left-right --count FETCH_HEAD...HEAD")
        if not counts:
            return "hesaplanamadı"
        parts = counts.replace("\t", " ").split()
        if len(parts) >= 2:
            return f"uzakta {parts[0]} benzersiz commit, yerelde {parts[1]} benzersiz commit"
        return counts.strip()

    async def _remote_head(self, branch: str) -> str | None:
        output = await self._git_output(f"ls-remote origin refs/heads/{branch}")
        if output is None:
            return None
        line = next((line for line in output.splitlines() if line.strip()), "")
        if not line:
            return None
        return line.split()[0]

    async def _default_branch(self) -> str | None:
        output = await self._git_output("ls-remote --symref origin HEAD")
        if not output:
            return None
        match = re.search(r"ref:\s+refs/heads/([^\s]+)\s+HEAD", output)
        return match.group(1) if match else None

    async def _git_output(self, subcommand: str) -> str | None:
        executed = await self.tools.execute("git", {"subcommand": subcommand})
        if not executed.result.ok:
            return None
        output = executed.result.output
        return "" if output.strip() == "(çıktı yok)" else output

    async def _ask(self, question: str, accepted: set[str]) -> str:
        if self.deps.asker is None:
            self.record.error = question
            self._save()
            return ""
        answer = (await self.deps.asker.ask(question)).strip().lower()
        return answer if answer in accepted else ""

    def _assert_contract(self) -> None:
        missing = missing_evidence(self.record, self.contract)
        if missing:
            raise RuntimeError("EffectContract kanıtları eksik: " + ", ".join(missing))

    def _status(self, status: WorkflowStatus) -> None:
        self.record.set_status(status)
        self._save()

    def _evidence(self, key: str, value: str, source: str) -> None:
        self.record.add_evidence(Evidence(key=key, value=value, source=source))
        self._save()

    def _save(self) -> None:
        self.store.save(self.record)

    def _fail(self, message: str) -> EffectRunResult:
        self.record.error = message
        self._status(WorkflowStatus.FAILED)
        return self._result(
            "İşlem tamamlanmadı. Herhangi bir push başarıyla doğrulanmış kabul edilmemelidir.\n"
            + message
            + f"\nWorkflow: {self.record.workflow_id}",
            ok=False,
        )

    def _cancel(self, message: str) -> None:
        self.record.error = message
        self._status(WorkflowStatus.CANCELLED)
        return None

    def _fail_value(self, message: str) -> None:
        self.record.error = message
        self._status(WorkflowStatus.FAILED)
        return None

    def _cancelled_or_failed(self) -> EffectRunResult:
        status = WorkflowStatus(self.record.status)
        prefix = (
            "İşlem iptal edildi."
            if status is WorkflowStatus.CANCELLED
            else "İşlem tamamlanmadı."
        )
        return self._result(
            f"{prefix} Push yapılmış kabul edilmemelidir.\n"
            f"Sebep: {self.record.error or 'hedef veya adım doğrulanamadı'}\n"
            f"Workflow: {self.record.workflow_id}",
            ok=False,
        )

    def _result(self, text: str, *, ok: bool) -> EffectRunResult:
        return EffectRunResult(
            final_text=text,
            ok=ok,
            tool_calls_made=self.tools.tool_calls_made,
            mutating_tool_calls_made=self.tools.mutating_tool_calls_made,
            failed_tool_calls=self.tools.failed_tool_calls,
            workflow_id=self.record.workflow_id,
        )

    @staticmethod
    def _looks_non_fast_forward(output: str) -> bool:
        lowered = output.lower()
        return any(marker in lowered for marker in _NON_FAST_FORWARD_MARKERS)

    @staticmethod
    def _short(text: str, limit: int = 900) -> str:
        compact = " ".join(text.split())
        return compact if len(compact) <= limit else compact[:limit] + "…"


def _parse_remote_repository(url: str) -> str | None:
    cleaned = url.strip()
    patterns = (
        r"github\.com[:/](?P<owner>[^/\s:]+)/(?P<repo>[^/\s]+?)(?:\.git)?$",
        r"gitlab\.com[:/](?P<owner>[^/\s:]+)/(?P<repo>[^/\s]+?)(?:\.git)?$",
        r"bitbucket\.org[:/](?P<owner>[^/\s:]+)/(?P<repo>[^/\s]+?)(?:\.git)?$",
    )
    for pattern in patterns:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            return f"{match.group('owner')}/{match.group('repo')}"
    return None


def _same_repo(left: str, right: str) -> bool:
    return left.removesuffix(".git").casefold() == right.removesuffix(".git").casefold()


def _looks_temporary_branch(branch: str) -> bool:
    lowered = branch.lower()
    return lowered.startswith(("repair/", "fix/", "feature/", "chore/", "tmp/", "wip/"))


def _skip_untracked(path: str, root: Path) -> bool:
    normalized = path.replace("\\", "/")
    if any(pattern.search(normalized) for pattern in _SKIP_UNTRACKED_PATTERNS):
        return True
    try:
        candidate = (root / path).resolve()
        candidate.relative_to(root)
        return candidate.is_file() and candidate.stat().st_size > _MAX_AUTO_STAGE_FILE_BYTES
    except (OSError, ValueError):
        # Okunamayan veya kök dışına çözülen dosya otomatik stage edilmez.
        return True


def _sensitive_tracked(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(pattern.search(normalized) for pattern in _SENSITIVE_TRACKED_PATTERNS)


def _sensitive_tracked_paths(status_porcelain: str) -> list[str]:
    found: list[str] = []
    for line in status_porcelain.splitlines():
        if len(line) < 4 or line.startswith("??"):
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if _sensitive_tracked(path):
            found.append(path)
    return found


def _batches(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]
