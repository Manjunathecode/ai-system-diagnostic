"""Bounded, audited execution of approved, parameterized repair workflows."""
from __future__ import annotations

import ctypes
import os
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from core.privileges import is_administrator
from fixes.registry import ApprovedFixRegistry
from fixes.path_safety import is_reparse_point
from fixes.verifiers import WindowsStateReader
from models.escalation import EscalationResult
from models.fix_result import AssessmentStatus, FixAssessment, FixExecutionResult, FixStatus
from models.problem import DetectedProblem


class AutonomousFixEngine:
    """Runs only hard-coded registry operations against an explicit target."""

    _SUPPORTED_SERVICE_NAMES = frozenset({"Spooler", "wuauserv", "bits", "Dnscache", "NlaSvc", "Netman"})
    _EXECUTABLE = frozenset({
        "network_flush_dns", "network_renew_ip", "network_restart_adapter",
        "restart_print_spooler", "clear_stuck_print_jobs", "safe_disk_cleanup",
        "restart_supported_windows_service",
    })
    _FALLBACKS = {"network_flush_dns": ("network_renew_ip",)}

    def __init__(self, registry: ApprovedFixRegistry, audit: Callable[[dict], None] | None = None,
                 dry_run: bool = False, reader=None, max_attempts: int = 2,
                 approved_cleanup_directories: tuple[Path, ...] | None = None) -> None:
        self.registry, self.audit, self.dry_run = registry, audit, dry_run
        self.reader, self.max_attempts = reader or WindowsStateReader(), max(1, max_attempts)
        defaults = (Path(tempfile.gettempdir()), self._windows_directory() / "Temp")
        self.approved_cleanup_directories = frozenset(
            path.resolve() for path in (approved_cleanup_directories if approved_cleanup_directories is not None else defaults)
        )

    @classmethod
    def executable_workflow_ids(cls) -> frozenset[str]:
        return cls._EXECUTABLE

    @classmethod
    def recovery_requires_confirmation(cls, fix_id: str, registry: ApprovedFixRegistry) -> bool:
        return any(bool(registry.get(candidate) and registry.get(candidate).risk.value != "low")
                   for candidate in cls._FALLBACKS.get(fix_id, ()))

    @staticmethod
    def target_resource(fix_id: str, problem: DetectedProblem) -> str | None:
        """Return the canonical resource identifier used by execute and verify."""
        if fix_id in {"restart_print_spooler", "clear_stuck_print_jobs", "restart_supported_windows_service"}:
            return problem.parameters.get("service_name")
        if fix_id in {"network_renew_ip", "network_restart_adapter"}:
            return problem.parameters.get("adapter_name")
        if fix_id == "safe_disk_cleanup":
            return problem.parameters.get("temp_directory")
        if fix_id == "network_flush_dns":
            return "dns_resolver"
        return None

    def run(self, problem: DetectedProblem, user_confirmed: bool = False) -> FixExecutionResult:
        started, events = datetime.now(timezone.utc), []
        fix_id = problem.recommended_fix_workflow
        workflow = self.registry.get(fix_id)

        def event(stage: str, message: str) -> None:
            item = {"timestamp": datetime.now(timezone.utc).isoformat(), "problem_id": problem.problem_id,
                    "fix_id": fix_id, "stage": stage, "message": message}
            events.append(item)
            if self.audit:
                self.audit(item)

        validation_error = self._validation_error(problem, workflow)
        if validation_error:
            event("escalated", validation_error)
            return self._result(problem, FixStatus.ESCALATED, started, validation_error, events)
        if problem.requires_user_confirmation and not user_confirmed:
            event("awaiting_confirmation", "User confirmation is required by risk policy.")
            return self._result(problem, FixStatus.AWAITING_CONFIRMATION, started, "Awaiting user approval.", events)
        if workflow.requires_administrator and not self.dry_run and not is_administrator():
            event("escalated", "Administrator privileges are required.")
            return self._result(problem, FixStatus.ESCALATED, started, "Administrator privileges are required.", events)

        before: dict = {}
        execution_succeeded = False
        execution_details: dict = {}
        try:
            event("pre_check", "Capturing exact target state for the registered pre-check.")
            before = self.reader.snapshot(fix_id, problem)
            if not before:
                raise ValueError("Required pre-repair state could not be collected")
            if not self._pre_check(fix_id, problem, before):
                event("pre_check_failed", "The intended fault is not present on the exact target.")
                return self._result(problem, FixStatus.PRE_CHECK_FAILED, started,
                                    "Pre-check found no eligible repair condition; no change was made.", events,
                                    before=before)
            event("fixing", "Executing registered fixed operation." if not self.dry_run
                  else "Dry run: approved operation skipped.")
            if not self.dry_run:
                execution_details = self._execute(fix_id, problem) or {}
                execution_succeeded = True
            event("verifying", "Capturing post-fix state and verifying the exact target.")
            after = self.reader.snapshot(fix_id, problem)
            if not after:
                raise ValueError("Required post-repair state could not be collected")
            verified, evidence, unresolved = self.reader.verify(fix_id, before, after)
            improvement = getattr(self.reader, "improvement", None)
            improved = bool(improvement(fix_id, before, after)) if callable(improvement) else False
        except Exception as error:
            event("failed", f"Approved workflow or verification failed: {error}")
            return self._result(problem, FixStatus.FAILED, started,
                                "Approved workflow or verification failed.", events,
                                before=before, execution_succeeded=execution_succeeded,
                                execution_details=execution_details)

        assessment = self._assessment(verified, evidence, before, after, unresolved, improved)
        if assessment.status == AssessmentStatus.SUCCESS:
            status = FixStatus.RESOLVED
        elif assessment.status == AssessmentStatus.PARTIAL_SUCCESS:
            status = FixStatus.PARTIALLY_RESOLVED
        else:
            status = FixStatus.FAILED
        event(status.value, assessment.verification_evidence[0] if assessment.verification_evidence
              else "Verification completed without evidence.")
        message = "Verification confirmed resolution." if status == FixStatus.RESOLVED else \
            "Verification did not fully confirm resolution."
        return self._result(problem, status, started, message, events, before, after, assessment,
                            execution_succeeded=execution_succeeded, execution_details=execution_details)

    def run_with_recovery(self, problem: DetectedProblem, user_confirmed: bool = False) -> tuple[tuple[FixExecutionResult, ...], EscalationResult | None]:
        attempts: list[FixExecutionResult] = []
        candidate_ids = (problem.recommended_fix_workflow,) + self._FALLBACKS.get(problem.recommended_fix_workflow, ())
        for fix_id in candidate_ids[:self.max_attempts]:
            workflow = self.registry.get(fix_id)
            if workflow is None or not workflow.executable or problem.category not in workflow.supported_problem_types:
                continue
            candidate = DetectedProblem(
                problem.problem_id, problem.category, problem.severity, problem.confidence,
                problem.evidence, problem.likely_cause, fix_id, workflow.requires_administrator,
                workflow.risk.value != "low", workflow.risk, dict(problem.parameters),
            )
            outcome = self.run(candidate, user_confirmed)
            attempts.append(outcome)
            if outcome.status == FixStatus.RESOLVED:
                return tuple(attempts), None
            if outcome.status == FixStatus.AWAITING_CONFIRMATION:
                return tuple(attempts), None
        remaining = attempts[-1].assessment.unresolved_symptoms if attempts and attempts[-1].assessment \
            else ("Problem remains unresolved.",)
        escalation = EscalationResult(
            problem, problem.evidence, tuple(attempts), remaining,
            "Review the recorded evidence and repair timeline; use administrator approval where indicated.",
            any(bool(self.registry.get(item.fix_id) and self.registry.get(item.fix_id).requires_administrator)
                for item in attempts),
        )
        return tuple(attempts), escalation

    def _assessment(self, verified, evidence, before, after, unresolved, improved=False) -> FixAssessment:
        comparison = {"before": before, "after": after}
        if verified is True:
            return FixAssessment(AssessmentStatus.SUCCESS, tuple(evidence), comparison, 1.0, ())
        if verified is None:
            return FixAssessment(AssessmentStatus.VERIFICATION_UNAVAILABLE, tuple(evidence), comparison,
                                 0.0, tuple(unresolved))
        if improved:
            return FixAssessment(AssessmentStatus.PARTIAL_SUCCESS, tuple(evidence), comparison,
                                 0.5, tuple(unresolved))
        return FixAssessment(AssessmentStatus.FAILED, tuple(evidence), comparison, 0.0, tuple(unresolved))

    def _result(self, problem, status, started, message, events, before=None, after=None,
                assessment=None, execution_succeeded=False, execution_details=None):
        return FixExecutionResult(
            str(uuid.uuid4()), problem.problem_id, problem.recommended_fix_workflow, status,
            started, datetime.now(timezone.utc), message, tuple(events),
            before if before is not None else {}, after if after is not None else {}, assessment,
            dict(problem.parameters), execution_succeeded, execution_details or {},
        )

    def _validation_error(self, problem, workflow) -> str | None:
        if workflow is None or not workflow.enabled:
            return "Workflow is not registered and enabled."
        if not workflow.executable or workflow.workflow_id not in self._EXECUTABLE:
            return "Workflow is advisory-only and cannot be executed."
        if problem.category not in workflow.supported_problem_types:
            return "Workflow is not compatible with the detected problem category."
        missing = [name for name in workflow.required_parameters if not problem.parameters.get(name)]
        if missing:
            return "Required workflow target is missing: " + ", ".join(missing)
        service_name = problem.parameters.get("service_name")
        if service_name and service_name not in self._SUPPORTED_SERVICE_NAMES:
            return "Service target is not in the approved service allowlist."
        adapter_name = problem.parameters.get("adapter_name")
        if adapter_name and (not isinstance(adapter_name, str) or len(adapter_name) > 128 or
                             any(char in adapter_name for char in "'\";`$|&<>\r\n")):
            return "Adapter target is invalid."
        if workflow.workflow_id == "safe_disk_cleanup":
            requested_root = Path(str(problem.parameters["temp_directory"]))
            root = requested_root.resolve()
            drive = str(problem.parameters["drive"]).rstrip("\\/").casefold()
            if root not in self.approved_cleanup_directories:
                return "Cleanup target is not an approved Windows temporary directory."
            if not root.exists() or not root.is_dir() or is_reparse_point(requested_root) or root.anchor.rstrip("\\/").casefold() != drive:
                return "Approved temporary-directory target is unavailable or belongs to another drive."
        return None

    def _pre_check(self, fix_id, problem, before):
        if fix_id == "network_flush_dns":
            return before.get("dns_resolves") is False
        if fix_id == "network_renew_ip":
            return before.get("adapter_name") == problem.parameters.get("adapter_name") and \
                (before.get("has_valid_ipv4") is False or before.get("has_gateway") is False)
        if fix_id == "network_restart_adapter":
            return before.get("adapter_name") == problem.parameters.get("adapter_name") and \
                before.get("adapter_state") in {"disabled", "down"}
        if fix_id in {"restart_print_spooler", "clear_stuck_print_jobs", "restart_supported_windows_service"}:
            if before.get("service_name") != problem.parameters.get("service_name"):
                return False
            if fix_id == "clear_stuck_print_jobs":
                return problem.parameters.get("service_name") == "Spooler" and before.get("pending_job_count", 0) > 0
            state = before.get("service_state")
            if state in {"paused", "start_pending", "stop_pending", "continue_pending", "pause_pending"}:
                return True
            if state != "stopped":
                return False
            start_type = before.get("service_start_type")
            if fix_id == "restart_print_spooler":
                return start_type in {"automatic", "manual"}
            return start_type in {"automatic", "boot", "system"}
        if fix_id == "safe_disk_cleanup":
            return before.get("temp_directory") == str(Path(problem.parameters["temp_directory"]).resolve()) and \
                before.get("eligible_temp_files", 0) > 0
        return False

    def _execute(self, fix_id, problem):
        parameters = problem.parameters
        if fix_id == "network_flush_dns":
            result = self._run(["ipconfig", "/flushdns"])
            return {"operation": "flush_dns", "exit_code": result.returncode}
        elif fix_id == "network_renew_ip":
            result = self._run(["ipconfig", "/renew", parameters["adapter_name"]], 60)
            return {"operation": "renew_ip", "adapter_name": parameters["adapter_name"], "exit_code": result.returncode}
        elif fix_id == "network_restart_adapter":
            env = dict(os.environ)
            env["MANJUAI_APPROVED_TARGET"] = parameters["adapter_name"]
            result = self._run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                                "Restart-NetAdapter -Name $env:MANJUAI_APPROVED_TARGET -Confirm:$false -ErrorAction Stop"], 45, env)
            return {"operation": "restart_adapter", "adapter_name": parameters["adapter_name"], "exit_code": result.returncode}
        elif fix_id in {"restart_print_spooler", "restart_supported_windows_service"}:
            return self._restart_service(parameters["service_name"])
        elif fix_id == "clear_stuck_print_jobs":
            return self._clear_print_jobs(parameters["service_name"])
        elif fix_id == "safe_disk_cleanup":
            return self._clean_old_temp_files(Path(parameters["temp_directory"]))
        else:
            raise ValueError("No executable implementation exists for workflow")

    def _run(self, args, timeout=30, env=None):
        return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout, env=env,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def _restart_service(self, name: str) -> dict:
        initial_state = self._query_service_state(name)
        if initial_state != "1":
            self._run(["sc", "stop", name])
            self._wait_for_service(name, "STOPPED")
        self._run(["sc", "start", name])
        self._wait_for_service(name, "RUNNING")
        return {"operation": "restart_service", "service_name": name, "initial_state_code": initial_state,
                "final_state_code": "4"}

    def _query_service_state(self, name: str) -> str:
        result = self._run(["sc", "query", name], 10)
        for line in result.stdout.splitlines():
            if line.strip().startswith("STATE"):
                parts = line.split()
                if len(parts) >= 3 and parts[2].isdigit():
                    return parts[2]
        raise ValueError(f"Service {name} returned an unrecognized state")

    def _wait_for_service(self, name: str, expected: str, timeout: float = 30) -> None:
        deadline = time.monotonic() + timeout
        expected_code = {"STOPPED": "1", "RUNNING": "4"}[expected]
        while time.monotonic() < deadline:
            if self._query_service_state(name) == expected_code:
                return
            time.sleep(0.25)
        raise TimeoutError(f"Service {name} did not reach {expected}")

    def _clear_print_jobs(self, service_name: str) -> dict:
        if service_name != "Spooler":
            raise ValueError("Print queue cleanup requires the Spooler target")
        initial_state = self._query_service_state(service_name)
        if initial_state != "1":
            self._run(["sc", "stop", service_name])
        try:
            if initial_state != "1":
                self._wait_for_service(service_name, "STOPPED")
            folder = self._windows_directory() / "System32" / "spool" / "PRINTERS"
            removed = 0
            skipped = 0
            failed = 0
            for child in folder.iterdir():
                if is_reparse_point(child):
                    skipped += 1
                elif child.is_file() and child.suffix.casefold() in {".shd", ".spl"}:
                    try:
                        child.unlink()
                        removed += 1
                    except OSError:
                        failed += 1
                else:
                    skipped += 1
        finally:
            self._run(["sc", "start", service_name])
            self._wait_for_service(service_name, "RUNNING")
        return {"operation": "clear_print_queue", "service_name": service_name,
                "approved_directory": str(folder), "files_removed": removed, "files_skipped": skipped,
                "failed_deletions": failed}

    def _clean_old_temp_files(self, root: Path) -> dict:
        requested_root = root
        root = root.resolve()
        if root not in self.approved_cleanup_directories or is_reparse_point(requested_root):
            raise ValueError("Cleanup target is outside the approved temporary-directory allowlist")
        cutoff = time.time() - 604800
        details = {"operation": "safe_temp_cleanup", "cleanup_directory": str(root), "files_examined": 0,
                   "eligible_files": 0, "files_removed": 0, "bytes_removed": 0,
                   "recent_files_skipped": 0, "reparse_points_skipped": 0,
                   "non_files_skipped": 0, "failed_deletions": 0}
        for child in root.iterdir():
            details["files_examined"] += 1
            if is_reparse_point(child):
                details["reparse_points_skipped"] += 1
                continue
            if not child.is_file():
                details["non_files_skipped"] += 1
                continue
            try:
                stat = child.stat()
            except OSError:
                details["failed_deletions"] += 1
                continue
            if stat.st_mtime >= cutoff:
                details["recent_files_skipped"] += 1
                continue
            details["eligible_files"] += 1
            try:
                child.unlink()
                details["files_removed"] += 1
                details["bytes_removed"] += stat.st_size
            except OSError:
                details["failed_deletions"] += 1
        return details

    @staticmethod
    def _windows_directory() -> Path:
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            length = ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer))
            if 0 < length < len(buffer):
                return Path(buffer.value)
        except (AttributeError, OSError):
            pass
        return Path(os.environ.get("SystemRoot", "C:\\Windows"))
