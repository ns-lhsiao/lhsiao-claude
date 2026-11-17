# Sidecar 特例：webui2（含 AWS leg）

最後更新：2026-11-17。通則：[sidecar.md](sidecar.md)。渲染鏈深入版：[crane-webui2-render.md](crane-webui2-render.md)、[crane-frame-index-serving.md](crane-frame-index-serving.md)。

---

## 1. 為什麼 webui2 特殊

一般 mf 的入口（`remoteEntry.js`）是瀏覽器經過 ngssl 拿的，header 自然生效。webui2 有兩個入口：

| build | URL | 入口 | 誰去拿入口 |
|---|---|---|---|
| `dist` | `/mf/shell/*` | `remoteEntry.js`（Angular 嵌入，embedded） | 瀏覽器 → edge → header ✅ |
| `dist-frame` | `/mf/frame/*` | `index.html`（全頁 React shell，standalone） | `/ns` 時是 **server 端 curl**（Ns.php / ms-bootstrap）→ header 不會自動帶 ❌ |

核心規則：**誰提供第一個沒有 hash 的檔案，誰就決定跑哪個 build。** 之後的 chunk hash 全寫死在那份 HTML/JS 裡；`x-npe-env` 只改「去哪拿」，不改「拿哪個檔名」。sidecar 沒有 main 的 hash → 404 → fallback main → 200，**頁面看起來正常但跑的是 main**（最常見的誤判）。

## 2. 四種組合（2026-11-17 狀態）

|  | `/ns` 產生者 = webui PHP（非 cutover） | `/ns` 產生者 = ms-bootstrap（crane） |
|---|---|---|
| Angular shell（flag 關） | ① ✅ 瀏覽器自己抓 `/mf/shell/remoteEntry.js` | ③ ✅ 同左 |
| React shell（flag 開） | ② webui#19476 已 merge，**但還要 webui2#4282（open）** 否則白頁 | ④ ✅ ms-bootstrap#433 已 merge |

- 直接打 `/mf/frame/<route>`：不經 server 代理，兩種租戶都 ✅。
- ①③ 例外：`ns.globals.balkan_s3_cloudfront_url` 若是 CloudFront，請求不經 ngssl → sidecar 失效。
- ② 卡住的原因：server 拿到 sidecar HTML 沒用，瀏覽器接著要 `/mf/frame/assets/<sidecar hash>.js` 仍走 edge → qa01 `webui2-mf-frame` Ingress → **main** Service → 404（fallback main 也 404）→ 白頁。MP sidecar 必須有 `/mf/frame/<suffix>` Ingress。修正順序：ngweb-actions#91（cleanup 依 label 掃 Ingress，**已 merge**）→ webui2#4282（MP template 開 `ingress.frame.pathPrefix: /mf/frame/{{ SUFFIX }}` + `rewriteTarget: /mf/frame/$2`）。ingress-nginx regex 路徑優先順序還沒 live 驗證。

## 3. 誰去哪個 leg（ngssl 依 `$crane_tenant` 分流）

| 租戶 | `/mf/frame/*` | `/mf/shell/*`、`/ns` |
|---|---|---|
| crane=1（`/etc/nginx/crane_tenants.map`，如 cpcs-auth-3） | `$crane_mf_proxy_pass` = `aws_nlb` → **AWS leg** | `/ns` → aws_nlb → ms-bootstrap |
| crane=0 | `$ngweb_mf_pass` → **MP leg** | `/ns` → `$webui_pass` → Ns.php |

crane 的 `/mf/frame` block（`ngweb_mf_route_mappings.conf`）對所有租戶都生效，只是 map 把非 crane 導回 `ngweb_mf`。crane 租戶走 `conf.d/aws_crane/*.conf`，**不是** rtp 設定；`/npe-ngssl-check` 掃 `webui_proxy*.nginx.conf` 看不到它們。

## 4. MP leg

- Release `webui2-npe-<suffix>`，namespace `ngweb-v2`，qa01/npa01；pipeline `deployment/helm/yap/pipeline-sidecar`，app `webui2-sidecar`。
- Template `charts/webui2/stacks/sidecar-value-template.yaml`：
  - `ingress.pathPrefix: /mf/shell/{{ SUFFIX }}(/|$)(.*)` —— lib chart 的 pathPrefix helper 只對 `mf-*` 名稱補 capture group，webui2 不是 `mf-*`，所以 regex 要手寫，配 rewrite-target `/$2`。
  - `ingress.frame.pathPrefix: ""` —— **必須關**，否則 chart 預設 `/mf/frame` 會用 sidecar 名字在 mainline frame path 長 Ingress。#4282 會改成帶 suffix 版本。
  - `icaas.enabled: true`、`ingressClassName: icaas-nginx-int-ngweb`。
- 觸發：`cicd-pr.yaml` → `service_cicd.yaml`（`sidecar_enabled: true`）。`labeled` 事件也會觸發：balkan-pr-scope 在 rollout-page PR 上自動蓋 `ci:sidecar-approved:npe-pr-<N>`，不需人工 gate。

## 5. AWS leg（cpcs，eks-skopeit-dev）

