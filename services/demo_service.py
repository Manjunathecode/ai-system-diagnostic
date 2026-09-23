"""Clearly labelled, fully simulated portfolio demos; no real repair path is used."""
from __future__ import annotations
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from diagnostics.windows_diagnostics import WindowsDiagnosticEngine
from decision_engine.offline_rules import OfflineDecisionEngine
from fixes.executor import AutonomousFixEngine
from models.diagnostic import DiagnosticResult, DiagnosticStatus, Severity

class DemoReader:
    def __init__(self, verdict=True): self.verdict, self.calls = verdict, {}
    def snapshot(self, fix_id, problem):
        position = self.calls.get(fix_id, 0); self.calls[fix_id] = position + 1
        before = position == 0
        states = {
            "network_flush_dns": {"resource": "dns_resolver", "dns_resolves": False if before or not self.verdict else True},
            "network_renew_ip": {"adapter_name": problem.parameters.get("adapter_name", "Wi-Fi"),
                                 "has_valid_ipv4": False if before or not self.verdict else True,
                                 "has_gateway": False if before or not self.verdict else True,
                                 "gateway_reachable": False if before or not self.verdict else True},
            "restart_print_spooler": {"service_name": "Spooler", "service_state": "stopped" if before or not self.verdict else "running", "service_start_type": "automatic"},
            "safe_disk_cleanup": {"temp_directory": problem.parameters.get("temp_directory"),
                                  "eligible_temp_files": 2 if before or not self.verdict else 0,
                                  "eligible_temp_bytes": 1000 if before or not self.verdict else 0,
                                  "free_bytes": 100 if before or not self.verdict else 110},
        }
        return states.get(fix_id, {"simulated": True, "workflow": fix_id})
    def verify(self, fix_id, before, after): return self.verdict, (f"Simulated verification for {fix_id}: {self.verdict}",), () if self.verdict else ("Simulated symptom remains unresolved.",)
    def improvement(self, fix_id, before, after): return self.verdict and before != after

class DemoService:
    SCENARIOS = ("DNS resolution failure", "Print Spooler stopped", "Low disk space", "High CPU usage", "Unresolved escalation")
    def __init__(self, registry): self.registry = registry
    def run(self, scenario: str):
        now = datetime.now(timezone.utc); scan = f"demo-{scenario.lower().replace(' ', '-') }"
        temp_root = Path(tempfile.gettempdir()).resolve()
        finding = {
            "DNS resolution failure": DiagnosticResult(scan, "Network", "Network connectivity", DiagnosticStatus.WARNING, Severity.MEDIUM, "Simulated DNS failure", now, {"internet_connectivity": True, "dns_resolution": False, "primary_adapter": "Wi-Fi"}),
            "Print Spooler stopped": DiagnosticResult(scan, "Printer", "Printer diagnostics", DiagnosticStatus.WARNING, Severity.MEDIUM, "Simulated stopped spooler", now, {"print_spooler": {"Name": "Spooler", "state": "stopped", "start_type": "automatic"}, "offline_printers": [], "printers": [], "pending_jobs": [], "stuck_jobs": []}),
            "Low disk space": DiagnosticResult(scan, "Disk Health", "Drive capacity", DiagnosticStatus.WARNING, Severity.HIGH, "Simulated low space", now, {"drives": [{"drive": temp_root.anchor, "free_percent": 2.0, "free_bytes": 1000}], "low_space_drives": [temp_root.anchor]}),
            "High CPU usage": DiagnosticResult(scan, "CPU and Memory", "CPU usage", DiagnosticStatus.WARNING, Severity.HIGH, "Simulated high CPU", now, {"cpu_percent": 96.0, "top_cpu_processes": [{"ProcessName": "DemoProcess", "CPU": 99}]}),
            "Unresolved escalation": DiagnosticResult(scan, "Network", "Network connectivity", DiagnosticStatus.WARNING, Severity.MEDIUM, "Simulated unresolved DNS", now, {"internet_connectivity": True, "dns_resolution": False, "primary_adapter": "Wi-Fi"}),
        }[scenario]
        problems = OfflineDecisionEngine(self.registry).analyze([finding])
        attempts, escalation = (), None
        if problems:
            # dry_run=True is the hard demo isolation boundary: _execute is never called.
            attempts, escalation = AutonomousFixEngine(self.registry, dry_run=True, reader=DemoReader(scenario != "Unresolved escalation"), max_attempts=2).run_with_recovery(problems[0], user_confirmed=True)
        return {"simulation": True, "scenario": scenario, "findings": [finding], "problems": problems, "attempts": attempts, "escalation": escalation}
