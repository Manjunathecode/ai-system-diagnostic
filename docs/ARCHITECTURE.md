# Architecture

```mermaid
flowchart TD
  A[User or System Symptoms] --> B[Conversation Layer]
  B --> C[Diagnostic Engine]
  C --> D[Offline Decision Engine]
  D --> E[Optional Hybrid AI Reasoning]
  E --> F[Approved Fix Registry]
  F --> G[Safety Layer]
  G --> H[Autonomous Fix Executor]
  H --> I[Verification Engine]
  I --> J[Fallback or Escalation]
  J --> K[Audit and Reports]
```

The optional AI layer returns structured reasoning only. It cannot issue commands, change the registry, bypass confirmation/elevation, or execute repairs. The executor maps a finite local registry to reviewed implementations.