**為什麼存在**：frame 原本只在 AWS 上（`ingressFrameEks.yaml`），MP sidecar 沒有 frame Ingress，所以 AWS leg 曾是 PR 上預覽 frame 改動的唯一地方。MP mainline 已自己服務 `/mf/frame`（webui2#3809），但在 #4282 落地前 MP sidecar 仍不行。

**實作**（webui2 `cicd-pr.yaml`，webui2#4119 2026-11-12 重新啟用）：
- **獨立 job，不經 ngweb-actions**：ngweb-actions#80（整合式 aws leg input）已 **closed / 放棄**。現行是 webui2 自己的 `publish_manifest_sidecar_aws` → `trigger_yap_sidecar_aws`。
- 沿用 `needs.cicd.outputs.tag`，不重 build docker；chart 版本 `${TAG}-aws`，上傳 `ngweb-release-helm/webui2/`。
- manifest：`ngweb-actions/.github/actions/build-and-publish-manifest@develop`，`yap-pipeline-config-dir: deployment/helm/yap-aws/pipeline-sidecar`、`manifest-template: manifest_template_sidecar_aws.mt.yml`、`force-trigger-yap: 'true'`；Spinnaker app `webui2-sidecar-aws`。
- suffix 從 PR 的 label 現讀（`gh pr view --json labels`，不信 dispatch 時的 event snapshot），規則跟 MP leg 的 `resolve_sidecar_suffix` 一致：`ci:sidecar-denied` + approval 並存 → fail；多個 approval → fail；release 必須符合 `^webui2-npe-[a-z0-9]([a-z0-9-]{0,8}[a-z0-9])?$`。**一個 label、一個 suffix、一個 header 同時開兩個 leg。**

**Template `charts/webui2/stacks/aws/sidecar-value-template.yaml`**（不能跟 MP 的合併）：
- `isAwsEnvironment: true` 是 chart 全域開關（lib chart 改 render ALB Ingress，不是 nginx/icaas），放進 MP template 會弄壞 MP 叢集。
- ALB `pathType: Prefix` 是**字面比對、不支援 regex、不做 rewrite** → `ingress.pathPrefix: /mf/shell/{{ SUFFIX }}`，env 段由 **pod nginx**（`deploy/nginx/default.conf`）剝掉。
- **兩條 rule 都要**：`pathPrefix: /mf/shell/<suffix>` + `ingress.aws.additionalPathPrefixes: [/mf/frame/<suffix>]`。frame 頁會拉 `/mf/shell/...` 的資產，少一條就混到 mainline。
- ALB group：`group.name: cpcs-qa01`、`load-balancer-name: ns-cpcs-nonprod-qa01-alb-use1`（加入 mainline 同一顆 ALB）。
- **Rule 順序**：ALB group 由 order 小到大、first match wins；mainline `/mf/shell` Prefix 也會吃到 env-prefixed path，所以 sidecar 必須**排在 mainline 前面（數字更小）**：sidecar shell `group.order: "5"`、frame `groupOrderOffset: 4` → 6；mainline shell 10 / frame 11。第一次部署前確認 group 內沒有別的 service 佔 5/6。**同時只能容納很少的 AWS sidecar**（order 7 是唯一預留）。

**Cleanup 缺口**：eks-skopeit-dev 不是 Rancher 管（`nsk cluster list` 看不到 cpcs），`sidecar_cleanup.yaml` 的 clusters.conf + `RANCHER_TOKEN` 搆不到 → **AWS sidecar 在 PR 關閉後殘留**（1 pod + 2 Ingress）。EKS 版 sidecar-terminator 在 ngweb-actions#88（open）。目前需手動清。

## 6. 驗證

```bash
H=https://cpcs-auth-3.qa.boomskope.com      # crane → AWS leg；換非 crane 租戶測 MP leg
E=npe-pr-4071
curl -s "$H/ns" | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1                         # main
curl -s -H "x-npe-env: $E" "$H/ns" | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1       # 應 ≠ main
curl -s -H "x-npe-env: $E" "$H/mf/frame/index.html" | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1  # sidecar 本身
curl -s -H "x-npe-env: $E" "$H/mf/frame/build-info.json"                                 # deploymentSuffix
```

DevTools 判讀：`/ns` document 裡直接有 `/mf/frame/assets/index-*.js` → ②④（hash 由 server 決定）；`/ns` 是 Angular、之後才載 `/mf/shell/remoteEntry.js` → ①③。**第一個沒 hash 的檔案對了，後面全對。**

## 7. 坑

- 「帶 header 頁面正常」不代表跑 sidecar —— 一定比對 `index-<hash>.js`。
- `/ns` 和 `/ns/.+` 不要混：後者是 post-auth API（`getStaticGlobals` 等，crane 走 `$mp_webui_proxy_pass` api-gateway），在那裡加 rewrite 會弄壞 API。
- 非 crane 路徑下 sidecar frame 資產其實可由 `/mf/shell/<env>/mf/frame/assets/<hash>.js` 拿到（實測 200），理論上可改寫 HTML 免 Ingress，但沒做瀏覽器端到端驗證，正解仍是 #4282。
- 本機 webui2 checkout 容易落後 origin/master 很多 commit，引用行號前先 `git fetch`。
