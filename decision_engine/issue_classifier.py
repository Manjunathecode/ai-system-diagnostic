"""Offline natural-language categorization. Input remains data, never commands."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Classification:
    category: str
    confidence: float
    follow_up_questions: tuple[str, ...]
    candidate_categories: tuple[str, ...] = ()

class OfflineIssueClassifier:
    _RULES = (
        ("Printer", ("printer", "print", "spooler"), "Is the printer shown as online, and are jobs stuck in its queue?"),
        ("Disk Space", ("disk space", "storage", "drive is full", "disk is full", "low disk", "low storage", "full drive"), "Which drive is low on space, and did Windows show a storage warning?"),
        ("DNS", ("website", "websites", "dns", "browser"), "Can other devices on the same network open websites?"),
        ("Network", ("internet", "network", "wi-fi", "wifi", "connected"), "Are other devices on the same network able to access the internet?"),
        ("Network Adapter", ("adapter", "ethernet", "wireless adapter", "wifi missing"), "Is the network adapter visible and enabled in Windows settings?"),
        ("IP Configuration", ("ip address", "gateway", "dhcp", "169.254"), "Does the computer show a valid IP address and default gateway?"),
        ("System Performance", ("slow", "freeze", "lag", "performance", "high cpu", "memory"), "Does the slowdown affect all applications or only one?"),
        ("Windows Services", ("service", "windows update", "update"), "Did the problem start after a Windows update or restart?"),
        ("Device Errors", ("usb", "device", "not detecting", "driver", "hardware"), "Is the device visible in Device Manager with an error icon?"),
    )
    def classify(self, description: str) -> Classification:
        text = description.lower()
        if any(phrase in text for phrase in ("system health", "check my system", "any issue", "any issues", "windows issue", "windows issues", "check windows")):
            return Classification("System Health", 0.9, ("I will run a safe read-only full system health scan. Continue?",))
        if any(term in text for term in ("wifi", "wi-fi", "internet", "network")) and any(term in text for term in ("slow", "speed", "disconnect", "not working", "no internet")) and not any(term in text for term in ("missing", "disabled", "printer", "memory", "cpu")):
            return Classification("Network", 0.85, ("Does the connection problem affect all websites and other devices, or only this computer?",), ("Network",))
        # Specific failure expressions win over broad words such as "wifi" or "connected".
        if (("missing" in text and any(term in text for term in ("wifi", "wi-fi", "adapter"))) or
                any(phrase in text for phrase in ("wireless adapter", "adapter disabled", "adapter is disabled", "ethernet adapter"))):
            return Classification("Network Adapter", 0.9, ("Is the network adapter visible and enabled in Windows settings?",), ("Network Adapter",))
        if any(word in text for word in ("website", "websites", "dns", "browser")):
            return Classification("DNS", 0.9, ("Can other devices on the same network open websites?",), ("DNS",))
        matches = [(category, question) for category, words, question in self._RULES if any(word in text for word in words)]
        # Preserve category order while removing overlaps within one category.
        matches = list(dict.fromkeys(matches))
        if len(matches) != 1:
            candidates = tuple(category for category, _ in matches)
            question = ("This may involve " + " or ".join(candidates) + ". Which symptom is primary?"
                        if candidates else "What is affected: internet, printing, a slow computer, disk space, or a device? You can also enter 'check my system health' for a full scan.")
            return Classification("Unknown", 0.25 if matches else 0.0, (question,), candidates)
        category, question = matches[0]
        return Classification(category, 0.85, (question,), (category,))
