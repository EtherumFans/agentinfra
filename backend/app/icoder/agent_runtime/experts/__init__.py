"""iCoDer Runtime — Experts (Phase 2).

This package contains the **real** Expert implementations that the
Orchestrator's Delegator routes to. Phase 1 only had a sync-async
bridge in ``orchestrator/wiring.py``; M1 of the MedCodER Runtime
Upgrade adds the first real Expert — :class:`CodingExpert`.

Future phases:
  - Phase 5: drg-expert, compliance-expert, dip-expert (and
    deprecate the remaining bridge code in ``wiring.py``).
"""
