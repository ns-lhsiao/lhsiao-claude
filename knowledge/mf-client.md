# mf-client (netskope-ng-base/frontends/mf-client)

## Run jest via `yarn test` (craco), never `npx jest` directly (2026-11-06)

- Symptom: `npx jest <path>` fails with `SyntaxError: Unexpected token 'export'` from
  `@netskope-ui/core/dist/es/index.js` (ESM inside a CJS-consumed package), or earlier with
  `ReferenceError: MutationObserver is not defined` when the suite needs the jsdom29 env.
- Root cause: mf-client is a CRA + craco repo. The CRA default jest config (babel transform,
  jsdom env, transformIgnorePatterns covering `@netskope-ui/*`) is only applied through
  `craco test`. Bare `npx jest` uses the minimal `jest` block in `package.json`, which lacks
  the CRA transform pipeline.
- Fix: always run `yarn test --testPathPattern="<name>"` (script is `craco test --watchAll=false`).
- Related: for suites that hit `MutationObserver is not defined`, add the docblock
  `/** @jest-environment <rootDir>/src/test-utils/jest-environment-jsdom29.js */` at the top
  of the test file (sibling suites already do this — see
  `src/components/SteeringConfigModal/PrivateAppsGatewaySelection.test.tsx`). The custom env
  uses `pretendToBeVisual: true` so `MutationObserver` is defined. mf-cfw has a similar
  custom-env trap — see [[mf-cfw]].

## Submodule bumps surface in the parent `netskope-ng-base` worktree

- `frontends/mf-client` is a git submodule of `netskope-ng-base`. Committing inside the
  submodule leaves the parent worktree with `M frontends/mf-client` until the parent is
  updated to point at the new submodule SHA. Boot-feature flow: do the feature work in the
  submodule's own branch (`pr/ENG-XXX/...`), push, PR against mf-client's `master`. Parent
  submodule bump is a separate, later step (usually handled by release tooling).
