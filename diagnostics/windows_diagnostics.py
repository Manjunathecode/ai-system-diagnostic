"""Read-only Windows diagnostics collected through documented OS interfaces."""
from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import socket
import subprocess
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from models.diagnostic import DiagnosticResult, DiagnosticStatus, Severity
from diagnostics.service_state import normalize_service_record, service_needs_attention


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def _powershell(script: str, timeout: int = 20) -> Any:
    """Run a read-only PowerShell query and decode its JSON output."""
    prefix = "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", prefix + script],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    output = completed.stdout.strip()
    return json.loads(output) if output else []


def _items(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    return value if isinstance(value, list) else [value]


class WindowsDiagnosticEngine:
    """Runs bounded, read-only checks and converts failures into structured findings."""
    def __init__(self, disk_free_threshold_percent: float = 10.0) -> None:
        self.scan_id = str(uuid.uuid4())
        self.disk_free_threshold_percent = disk_free_threshold_percent

    def run_full_scan(self, progress: Callable[[str, int], None] | None = None) -> list[DiagnosticResult]:
        checks = [self.system_information, self.cpu_memory_health, self.disk_health, self.network_diagnostics,
                  self.windows_services, self.printer_diagnostics, self.device_diagnostics]
        results: list[DiagnosticResult] = []
        for index, check in enumerate(checks, start=1):
            if progress:
                progress(check.__name__.replace("_", " ").title(), int((index - 1) * 100 / len(checks)))
            try:
                results.extend(check())
            except Exception as error:  # individual collectors must never abort a full scan
                results.append(self._failure_result(check.__name__, error))
        if progress:
            progress("Scan complete", 100)
        return results

    def run_targeted(self, category: str, progress: Callable[[str, int], None] | None = None) -> list[DiagnosticResult]:
        if category == "System Health":
            return self.run_full_scan(progress)
        routes = {
            "System Performance": [self.cpu_memory_health, self.disk_health], "Disk Space": [self.disk_health],
            "Network": [self.network_diagnostics], "DNS": [self.network_diagnostics],
            "IP Configuration": [self.network_diagnostics], "Network Adapter": [self.network_diagnostics],
            "Printer": [self.printer_diagnostics, self.windows_services], "Windows Services": [self.windows_services],
            "Device Errors": [self.device_diagnostics],
        }
        checks = routes.get(category, [])
        results = []
        for index, check in enumerate(checks, 1):
            if progress: progress(f"Targeted: {check.__name__}", int((index - 1) * 100 / max(len(checks), 1)))
            try: results.extend(check())
            except Exception as error: results.append(self._failure_result(check.__name__, error))
        if progress: progress("Targeted diagnostics complete", 100)
        return results

    def _failure_result(self, check_name: str, error: Exception) -> DiagnosticResult:
        diagnostic_error = str(error.stderr or error) if isinstance(error, subprocess.CalledProcessError) else str(error)
        message = f"{type(error).__name__}: {diagnostic_error[:1500]}"
        lowered = message.lower()
        if isinstance(error, PermissionError) or "access is denied" in lowered or "access denied" in lowered:
            status = DiagnosticStatus.PERMISSION_REQUIRED
        elif isinstance(error, (subprocess.TimeoutExpired, TimeoutError, json.JSONDecodeError)):
            status = DiagnosticStatus.ERROR
        elif isinstance(error, FileNotFoundError):
            status = DiagnosticStatus.UNAVAILABLE
        else:
            status = DiagnosticStatus.NOT_RUN
        return self._result("Diagnostic Engine", check_name, status, Severity.LOW,
                            f"Check could not be completed: {message}", {"error_type": type(error).__name__})

    def _result(self, category: str, name: str, status: DiagnosticStatus, severity: Severity, summary: str, details: dict[str, Any]) -> DiagnosticResult:
        return DiagnosticResult(self.scan_id, category, name, status, severity, summary, datetime.now(timezone.utc), details)

    def _memory(self) -> MEMORYSTATUSEX:
        state = MEMORYSTATUSEX()
        state.dwLength = ctypes.sizeof(state)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
            raise OSError("GlobalMemoryStatusEx failed")
        return state

    def system_information(self) -> list[DiagnosticResult]:
        memory = self._memory()
        processor = _powershell("Get-CimInstance Win32_Processor | Select-Object -First 1 Name,NumberOfCores,NumberOfLogicalProcessors | ConvertTo-Json -Compress")
        details = {"windows_version": platform.platform(), "computer_name": socket.gethostname(), "processor": processor,
                   "total_ram_bytes": memory.ullTotalPhys, "available_ram_bytes": memory.ullAvailPhys,
                   "uptime_seconds": int(ctypes.windll.kernel32.GetTickCount64() / 1000)}
        return [self._result("System Information", "System overview", DiagnosticStatus.PASSED, Severity.INFO,
                             "Basic Windows system information collected.", details)]

    def cpu_memory_health(self) -> list[DiagnosticResult]:
        cpu = _powershell("Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average | Select-Object -ExpandProperty Average | ConvertTo-Json -Compress")
        memory_processes = _items(_powershell("Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 10 ProcessName,Id,CPU,WorkingSet64 | ConvertTo-Json -Compress"))
        cpu_processes = _items(_powershell("Get-Process | Sort-Object CPU -Descending | Select-Object -First 10 ProcessName,Id,CPU | ConvertTo-Json -Compress"))
        memory = self._memory()
        ram_usage = int(memory.dwMemoryLoad)
        if cpu is None or cpu == [] or isinstance(cpu, bool):
            raise ValueError("Windows did not return a CPU usage sample; CPU usage is unknown.")
        cpu_value = float(cpu)
        if not 0 <= cpu_value <= 100:
            raise ValueError("Windows returned an invalid CPU usage sample.")
        cpu_status = DiagnosticStatus.WARNING if cpu_value >= 90 else DiagnosticStatus.PASSED
        ram_status = DiagnosticStatus.WARNING if ram_usage >= 90 else DiagnosticStatus.PASSED
        return [
            self._result("CPU and Memory", "CPU usage", cpu_status, Severity.HIGH if cpu_status == DiagnosticStatus.WARNING else Severity.INFO,
                         f"Current processor load is {cpu_value:.0f}%.", {"cpu_percent": cpu_value, "top_cpu_processes": cpu_processes,
                         "cpu_process_note": "CPU values are cumulative processor time, useful for identifying long-running CPU consumers."}),
            self._result("CPU and Memory", "Memory usage", ram_status, Severity.HIGH if ram_status == DiagnosticStatus.WARNING else Severity.INFO,
                         f"Physical memory usage is {ram_usage}%.", {"memory_percent": ram_usage, "high_memory_processes": memory_processes}),
        ]

    def disk_health(self) -> list[DiagnosticResult]:
        drives = []
        low = []
        errors = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            path = f"{letter}:\\"
            if os.path.exists(path):
                try:
                    usage = shutil.disk_usage(path)
                except OSError as error:
                    errors.append({"drive": path, "error": str(error)})
                    continue
                free_percent = round(usage.free / usage.total * 100, 1) if usage.total else 0
                entry = {"drive": path, "total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free, "free_percent": free_percent}
                drives.append(entry)
                if free_percent < self.disk_free_threshold_percent:
                    low.append(path)
        status = DiagnosticStatus.WARNING if low else DiagnosticStatus.UNAVAILABLE if errors or not drives else DiagnosticStatus.PASSED
        return [self._result("Disk Health", "Drive capacity", status, Severity.HIGH if low else Severity.INFO,
                             ("Low free space detected on: " + ", ".join(low) if low else "Drive capacity collection is incomplete." if errors or not drives else f"All detected drives have at least {self.disk_free_threshold_percent:g}% free space.") + (" Some drives could not be read." if errors else ""),
                             {"drives": drives, "low_space_drives": low, "collection_errors": errors, "threshold_percent": self.disk_free_threshold_percent, "health_indicator": "Capacity only; SMART was not collected."})]

    def network_diagnostics(self) -> list[DiagnosticResult]:
        adapters = _items(_powershell("Get-NetAdapter | Select-Object Name,ifIndex,Status,MacAddress,LinkSpeed,InterfaceDescription | ConvertTo-Json -Compress"))
        config = _items(_powershell("Get-NetIPConfiguration | Where-Object {$_.NetAdapter.Status -eq 'Up'} | ForEach-Object {[pscustomobject]@{InterfaceAlias=$_.InterfaceAlias;InterfaceIndex=$_.InterfaceIndex;IPv4Address=@($_.IPv4Address.IPAddress);DefaultIPGateway=@($_.IPv4DefaultGateway.NextHop);DNSServer=@($_.DNSServer.ServerAddresses)}} | ConvertTo-Json -Compress"))
        internet = bool(_powershell("Test-Connection -ComputerName 1.1.1.1 -Count 1 -Quiet | ConvertTo-Json -Compress", 10))
        dns = bool(_powershell("$answer = try { Resolve-DnsName example.com -Type A -ErrorAction Stop | Select-Object -First 1 | Out-Null; $true } catch { $false }; $answer | ConvertTo-Json -Compress", 12))
        gateways = [gateway for item in config for gateway in (item.get("DefaultIPGateway") or [])]
        gateway_reachable = None
        if gateways:
            gateway_reachable = bool(_powershell(f"Test-Connection -ComputerName '{gateways[0]}' -Count 1 -Quiet | ConvertTo-Json -Compress", 10))
        primary = next((item for item in config if item.get("IPv4Address")), config[0] if config else {})
        ipv4_addresses = primary.get("IPv4Address") or []
        if isinstance(ipv4_addresses, str):
            ipv4_addresses = [ipv4_addresses]
        valid_ipv4 = any(address and not str(address).startswith("169.254.") for address in ipv4_addresses)
        primary_adapter = primary.get("InterfaceAlias")
        ip_configuration_valid = bool(primary_adapter and valid_ipv4 and gateways)
        status = DiagnosticStatus.PASSED if internet and dns and ip_configuration_valid and gateway_reachable is not False else DiagnosticStatus.WARNING
        return [self._result("Network", "Network connectivity", status, Severity.MEDIUM if status == DiagnosticStatus.WARNING else Severity.INFO,
                             f"Internet reachability: {'available' if internet else 'unavailable'}; DNS resolution: {'available' if dns else 'unavailable'}.",
                             {"adapters": adapters, "ip_configurations": config, "internet_connectivity": internet, "dns_resolution": dns,
                              "gateway_reachability": gateway_reachable, "primary_adapter": primary_adapter,
                              "ip_configuration_valid": ip_configuration_valid})]

    def windows_services(self) -> list[DiagnosticResult]:
        expected = ("Spooler", "wuauserv", "bits", "Dnscache", "NlaSvc", "Netman")
        raw_services = _items(_powershell(
            "Get-Service -Name Spooler,wuauserv,bits,Dnscache,NlaSvc,Netman -ErrorAction SilentlyContinue | "
            "Select-Object Name,DisplayName,Status,StartType | ConvertTo-Json -Compress"
        ))
        by_name = {str(item.get("Name", "")).lower(): item for item in raw_services}
        services = [normalize_service_record(by_name.get(name.lower()), name) for name in expected]
        needs_attention = [item["Name"] for item in services if service_needs_attention(item)]
        unavailable = [item["Name"] for item in services if item["state"] in {"unknown", "not_run", "unavailable"}]
        if needs_attention:
            status, severity = DiagnosticStatus.WARNING, Severity.MEDIUM
            summary = "Monitored services needing attention: " + ", ".join(needs_attention)
        elif unavailable:
            status, severity = DiagnosticStatus.UNAVAILABLE, Severity.LOW
            summary = "Service state unavailable for: " + ", ".join(unavailable)
        else:
            status, severity = DiagnosticStatus.PASSED, Severity.INFO
            summary = "All applicable monitored services are in an expected state."
        return [self._result("Windows Services", "Important service status", status, severity, summary,
                             {"services": services, "needs_attention": needs_attention, "unavailable_services": unavailable})]

    def printer_diagnostics(self) -> list[DiagnosticResult]:
        printers = _items(_powershell("Get-CimInstance Win32_Printer | Select-Object Name,Default,PrinterStatus,WorkOffline,DetectedErrorState | ConvertTo-Json -Compress"))
        jobs = _items(_powershell("Get-CimInstance Win32_PrintJob -ErrorAction Stop | Select-Object Name,JobStatus,TotalPages | ConvertTo-Json -Compress"))
        raw_spooler = _powershell("Get-Service Spooler | Select-Object Name,DisplayName,Status,StartType | ConvertTo-Json -Compress")
        spooler = normalize_service_record(raw_spooler if isinstance(raw_spooler, dict) else None, "Spooler")
        unhealthy = [printer.get("Name") for printer in printers if printer.get("WorkOffline")]
        error_printers = [printer.get("Name") for printer in printers
                          if printer.get("DetectedErrorState") not in (None, 0) or printer.get("PrinterStatus") in (6, 7)]
        stuck_states = ("error", "offline", "paperout", "blocked", "userintervention", "paused")
        stuck_jobs = [job for job in jobs if any(marker in str(job.get("JobStatus", "")).replace(" ", "").lower() for marker in stuck_states)]
        if spooler["state"] in {"unknown", "not_run", "unavailable"}:
            status, severity = DiagnosticStatus.UNAVAILABLE, Severity.LOW
        elif spooler["state"] != "running" or unhealthy or error_printers or stuck_jobs:
            status, severity = DiagnosticStatus.WARNING, Severity.MEDIUM
        else:
            status, severity = DiagnosticStatus.PASSED, Severity.INFO
        return [self._result("Printer", "Printer diagnostics", status, severity,
                             f"{len(printers)} printer(s), {len(jobs)} pending print job(s).",
                             {"printers": printers, "print_spooler": spooler, "pending_jobs": jobs,
                              "stuck_jobs": stuck_jobs, "offline_printers": unhealthy, "error_printers": error_printers})]

    def device_diagnostics(self) -> list[DiagnosticResult]:
        devices = _items(_powershell("Get-CimInstance Win32_PnPEntity | Where-Object {$_.ConfigManagerErrorCode -ne 0} | Select-Object Name,Status,ConfigManagerErrorCode,PNPDeviceID | ConvertTo-Json -Compress", 35))
        disabled = _items(_powershell("Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object {$_.Status -eq 'Disabled'} | Select-Object FriendlyName,Class,Status,InstanceId | ConvertTo-Json -Compress", 35))
        count = len(devices) + len(disabled)
        return [self._result("Devices", "Device status", DiagnosticStatus.WARNING if count else DiagnosticStatus.PASSED,
                             Severity.MEDIUM if count else Severity.INFO,
                             f"{count} device(s) reported an error or disabled status.", {"devices_with_errors": devices, "disabled_devices": disabled})]
