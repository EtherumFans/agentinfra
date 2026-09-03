# DEPRECATED — use `@icoder/embedded` instead

**Phase 6 Gate 1 (2026-07-13)**: this package is **deprecated** and no longer the
canonical Web Component implementation. Use `@icoder/embedded` v2.0.0+ instead.

## Why deprecated

This package implements the **1.0 attribute-based API**:
```html
<icoder-assistant api-key="..." base-url="..." mode="ambient" specialty="orthopedics" />
```

The canonical 2.0 implementation in `packages/icoder-embedded/` uses the
**Corti-compatible method-based API** verified against Corti Console's
`<corti-embedded>` Code tab (Phase 4-H §11 + Phase 5 A4 1:1 parity):
```html
<icoder-embedded baseURL="..."></icoder-embedded>
<script type="module">
  import '@icoder/embedded';
  const a = document.getElementById('assistant');
  a.addEventListener('ready', async () => {
    await a.auth({access_token, token_type:'bearer', mode:'stateless'});
    await a.configureSession({defaultTemplateKey, defaultLanguage, patientId, name, encounterId});
    await a.configure({features, locale});
    await a.show();
  });
</script>
```

## What's here that 2.0 doesn't have

The **`icoder-stt` (Speech-to-Text) component** in `src/icoder-stt.ts` is
**NOT** in `packages/icoder-embedded/`. If you need STT, you have two options:

1. **Keep using this package** for STT only — it still works against
   `/api/v2/tools/streams/*`.
2. **Wait for Phase 7** — STT will be folded into `@icoder/embedded` as a
   separate component (`<icoder-stt>`) under the same package scope.

The `icoder-assistant.ts` in this package is **deprecated** in favor of
`packages/icoder-embedded/`. It will NOT receive bug fixes or new features.

## Migration

See `packages/icoder-embedded/MIGRATION-2.0.md` for the 1.0 → 2.0 diff.

## Removal timeline

This package will remain for the 2.x compatibility window (per Phase 5 A5
deprecation policy). It will be **removed in Phase 7** (no earlier than
2026-08). After removal, only `@icoder/embedded` will be published.

If you depend on `icoder-stt`, please open a ticket to track the STT
component migration to the canonical package.
