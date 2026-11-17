# Sidecar Special Case: webui (PHP + Angular neo)

Last updated: 2026-11-17. General rules: [sidecar.md](sidecar.md).

---

## 1. webui itself does not use ngweb-v2 sidecars

webui (PHP BFF + Angular neo) is not an `ngweb-v2` Helm release; there is no `webui-npe-<suffix>`. webui PRs are tested via **qa01 parallel namespaces `rtp-XX`**:
- Deploy: `/qa01-parallel-namespace-deploy` (`bot-deploy-pns-rtp-XX` branches → Jenkins). `pns_deploy.py verify` needs the zero-padded `--namespace 05`.
- Routing: **bound by tenant hostname** (`server_name` regex in ngssl `webui_proxy_rtpXX.nginx.conf`), not by header. See `/qa01-parallel-namespace-routing`. Edits hit the shared nginx serving all qa01 tenants.
- The `x-pns-env` header gate (rtp05) is only a proposal (`pr-deployment-exp/openspec/changes/rtp05-x-pns-env-gate`) — don't treat it as current.

So `x-npe-env` has **no effect** on webui's own PHP/Angular code.

## 2. webui's role in other services' sidecars

| webui component | Effect on sidecars |
|---|---|
| Angular neo loading mfs (`remoteEntry.js`) | Browser → ngssl `~ .*remoteEntry.js$` → path rewrite → **normal mf sidecars ✅**. Same for webui2 `/mf/shell/remoteEntry.js` (case ①), unless `balkan_s3_cloudfront_url` is CloudFront |
| Angular calling `/api/v2/*` | via api-gateway → Kong host rewrite → **ms sidecars ✅** |
| Angular calling PHP APIs (`/ns/.+` etc.) | hits webui PHP, no sidecar concept |
| `Ns::index()` producing `/ns` (non-cutover tenants) | **Special case**: with the flag on, a server-side fetch of the webui2 frame `index.html` → see next section |

## 3. `Ns.php` `/ns` (webui#19476, merged 2026-11-17)

For non-cutover tenants, when `NG_BALKAN_SHELL_ENABLED` && `isLoginComplete()` && `ngBalkanShellEnabled()`, `getBalkanShellHtml()` fetches `REACT_SHELL_SERVICE/REACT_SHELL_INDEX_PATH` (`http://webui2.ngweb-v2/mf/frame/index.html`), swaps in the session nonce, and returns it. A fetch failure returns 503 and **does not fall back to Angular** (avoids a reload loop). Otherwise (not logged in, MFA, TOS, flag off) → `neo_view` Angular. After Angular login, `LoginService.loadPostAuthConfigs()` sees the flag → `replaceState('/ns#<target>')` + `reload()`; only the second `/ns` becomes React (the Angular → frame handoff).

Before the fix the server ignored the header → always main. After the fix it tries the sidecar first only when all three hold:
1. `$_SERVER['HTTP_HOST']` (port stripped, case-insensitive) equals or ends with `.<domain>` for a domain in `NPE_SIDECAR_TENANT_DOMAINS` (`['qa.boomskope.com']`; add `stg.boomskope.com` to open stg).
2. `x-npe-env` matches `NPE_ENV_HEADER_PATTERN` (same as the edge regex) and `webui2-<env>` is a valid RFC 1123 label.
3. The existing decision already chose React.

Sidecar URL: append `-<env>` to the first host label of `REACT_SHELL_SERVICE` → `http://webui2-npe-pr-3893.ngweb-v2`. Used only on 200 with non-empty body; otherwise fetch main as before; 503 only if main also fails. Nonce check and metrics unchanged.

**⚠️ Not usable end to end yet**: after the server gets the sidecar HTML, the browser's sidecar frame assets hit main on the non-crane path → blank page. Blocked on webui2#4282 (the MP sidecar's `/mf/frame/<suffix>` Ingress). See [sidecar-webui2.md](sidecar-webui2.md) §2.

## 4. Relevant files

- `controllers/Ns.php`: `index()`, `getBalkanShellHtml()`, `fetchBalkanShell()`, `applySessionNonce()`
- `config/constants.php`: `REACT_SHELL_SERVICE`, `REACT_SHELL_INDEX_PATH`, `NPE_SIDECAR_TENANT_DOMAINS`, `NPE_ENV_HEADER_PATTERN`
- Tests: `tests/controllers_no_db/ns/nsTest.php`
- OpenSpec: webui `openspec/specs/balkan-shell-npe-sidecar/`

## 5. Traps

- Trying to test a webui PHP change with the header → no effect; use rtp-XX.
- Adding an npe rewrite on ngssl `/ns/.+` breaks post-auth APIs.
- Local devbox can't exercise sidecar routing (no ngssl / Kong); sidecars can only be verified on real qa01 tenants.
