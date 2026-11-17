# ngweb-v2 PR Sidecar — 通則

最後更新：2026-11-17。特例：[sidecar-webui2.md](sidecar-webui2.md)（含 AWS leg）、[sidecar-webui.md](sidecar-webui.md)、[sidecar-ms-bootstrap.md](sidecar-ms-bootstrap.md)。
操作面（查 run、算 release name、教人掛 header）用 `/sidecar` skill；本檔記「為什麼會這樣」與踩過的坑。

---

## 1. 一句話

sidecar = 同一個 namespace（`ngweb-v2`）裡多一個 branch-isolated Helm release `{service}-npe-{suffix}`，靠 **Kubernetes label + 帶 suffix 的 Ingress path** 隔離，不靠 namespace。使用者 URL 不變，只加一個 request header `x-npe-env: npe-<suffix>`。

## 2. 一般情況的路由（99% 的 mf-* / ms-*）

| 流量 | 誰處理 header | 機制 | fallback |
|---|---|---|---|
| `/mf/*`（mf 靜態檔、`remoteEntry.js`） | **ngssl**（edge nginx，`service` repo） | **改 path**：`/mf/<app>/x` → `/mf/<app>/<env>/x`，再 proxy 給 `ngweb_mf`/ngweb-fe；sidecar Ingress 吃 `/mf/<app>/<suffix>` prefix，pod 端（或 Ingress rewrite-target）再剝掉 env 段 | 404 → `@mf_npe_fallback` 打原路徑（main） |
| `/api/v2/*`（ms-*、v2 API） | **api-gateway**（Kong，`api-gateway-controller`） | **改 upstream host**：`ns-upstream-target-overrider` plugin 把 `ms-<svc>.ngweb[-v2]` → `ms-<svc>-<env>.ngweb[-v2]`，path 不變 | NXDOMAIN → default upstream；sidecar 存在但 0 healthy pod → **502**（刻意不 fallback） |

- header 驗證：`^npe-[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$`（ngssl `webui_proxy.nginx.conf` 的 map；不合格 → 空字串 = 不走 sidecar）。
- 只在 NPE 生效（`boomskope.com` / `enable_npe_env_routing`）；prod 忽略 header。
- 同一個 header 同時驅動 mf 與 ms 兩半，但 **mf 和 ms 是各自的 release**：mf-client PR 只部署 `mf-client-npe-<suffix>`，要測後端改動必須另外有 `ms-<svc>-npe-<suffix>`。

**例外**就是「第一個沒有 hash 的檔案不是瀏覽器經過 edge 去拿的」的情況 —— server 端自己 curl 回 HTML 時 header 不會自動跟著走。webui2 的 `/ns` 就是這種（見 [sidecar-webui2.md](sidecar-webui2.md)）。

## 3. 生命週期

| 項目 | 規則 |
|---|---|
| Release name | `{service}-npe-{suffix}`；`deployment_suffix` 輸入 sanitize：非 `[a-zA-Z0-9-]` → `-`、lowercase、**`cut -c1-10`**（截的是輸入，不含 `npe-`）、去頭尾 `-` |
| Auto suffix | `pr-{PR number}`（8 位數 PR 才會被截） |
| 觸發 | 現行：service repo `cicd-pr.yaml` → ngweb-actions `service_cicd.yaml` 整合 lifecycle，**approval label `ci:sidecar-approved:npe-<suffix>` 就是紀錄**（`ci:sidecar-denied` 互斥，多個 approval label → fail closed）。舊：`pr-sidecar.yaml`（`auto-pr-sidecar` environment gate）/ `on-demand-sidecar-deploy.yml`（`workflow_dispatch`，已有 deprecation spec） |
| Artifacts | docker `ngweb-release-docker`（PR build）/ helm `ngweb-release-helm`；sidecar values 檔用 image override 指回 release-docker，因為 mainline stack 檔 pin 的是 develop/master track |
| 部署 | 一律經 in-cluster pipeline（Hubble manifest → YAP/Spinnaker）；**GH runner 沒有 kubeconfig，不能直接 `helm upgrade`** |
| Values | `sidecar-value-template.yaml`（`{{ SUFFIX }}`）render 成 `sidecar-value.yaml`，放在 pipeline overrides pattern **最後一項**，蓋過 mainline stack 值 |
| Cleanup | PR close → `sidecar_cleanup.yaml`：Deployment/Service/HPA 依 `app.kubernetes.io/name={release}`；Ingress 自 ngweb-actions#91（2026-11-17 merged）起也依 label 掃（之前只按 name `{release}`、`{release}-icaas`，多出來的 Ingress 會孤兒）。`--ignore-not-found`，可重跑 |
| 閒置回收 | sidecar-terminator（idle 10 天，ngweb-actions#81）；Rancher 管理的叢集才搆得到 |
| 叢集 | NPE：qa01（預設）、npa01；alias 見 `ngweb-actions/configs/clusters.conf` |

## 4. 驗證

- **mf**：`curl -H 'x-npe-env: npe-pr-N' https://<tenant>/mf/<app>/build-info.json`（mf-client 是 `/mf/client/build-info-json`）看 `deploymentSuffix`。
- **ms**：沒有 build-info，只能比對帶/不帶 header 的 response 差異，或看 sidecar pod log。「不帶 header 也能用」**不能**證明 sidecar 在服務（NXDOMAIN 會靜默 fallback）。
- **K8s 真相**：`kubectl get deploy -n ngweb-v2 | grep -- '-npe-'`。`helm list -n ngweb-v2` 看不到 YAP 部署的 sidecar。

## 5. 通用坑

- **`ngweb_mf` 對不存在的 env build 回 401 不是 404**，`@mf_npe_fallback` 只接 404 → 回最終 401 或被 `error_page 401 =404` 換成 174 KB 靜態 404 頁。`/npe-ngssl-check` 只查靜態設定，要配一個 live curl。
- **chart 預設值會在 mainline path 上長出 sidecar Ingress**：sidecar values 沒覆寫的 ingress（例：webui2 `ingress.frame.pathPrefix` 預設 `/mf/frame`）會用 sidecar 名字搶 mainline 路徑。新增 Ingress 種類時，sidecar template 要明確關掉或改成帶 suffix 的 path。
- **共用 namespace 的 Helm ownership 衝突**：非 release-scoped 的資源（ServiceAccount、ExternalName Service 等固定名字的物件）sidecar overlay 必須關掉，否則跟 main release 搶 ownership（client-oppy 經驗）。
- **DNS label 長度**：header regex 上限 67 字，但 `<service>-<env>` 要當 Service 名（≤63、不可有 `_`/大寫/尾 `-`）。server 端自己拼 sidecar host 的程式要做 RFC 1123 驗證，否則靜默打 main。
- **zsh `curl ${h:+-H "$h"}`** 不 word-split → header 前多空白 → nginx `400`。用 array。
- **`GITHUB_TOKEN` 加的 label 不會觸發其他 workflow**（recursion guard）；label-driven 流程要用 PAT/App token 或 `workflow_dispatch`。

## 6. 權威文件

- Whole picture：https://netskope.atlassian.net/wiki/spaces/ENG/pages/7810187526
- How to traffic sidecar deployment (User)：https://netskope.atlassian.net/wiki/spaces/ENG/pages/7749108007
- ngweb-actions specs：`openspec/specs/service-cicd-sidecar-lifecycle`、`sidecar-label-based-cleanup`、`sidecar-suffix-resolution`、`sidecar-terminator`
