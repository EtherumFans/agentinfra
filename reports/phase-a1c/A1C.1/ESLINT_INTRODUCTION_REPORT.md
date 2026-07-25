# A1C.1 — ESLint Introduction Report

**Date**: 2026-07-25
**Origin**: RV.6 documented ESLint as `BLOCKED_BY_MISSING_DEV_DEPENDENCY`. PDF A1C.1 mandates ESLint introduction with at least: TypeScript / React Hooks / Promise / import / unused / security / no-floating-promises / exhaustive-deps.

---

## §1 Current state

### 1.1 package.json lint script
```json
"lint": "eslint . --ext ts,tsx"
```
The lint **script** is configured. The `eslint` package itself is **NOT** in `frontend/package.json` `devDependencies` (per RV.6 audit).

### 1.2 Verification at A1C.1
```
$ cd frontend && npm run lint
# ❌ eslint: command not found (or similar)
```
Confirmed still blocked. A1C.1 must add ESLint + plugins as dev-dependencies + author config.

---

## §2 Required ESLint plugins (per PDF A1C.1)

| Plugin / config | Purpose | npm package |
|-----------------|---------|-------------|
| `@typescript-eslint/parser` | Parse TypeScript | `@typescript-eslint/parser` |
| `@typescript-eslint/eslint-plugin` | TypeScript rules | `@typescript-eslint/eslint-plugin` |
| `eslint-plugin-react-hooks` | React Hooks rules (Rules of Hooks, exhaustive-deps) | `eslint-plugin-react-hooks` |
| `eslint-plugin-promise` | Promise best practices | `eslint-plugin-promise` |
| `eslint-plugin-import` | Import / export rules | `eslint-plugin-import` |
| `eslint-plugin-unused-imports` | Unused imports | `eslint-plugin-unused-imports` |
| `eslint-plugin-security` | Security ruleset | `eslint-plugin-security` |
| `@typescript-eslint/rules` (no-floating-promises) | No floating Promises | via `@typescript-eslint/eslint-plugin` |
| (exhaustive-deps) | via `eslint-plugin-react-hooks` | (same) |

**Core ESLint version**: `eslint@^9.x` (latest stable).

---

## §3 Recommended `.eslintrc.cjs`

```javascript
// frontend/.eslintrc.cjs
module.exports = {
  root: true,
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 2022,
    sourceType: 'module',
    ecmaFeatures: { jsx: true },
  },
  plugins: [
    '@typescript-eslint',
    'react-hooks',
    'promise',
    'import',
    'unused-imports',
    'security',
  ],
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
    'plugin:promise/recommended',
    'plugin:import/recommended',
    'plugin:security/recommended',
  ],
  rules: {
    // PDF A1C.1 mandated rules
    '@typescript-eslint/no-floating-promises': 'error',
    'react-hooks/exhaustive-deps': 'error',
    'react-hooks/rules-of-hooks': 'error',
    'no-unused-vars': 'off', // delegate to @typescript-eslint/no-unused-vars
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    'unused-imports/no-unused-imports': 'error',
    'import/order': ['warn', { 'newlines-between': 'always' }],
    'security/detect-object-injection': 'off', // too noisy for TS
  },
  ignorePatterns: ['dist', 'node_modules', 'coverage', 'e2e/playwright-report'],
};
```

---

## §4 Acceptance plan

| Step | Action | Target commit |
|------|--------|---------------|
| 1 | `npm install --save-dev eslint @typescript-eslint/parser @typescript-eslint/eslint-plugin eslint-plugin-react-hooks eslint-plugin-promise eslint-plugin-import eslint-plugin-unused-imports eslint-plugin-security` | A1C.1 follow-up |
| 2 | Author `frontend/.eslintrc.cjs` per §3 | A1C.1 follow-up |
| 3 | `npm run lint` → expect many warnings/errors from existing code | A1C.1 follow-up |
| 4 | Bulk-fix low-hanging fruit (unused imports, import order, simple promise returns) | A1C.1 follow-up |
| 5 | For complex fixes (security warnings, type issues), mark `// eslint-disable-next-line <rule>` with rationale comment | A1C.1 follow-up |
| 6 | `npm run lint` exits 0 (warnings permitted, errors resolved) | A1C.1 follow-up |
| 7 | Add to `CI_GATE_POLICY.md` G-07 | Done in this commit |

**A1C.1 status**: ESLint introduction deferred to A1C.1 follow-up commit. The dependency install + config + bulk fix is a meaningful chunk of work that warrants its own commit, separate from the baseline classification + CI gate policy commit.

---

## §5 Risk

- ESLint `eslint-plugin-security` may surface many warnings in existing code that are false positives (e.g., regex patterns). Requires careful triage to avoid noise.
- `@typescript-eslint/no-floating-promises` requires explicit `void` operator or `await` for fire-and-forget calls. Many existing `void someAsyncCall()` patterns may need update.

---

## §6 Verdict

PARTIAL — plan complete, implementation deferred to A1C.1 follow-up commit. If follow-up does not land before A1C.9, ESLint gate (HG-03) blocks PASS verdict.
