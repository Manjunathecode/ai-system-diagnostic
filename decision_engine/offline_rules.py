"""Deterministic problem detection using diagnostics and an approved workflow allow-list."""
from __future__ import annotations

import uuid
import tempfile
from pathlib import Path

from models.diagnostic import DiagnosticResult, DiagnosticStatus, Severity
from models.problem import DetectedProblem
from fixes.registry import ApprovedFixRegistry


class OfflineDecisionEngine:
    def __init__(self, registry: ApprovedFixRegistry, disk_free_threshold_percent: float = 10.0) -> None:
        self.registry = registry
        self.disk_free_threshold_percent = disk_free_threshold_percent

    def analyze(self, results: list[DiagnosticResult]) -> list[DetectedProblem]:
        problems: list[DetectedProblem] = []
        for result in results:
            details = result.details
            if result.name == "CPU usage" and details.get("cpu_percent", 0) >= 90:
                problems.append(self._problem("System Performance", Severity.HIGH, 0.90, (f"CPU usage: {details['cpu_percent']}%",), "High processor usage in the collected sample.", "performance_resource_review"))
            elif result.name == "Memory usage" and details.get("memory_percent", 0) >= 90:
                problems.append(self._problem("System Performance", Severity.HIGH, 0.90, (f"Memory usage: {details['memory_percent']}%",), "Available physical memory is critically low.", "performance_resource_review"))
            elif result.name == "Drive capacity":
                temp_root = Path(tempfile.gettempdir()).resolve()
                for drive in details.get("drives", []):
                    if drive.get("free_percent", 100) < self.disk_free_threshold_percent:
                        drive_name = str(drive.get("drive", "")).rstrip("\\/")
                        parameters = {"temp_directory": str(temp_root), "drive": drive_name} \
                            if temp_root.anchor.rstrip("\\/").casefold() == drive_name.casefold() else {}
                        problems.append(self._problem("Disk Space", Severity.HIGH, 0.95,
                            (f"{drive.get('drive')} free space: {drive.get('free_percent')}%",), "Insufficient free disk capacity.", "safe_disk_cleanup", parameters))
            elif result.name == "Network connectivity":
                internet, dns = details.get("internet_connectivity"), details.get("dns_resolution")
                adapter_name = details.get("primary_adapter")
                if internet is True and dns is False:
                    problems.append(self._problem("DNS", Severity.MEDIUM, 0.95, ("External IP connectivity succeeded.", "DNS name resolution failed."), "DNS resolution problem.", "network_flush_dns", {"adapter_name": adapter_name} if adapter_name else {}))
                elif internet is False and details.get("ip_configuration_valid") is False and adapter_name:
                    problems.append(self._problem("Network", Severity.MEDIUM, 0.85, ("External IP connectivity failed.", "IP configuration is invalid."), "The active adapter does not have a valid IP configuration.", "network_renew_ip", {"adapter_name": adapter_name}))
                if details.get("gateway_reachability") is False and adapter_name:
                    problems.append(self._problem("IP Configuration", Severity.MEDIUM, 0.85, ("Default gateway did not respond.",), "Gateway or local IP configuration problem.", "network_renew_ip", {"adapter_name": adapter_name}))
                disabled = [item.get("Name") for item in details.get("adapters", []) if str(item.get("Status", "")).lower() == "disabled"]
                if disabled:
                    problems.append(self._problem("Network Adapter", Severity.MEDIUM, 0.95, ("Disabled adapters: " + ", ".join(disabled),), "A network adapter is disabled.", "network_restart_adapter", {"adapter_name": disabled[0]}))
            elif result.name == "Printer diagnostics":
                spooler = details.get("print_spooler") or {}
                if spooler.get("state") in {"stopped", "paused", "stop_pending"}:
                    problems.append(self._problem("Printer", Severity.MEDIUM, 0.95, (f"Print Spooler state: {spooler.get('state')}",), "Print Spooler service failure.", "restart_print_spooler", {"service_name": "Spooler"}))
                elif details.get("stuck_jobs"):
                    problems.append(self._problem("Printer", Severity.MEDIUM, 0.90, (f"Stuck print jobs: {len(details['stuck_jobs'])}",), "One or more print jobs are stuck.", "clear_stuck_print_jobs", {"service_name": "Spooler"}))
            elif result.name == "Important service status":
                for service in details.get("services", []):
                    name = service.get("Name")
                    if name != "Spooler" and name in details.get("needs_attention", []):
                        problems.append(self._problem("Windows Services", Severity.MEDIUM, 0.90,
                            (f"Service {name} state: {service.get('state')}", f"Start type: {service.get('start_type')}"),
                            "An applicable monitored Windows service is not running.", "restart_supported_windows_service",
                            {"service_name": name}))
            elif result.name == "Device status" and (details.get("devices_with_errors") or details.get("disabled_devices")):
                count = len(details.get("devices_with_errors", [])) + len(details.get("disabled_devices", []))
                problems.append(self._problem("Device Errors", Severity.MEDIUM, 0.90, (f"{count} device(s) have an error or disabled state.",), "Device Manager reports a device problem.", "device_error_review"))
        return problems

    def _problem(self, category: str, severity: Severity, confidence: float, evidence: tuple[str, ...], cause: str, workflow_id: str, parameters: dict | None = None) -> DetectedProblem:
        workflow = self.registry.get(workflow_id)
        if workflow is None:
            raise ValueError(f"Rule attempted to select unapproved workflow: {workflow_id}")
        return DetectedProblem(str(uuid.uuid4()), category, severity, confidence, evidence, cause,
                               workflow_id, workflow.requires_administrator, workflow.risk.value != "low", workflow.risk, parameters or {})
