# Safety model

- Natural-language and AI output are data, never executable input.
- Only registered, compatible workflows can reach the executor.
- Higher-risk workflows require confirmation; declared workflows require administrator rights.
- Verification determines final status. Recommendations are not success claims.
- Fallback is bounded and registry-controlled; unresolved issues escalate.
- Demo mode always uses dry-run execution and a simulated state reader.
- Reports redact secret-like fields before export.
