# Phase 7 Gate 11 — Patient Context Isolation & Recovery E2E

**Status**: PASS_GATE11_PATIENT_CONTEXT_ISOLATION_VERIFIED
**Date**: 2026-07-14
**Depends on**: Gate 10 (demos run in real browser)

## Objective

Per Phase 7 §11, Gate 11 verifies that the partner-embedded widget correctly
isolates patient PHI across patient switches AND across page reloads. This is
the partner-trust gate — partners will not embed iCoDer if there is any chance
of one patient's PHI bleeding into another patient's session, or persisting
across reloads.

Five behaviors must hold:

1. **Patient context set** — `configureSession({patientId, name, encounterId})`
   populates `_patientContext` and stamps `_contextId`
2. **Cross-patient warn** — switching `patientId` without first calling
   `clearPatientContext()` fires a `console.warn` flagging PHI bleed risk
3. **Clear emits event** — `clearPatientContext()` emits
   `patient.context.cleared` with `reason: 'host_invoked_clear'` and resets state
4. **Full session clear** — `clearSession()` emits `session.cleared` AND clears
   auth as well as patient context
5. **Reload safety** — page reload must NOT restore prior PHI; widget starts
   fresh with empty `_patientContext`, empty `_contextId`, cleared `_auth`

## Verification — Playwright MCP E2E

Loaded `http://127.0.0.1:8000/examples/medical-coding/`, set JWT, drove the
widget through the full isolation sequence via `page.evaluate()`.

### Result 1 — configure + cross-patient warn

```js
await el.configureSession({ patientId: 'P-2026-001', name: '张三', encounterId: 'E-20260713-001', ... })
// patient1 = { patientId: 'P-2026-001', name: '张三', contextId: 'E-20260713-001' }

await el.configureSession({ patientId: 'P-2026-002', name: '李四', ... }) // WITHOUT clear
// crossPatientBlocked: false (warns, doesn't throw — partner stays in control)
// crossPatientWarn: "[icoder-embedded] configureSession() called with a different patientId (P-2026-002) without first calling clearPatientContext(). Cross-patient PHI bleed risk — call clearPatientContext() on patient switch."
```

### Result 2 — clearPatientContext + clearSession

```js
el.clearPatientContext()
// capturedEvents[0] = { name: 'patient.context.cleared', contextId: '', reason: 'host_invoked_clear' }
// after = { patientId: undefined, contextId: '' }

await el.configureSession({ patientId: 'P-2026-002', name: '李四', ... }) // now clean
// patient2 = { patientId: 'P-2026-002', name: '李四', contextId: 'E-20260713-002' }

el.clearSession()
// capturedEvents[1] = { name: 'session.cleared', contextId: '', reason: 'host_invoked_clear' }
// afterClearAll = { patientId: undefined, contextId: '', authState: 'cleared' }
```

### Result 3 — page reload

```js
// Before reload: _patientContext = { patientId: 'P-2026-001', name: '张三', ... }
// sessionStorage.setItem('phase7_gate11_reload_marker', 'pre-reload')
// page.reload()

// After reload:
// markerStillThere: 'pre-reload'         ← reload happened
// patientContextAfterReload: {}           ← PHI cleared (empty object)
// contextIdAfterReload: ''                ← no context
// authAfterReload: 'cleared'              ← JWT not retained
// messagesAfterReload: 'no_field'         ← fresh widget instance
```

## iCoDer ADVANTAGE vs Corti (preserved)

- **Explicit patient context API** — Corti uses only `templateKey`, no
  `patientId`/`name`/`encounterId` fields. iCoDer's explicit context is the
  substrate that makes the cross-patient warn and clear events possible.
- **`patient.context.cleared` / `session.cleared` events** — Corti has no
  equivalent. iCoDer emits them so HIS/EMR hosts can confirm PHI flush in their
  own audit logs.
- **Cross-patient warn** — Corti has no equivalent. The warn fires before any
  PHI bleed occurs, so partner developers catch the bug in dev.
- **In-memory only** — `_patientContext` is never written to `localStorage`,
  `sessionStorage`, or cookies (verified Gate 6 §11.3). Page reload is the
  automatic safety net.

## Files

No code changes required — Gate 11 verified behaviors that Phase 6 Gate 2
already shipped. Screenshot:
`reports/phase7/phase7_gate11_patient_context_isolation.png`.

## Verdict

**PASS_GATE11_PATIENT_CONTEXT_ISOLATION_VERIFIED** — all 5 behaviors hold:
configure populates context, cross-patient warn fires, clearPatientContext
emits `patient.context.cleared`, clearSession emits `session.cleared`, page
reload wipes all in-memory PHI.

## Next

- Gate 12: 合作伙伴参考应用 (partner reference app — hard checkpoint D)
- Final: Phase 7 验收报告 (acceptance report)
