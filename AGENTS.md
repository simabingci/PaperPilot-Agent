# PaperPilot engineering rules

Validate untrusted inputs once at their boundary; keep validated internal values typed.
Catch errors only where the application can act on them. Never substitute mock output for failed inference.
Keep simple single-use logic inline; extract functions for reuse or substantive responsibilities.
Ask before adding speculative, low-probability defensive machinery.
Use only public example data. Never execute analyzed repository code.
Run tests and update validation evidence when changing behavior. Public GitHub release requires owner approval.
