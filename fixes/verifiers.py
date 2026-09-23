"""Read-only, deterministic, target-specific state snapshots and verification."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

from diagnostics.service_state import normalize_service_state, normalize_start_type
from fixes.path_safety import is_reparse_point
from models.problem import DetectedProblem


class WindowsStateReader:
    _VERIFIABLE = frozenset({
        "network_flush_dns", "network_renew_ip", "network_restart_adapter",
        "restart_print_spooler", "clear_stuck_print_jobs", "safe_disk_cleanup",
        "restart_supported_windows_service",
    })

    @classmethod
    def verifiable_workflow_ids(cls) -> frozenset[str]:
        return cls._VERIFIABLE

    def _command(self, args: list[str], timeout: int = 20, env: dict | None = None) -> tuple[int, str, str]:
        try:
            done = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return done.returncode, done.stdout, done.stderr
        except (OSError, subprocess.SubprocessError) as error:
            return -1, "", f"{type(error).__name__}: {error}"

    def _powershell_json(self, script: str, argument: str | None = None, timeout: int = 20):
        args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
        env = None
        if argument is not None:
            env = dict(os.environ)
            env["MANJUAI_APPROVED_TARGET"] = argument
        code, stdout, stderr = self._command(args, timeout, env)
        if code != 0:
            raise OSError(f"Read-only state query failed ({code}): {stderr.strip()}")
        return json.loads(stdout.strip()) if stdout.strip() else None

    def target_resource(self, fix_id: str, problem: DetectedProblem) -> str | None:
        if fix_id in {"restart_print_spooler", "clear_stuck_print_jobs", "restart_supported_windows_service"}:
            return problem.parameters.get("service_name")
        if fix_id in {"network_renew_ip", "network_restart_adapter"}:
            return problem.parameters.get("adapter_name")
        if fix_id == "safe_disk_cleanup":
            return problem.parameters.get("temp_directory")
        if fix_id == "network_flush_dns":
            return "dns_resolver"
        return None

    @staticmethod
    def _same(before: dict, after: dict, key: str) -> bool:
        return bool(before.get(key)) and before.get(key) == after.get(key)

    def _dns_snapshot(self) -> dict:
        context = self._network_context()
        try:
            context.update({"resource": "dns_resolver", "dns_resolves": bool(socket.gethostbyname("example.com"))})
        except socket.gaierror:
            context.update({"resource": "dns_resolver", "dns_resolves": False})
        return context

    def _network_context(self, adapter_name: str | None = None) -> dict:
        selector = "-InterfaceAlias $env:MANJUAI_APPROVED_TARGET" if adapter_name else "| Where-Object {$_.NetAdapter.Status -eq 'Up'} | Select-Object -First 1"
        script = (
            f"$c=Get-NetIPConfiguration {selector} -ErrorAction Stop; "
            "$a=$c.NetAdapter; [pscustomobject]@{adapter_name=$c.InterfaceAlias; adapter_state=$a.Status; "
            "ipv4=@($c.IPv4Address|ForEach-Object IPAddress); gateways=@($c.IPv4DefaultGateway|ForEach-Object NextHop); "
            "dns_servers=@($c.DNSServer.ServerAddresses)} | ConvertTo-Json -Depth 4 -Compress"
        )
        try:
            data = self._powershell_json(script, adapter_name) or {}
        except OSError:
            data = {}
        for key in ("ipv4", "gateways", "dns_servers"):
            if isinstance(data.get(key), str):
                data[key] = [data[key]]
            elif data.get(key) is None:
                data[key] = []
        internet = self._powershell_json(
            "Test-Connection -ComputerName 1.1.1.1 -Count 1 -Quiet | ConvertTo-Json -Compress", timeout=10
        )
        try:
            dns_resolves = bool(socket.gethostbyname("example.com"))
        except socket.gaierror:
            dns_resolves = False
        return {"adapter_name": data.get("adapter_name") or adapter_name,
                "adapter_state": str(data.get("adapter_state") or "unknown").strip().lower(),
                "ipv4_addresses": data.get("ipv4", []), "gateways": data.get("gateways", []),
                "dns_servers": data.get("dns_servers", []), "dns_resolves": dns_resolves,
                "internet_reachable": bool(internet)}

    def _ip_snapshot(self, adapter_name: str) -> dict:
        context = self._network_context(adapter_name)
        addresses = context.get("ipv4_addresses") or []
        gateways = context.get("gateways") or []
        valid = [value for value in addresses if value and not str(value).startswith("169.254.") and str(value) != "0.0.0.0"]
        gateway_reachable = None
        if gateways:
            gateway_reachable = bool(self._powershell_json(
                "Test-Connection -ComputerName $env:MANJUAI_APPROVED_TARGET -Count 1 -Quiet | ConvertTo-Json -Compress",
                str(gateways[0]), 10,
            ))
        context.update({"has_valid_ipv4": bool(valid), "has_gateway": bool(gateways),
                        "gateway_reachable": gateway_reachable})
        return context

    def _adapter_snapshot(self, adapter_name: str) -> dict:
        context = self._network_context(adapter_name)
        data = self._powershell_json(
            "Get-NetAdapter -Name $env:MANJUAI_APPROVED_TARGET -ErrorAction Stop | Select-Object Name,Status | ConvertTo-Json -Compress",
            adapter_name,
        ) or {}
        context["adapter_name"] = data.get("Name") or adapter_name
        context["adapter_state"] = str(data.get("Status") or "unknown").strip().lower()
        context["connectivity"] = context["internet_reachable"]
        return context

    def _service_snapshot(self, service_name: str) -> dict:
        data = self._powershell_json(
            "Get-Service -Name $env:MANJUAI_APPROVED_TARGET -ErrorAction Stop | Select-Object Name,Status,StartType | ConvertTo-Json -Compress",
            service_name,
        ) or {}
        return {"service_name": data.get("Name") or service_name,
                "service_state": normalize_service_state(data.get("Status")),
                "service_start_type": normalize_start_type(data.get("StartType"))}

    def _queue_snapshot(self, service_name: str) -> dict:
        service = self._service_snapshot(service_name)
        jobs = self._powershell_json(
            "@(Get-CimInstance Win32_PrintJob -ErrorAction Stop | Select-Object Name,JobStatus) | ConvertTo-Json -Compress"
        ) or []
        if isinstance(jobs, dict):
            jobs = [jobs]
        service.update({"pending_job_count": len(jobs), "job_states": [item.get("JobStatus") for item in jobs]})
        return service

    @staticmethod
    def _temp_snapshot(temp_directory: str) -> dict:
        root = Path(temp_directory).resolve()
        usage = shutil.disk_usage(root.anchor or root)
        cutoff = time.time() - 604800
        eligible = []
        try:
            for child in root.iterdir():
                try:
                    if child.is_file() and not is_reparse_point(child) and child.stat().st_mtime < cutoff:
                        eligible.append(child.stat().st_size)
                except OSError:
                    continue
        except OSError as error:
            raise OSError(f"Temporary directory cannot be inspected: {error}") from error
        return {"temp_directory": str(root), "drive": root.anchor, "eligible_temp_files": len(eligible),
                "eligible_temp_bytes": sum(eligible), "free_bytes": usage.free,
                "free_percent": round(usage.free * 100 / usage.total, 2)}

    def snapshot(self, fix_id: str, problem: DetectedProblem) -> dict:
        target = self.target_resource(fix_id, problem)
        if fix_id == "network_flush_dns":
            return self._dns_snapshot()
        if fix_id == "network_renew_ip" and target:
            return self._ip_snapshot(target)
        if fix_id == "network_restart_adapter" and target:
            return self._adapter_snapshot(target)
        if fix_id == "restart_print_spooler" and target:
            return self._service_snapshot(target)
        if fix_id == "clear_stuck_print_jobs" and target:
            return self._queue_snapshot(target)
        if fix_id == "safe_disk_cleanup" and target:
            return self._temp_snapshot(target)
        if fix_id == "restart_supported_windows_service" and target:
            return self._service_snapshot(target)
        return {}

    def verify(self, fix_id: str, before: dict, after: dict) -> tuple[bool | None, tuple[str, ...], tuple[str, ...]]:
        if fix_id == "network_flush_dns":
            success = before.get("dns_resolves") is False and after.get("dns_resolves") is True
            return success, (f"DNS before: {before.get('dns_resolves')}", f"DNS after: {after.get('dns_resolves')}"), () if success else ("DNS resolution did not transition from failed to successful.",)
        if fix_id == "network_renew_ip":
            same = self._same(before, after, "adapter_name")
            success = same and before.get("has_valid_ipv4") is False and after.get("has_valid_ipv4") is True and after.get("has_gateway") is True and after.get("gateway_reachable") is not False
            return success, (f"Adapter: {after.get('adapter_name')}", f"Valid IPv4 after: {after.get('has_valid_ipv4')}", f"Gateway after: {after.get('has_gateway')}", f"Gateway reachable: {after.get('gateway_reachable')}"), () if success else ("Target adapter did not gain a verified valid IP configuration.",)
        if fix_id == "network_restart_adapter":
            same = self._same(before, after, "adapter_name")
            success = same and before.get("adapter_state") != "up" and after.get("adapter_state") == "up" and after.get("connectivity") is True
            return success, (f"Adapter: {after.get('adapter_name')}", f"State after: {after.get('adapter_state')}", f"Connectivity after: {after.get('connectivity')}"), () if success else ("Target adapter did not return Up with connectivity.",)
        if fix_id in {"restart_print_spooler", "restart_supported_windows_service"}:
            same = self._same(before, after, "service_name")
            success = same and before.get("service_state") != "running" and after.get("service_state") == "running"
            return success, (f"Service: {after.get('service_name')}", f"State before: {before.get('service_state')}", f"State after: {after.get('service_state')}"), () if success else ("Target service did not transition to running.",)
        if fix_id == "clear_stuck_print_jobs":
            same = self._same(before, after, "service_name")
            success = same and isinstance(before.get("pending_job_count"), int) and before.get("pending_job_count", 0) > 0 and after.get("pending_job_count") == 0 and after.get("service_state") == "running"
            return success, (f"Service: {after.get('service_name')}", f"Jobs before: {before.get('pending_job_count')}", f"Jobs after: {after.get('pending_job_count')}", f"Spooler after: {after.get('service_state')}"), () if success else ("Target print queue was not verified empty with Spooler running.",)
        if fix_id == "safe_disk_cleanup":
            same = self._same(before, after, "temp_directory")
            before_count, after_count = before.get("eligible_temp_files"), after.get("eligible_temp_files")
            if not isinstance(before_count, int) or not isinstance(after_count, int):
                return None, ("Eligible temporary files could not be measured.",), ("Cleanup verification unavailable.",)
            recovered = (after.get("free_bytes") or 0) - (before.get("free_bytes") or 0)
            before_bytes, after_bytes = before.get("eligible_temp_bytes"), after.get("eligible_temp_bytes")
            success = same and before_count > 0 and after_count < before_count and \
                isinstance(before_bytes, int) and isinstance(after_bytes, int) and after_bytes < before_bytes and recovered > 0
            return success, (f"Eligible files before: {before_count}", f"Eligible files after: {after_count}", f"Observed free-space change: {recovered} bytes"), () if success else ("Eligible temporary-file count did not decrease.",)
        return None, ("No verifier is registered for this workflow.",), ("Verification unavailable.",)

    def improvement(self, fix_id: str, before: dict, after: dict) -> bool:
        if fix_id == "network_flush_dns":
            return before.get("dns_resolves") is False and after.get("dns_resolves") is True
        if fix_id == "network_renew_ip":
            return self._same(before, after, "adapter_name") and ((not before.get("has_valid_ipv4") and after.get("has_valid_ipv4")) or (not before.get("has_gateway") and after.get("has_gateway")))
        if fix_id == "network_restart_adapter":
            return self._same(before, after, "adapter_name") and before.get("adapter_state") != "up" and after.get("adapter_state") == "up"
        if fix_id in {"restart_print_spooler", "restart_supported_windows_service"}:
            return self._same(before, after, "service_name") and before.get("service_state") != "running" and after.get("service_state") == "running"
        if fix_id == "clear_stuck_print_jobs":
            return self._same(before, after, "service_name") and isinstance(before.get("pending_job_count"), int) and isinstance(after.get("pending_job_count"), int) and after["pending_job_count"] < before["pending_job_count"]
        if fix_id == "safe_disk_cleanup":
            return self._same(before, after, "temp_directory") and isinstance(before.get("eligible_temp_files"), int) and isinstance(after.get("eligible_temp_files"), int) and after["eligible_temp_files"] < before["eligible_temp_files"] and (after.get("eligible_temp_bytes") or 0) < (before.get("eligible_temp_bytes") or 0)
        return False
