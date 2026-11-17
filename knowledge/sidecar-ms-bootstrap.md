# Sidecar Special Case: ms-bootstrap (crane `/ns` producer)

Last updated: 2026-11-17. General rules: [sidecar.md](sidecar.md). webui2 side: [sidecar-webui2.md](sidecar-webui2.md).

---

## 1. Role

For crane cutover tenants (`/etc/nginx/crane_tenants.map`), `/ns` skips webui PHP: ngssl `$crane_webui_proxy_pass` → `aws_nlb` → ms-bootstrap `AppController.root()`. It **replaces** `Ns.php`; it does not sit behind webui.

| Condition | Result |
|---|---|
| `globals.ng_balkan_shell_enabled` on (**no login-state check**, unlike Ns.php) | `getReactShellHtml()` fetches `${REACT_SHELL_SERVICE}/${REACT_SHELL_INDEX_PATH}` (`mf/frame/index.html`), swaps nonce → React; failure → 503 |
| flag off | `getAngularIndexScripts()` fetches `${ANGULAR_UI_SERVICE}/ng/dist/prod-lazy/angular_view.txt` into the `index` template → Angular |

The `/ns` HTML is decided server-side → like Ns.php, it's an `x-npe-env` exception (the server fetch doesn't carry the header).

## 2. Fix (ms-bootstrap#433, ENG-1419882, merged 2026-11-17)

Same rules as webui#19476; only the tenant source differs:
1. `req.tenantUrl` (filled by `tenant-info.middleware.ts` from core DB `uiHostname`) suffix-matches `NPE_SIDECAR_TENANT_DOMAINS` (`['qa.boomskope.com']`).
2. `x-npe-env` matches `NPE_ENV_HEADER_PATTERN`.
3. React was already chosen.

Sidecar URL: append `-<env>` to the first host label of `REACT_SHELL_SERVICE`. Used only on 200 with non-empty body, else main.

**The crane path works end to end**: the browser's follow-up `/mf/frame/assets/<sidecar hash>.js` goes `aws_nlb` → AWS ALB → the **webui2 AWS leg**'s `/mf/frame/<suffix>` rule → 200. Prerequisite: the PR's **AWS leg is deployed** (webui2 `cicd-pr.yaml` `publish_manifest_sidecar_aws`); with only the MP leg, crane tenants won't see the sidecar.

With the flag off (Angular), a request with the header still gets Angular — exactly why the nginx bypass was rejected.

## 3. Why not the nginx bypass (service#111366, open, **do not merge**)

#111366 had the edge serve `/mf/frame/<env>/index.html` directly for crane `/ns` requests with the header, skipping ms-bootstrap:
- nginx can't read the tenant DB's `ng_balkan_shell_enabled` → flag-off tenants with the header get forced into React.
- #433's code would never run; no domain restriction.
- Declaring `error_page` in the `/ns` location makes it **stop inheriting** server-level `error_page` (maintenance, 507, 404), affecting all tenants.

## 4. qa01 ngssl state notes

- The 2026-11-12 `/ns` hotfix has been reverted; `aws_crane/webui_route_mappings.conf` = service `develop`. Leftover backups `.broken-20261112101409`, `.hotfix-v1-20261112103605` can be removed after #433 is verified live.
- `aws_crane/upstream_map_definition.conf` also carries an ENG-1421154 reporting-cutover map (backup `.erased-202611131357`) — not ours.
- This VM (`ngsslwebui01`) serves **all** qa01 tenants: back up first → `sudo nginx -t -c /etc/nginx/nginx-sslwebui.conf` (`-c` required) → coordinate, then `sudo supervisorctl signal HUP nginx`. `tsh ssh` hangs silently on an expired profile; run `timeout 20 tsh status` first.

## 5. Dev traps

- `.env.test` has `REACT_SHELL_SERVICE="localhost"`, not a valid URL; specs must override it with a real URL in `beforeEach` and restore in `afterEach`.
- The flag cache is request-scoped (`TenantDbFactory` `Scope.REQUEST`, scope propagates upward) → flag changes need no pod restart.
- Files: `src/app.controller.ts`, `src/common/npe-sidecar.ts`, `src/constants/general.constants.ts`, `src/.../tenant-info.middleware.ts`.
- OpenSpec: `pr-deployment-exp/openspec/specs/ms-bootstrap-react-shell-npe-sidecar/`; `changes/ns-npe-sidecar-crane-routing/` to be archived as superseded after live verification.
- **Unverified**: whether ms-bootstrap's own PRs can be tested via a sidecar (`/ns` doesn't go through api-gateway, so the Kong host rewrite doesn't apply). Check its deploy model before assuming.
