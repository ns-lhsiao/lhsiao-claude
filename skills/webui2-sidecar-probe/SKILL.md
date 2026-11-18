---
name: webui2-sidecar-probe
description: >-
  Live-probe whether a qa tenant's /ns actually lands on a webui2 PR sidecar
  (x-npe-env). Reports what was requested, who produced /ns (webui PHP vs
  ms-bootstrap/crane), how Balkan rendered (React /mf/frame vs Angular +
  /mf/shell remoteEntry), and whether follow-up assets were served by the
  sidecar pod. Triggers on "probe sidecar", "live probe <tenant> x-npe-env",
  "/ns 有沒有吃到 sidecar", "is /ns on the sidecar", "/webui2-sidecar-probe".
  Read-only (GETs only). For k8s-side deploy state use sidecar-deploy-status.
---

# webui2 sidecar probe

Run:

```bash
~/.claude/skills/webui2-sidecar-probe/scripts/probe.sh <tenant-host> <npe-env> [cookie]
# e.g. probe.sh cpcs-auth-3.qa.boomskope.com npe-pr-4071
```

Cookie optional (`'ci_session=...'`). Without it the PHP path always shows the
Angular login page and `/mf/shell/remoteEntry.js` is a 404 (auth_request
masquerade), so post-login shell / Angular-embedded cases need a cookie. Never
echo the cookie value back in the report.

## Report to user (in this order)

1. **戳了什麼** — the requests (`/ns` ±header, `/mf/frame/index.html`, assets, build-info).
2. **/ns producer** — PHP vs ms-bootstrap and why.
3. **Balkan render** — React frame (case ②/④) vs Angular + `/mf/shell` (①/③); sidecar or main entry.
4. **Assets** — sidecar-only / both / broken per file.
5. **build-info + leg skew** — if any ⚠️, suggest `sidecar-deploy-status webui2 <env>`.

## How the script decides

| Question | Signal | Why |
|---|---|---|
| Producer | `Set-Cookie: ci_session=` present → PHP | CodeIgniter session; ms-bootstrap never sets it (verified by source grep). |
| | else crane map snapshot `~/ns/git/webui-crane-project/qa01_crane_tenants.md` (override `CRANE_MAP=`) | Snapshot can be stale (lhsiao/mitchw were in snapshot yet PHP-served 2026-11-18). Live map: `ngsslwebui01:/etc/nginx/crane_tenants.map` (needs VPN DNS). |
| | NOT `Expires: 1981` / `X-XSS-Protection: 0` | ms-bootstrap `app.module.ts` copies PHP cache headers + helmet; both producers send them. |
| Shell | `/ns` HTML has `/mf/frame/assets/index-*.js` → React frame; has `UI_Layer/dist` → Angular | First unhashed file decides the build (see knowledge `crane-webui2-render.md` §5). |
| Sidecar /ns | `/ns`+hdr entry == sidecar `/mf/frame/index.html` entry ≠ main entry | Server-side curl must have forwarded the header. |
| Asset owner | hdr 200 / no-hdr 404 → sidecar-only ✅; 200/200 → shared hash or main fallback ⚠️ (not proof); hdr ≠200 → broken | Edge falls back to main on 404, so only sidecar-only hashes prove the sidecar pod. |
| Leg skew | `/mf/frame/build-info.json` vs `/mf/shell/build-info.json` commit (both +hdr) | Crane `/mf/frame` → AWS leg (EKS); `/mf/shell` → MP leg (qa01). Different commits = one leg not redeployed. |

## Traps

- zsh: don't `curl ${h:+-H "$h"}` (one arg, leading space → 400); script is bash with arrays.
- `/ns/.+` is the post-auth API, not the entry — probe only `/ns`.
- `balkan_s3_cloudfront_url` non-empty → browser bypasses ngssl, header useless for Angular-embedded.

Background: `~/.claude/knowledge/crane-webui2-render.md`, `knowledge/sidecar-webui2.md`.
