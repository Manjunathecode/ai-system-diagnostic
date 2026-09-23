"""The finite, reviewed allow-list of repair workflow definitions."""
from __future__ import annotations

from models.fix_workflow import FixWorkflow, WorkflowRisk


class ApprovedFixRegistry:
    def __init__(self, workflows: tuple[FixWorkflow, ...] | None = None) -> None:
        self._workflows = {workflow.workflow_id: workflow for workflow in workflows or self._defaults()}

    def get(self, workflow_id: str) -> FixWorkflow | None:
        return self._workflows.get(workflow_id)

    def contains(self, workflow_id: str) -> bool:
        return workflow_id in self._workflows

    def all(self) -> tuple[FixWorkflow, ...]:
        return tuple(self._workflows.values())

    def validate(self, executable_ids: set[str] | frozenset[str], verifiable_ids: set[str] | frozenset[str]) -> list[str]:
        errors = []
        for workflow in self._workflows.values():
            if not workflow.enabled or not workflow.executable:
                continue
            if workflow.workflow_id not in executable_ids:
                errors.append(f"{workflow.workflow_id}: executable implementation missing")
            if workflow.workflow_id not in verifiable_ids:
                errors.append(f"{workflow.workflow_id}: compatible verifier missing")
        return errors

    @staticmethod
    def _defaults() -> tuple[FixWorkflow, ...]:
        entries = (
            ("performance_resource_review", "Review resource-intensive processes", ("System Performance",), WorkflowRisk.LOW, False, False, ()),
            ("safe_disk_cleanup", "Safe temporary-file cleanup", ("Disk Space",), WorkflowRisk.MEDIUM, False, True, ("temp_directory", "drive")),
            ("network_flush_dns", "Flush DNS resolver cache", ("DNS",), WorkflowRisk.LOW, False, True, ()),
            ("network_renew_ip", "Renew DHCP IP lease", ("Network", "IP Configuration", "DNS"), WorkflowRisk.MEDIUM, True, True, ("adapter_name",)),
            ("network_restart_adapter", "Restart network adapter", ("Network Adapter",), WorkflowRisk.HIGH, True, True, ("adapter_name",)),
            ("restart_print_spooler", "Restart Print Spooler", ("Printer",), WorkflowRisk.MEDIUM, True, True, ("service_name",)),
            ("clear_stuck_print_jobs", "Clear stuck print jobs", ("Printer",), WorkflowRisk.HIGH, True, True, ("service_name",)),
            ("restart_supported_windows_service", "Restart approved Windows service", ("Windows Services",), WorkflowRisk.HIGH, True, True, ("service_name",)),
            ("device_error_review", "Review device error", ("Device Errors",), WorkflowRisk.LOW, False, False, ()),
        )
        return tuple(FixWorkflow(fix_id, name, name, problems, risk, requires_administrator=admin,
                                 pre_check="registered pre-check", execute="registered fixed operation", verify="registered verification",
                                 rollback_if_available=None, audit_log=True, enabled=True, executable=executable,
                                 required_parameters=required)
                     for fix_id, name, problems, risk, admin, executable, required in entries)
