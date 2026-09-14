# FinHub — 本地部署记录（离线/内网适配版）

本仓库在标准网络下用 `make config && make up` 即可启动。当前环境只有 `mirrors.tencent.com` 可达（ghcr.io、pypi.org、registry.npmjs.org、github.com、deb.debian.org、archive.ubuntu.com、nodejs.org 全部不通），因此新增了一层 **本地 override 文件**，官方 `docker-compose.yml` / `Dockerfile.dev` / `Dockerfile.sandbox` 保持零改动。

## 启动命令

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build -d
```

停止：

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml down
```

沙箱镜像（PTC 代码执行，可选）：

```bash
docker build -f Dockerfile.sandbox.local -t finhub-sandbox:latest .
```

## 访问地址

| 服务 | 地址 | 说明 |
| --- | --- | --- |
| 前端 | http://localhost:5173 | Vite dev server |
| 后端 API | http://localhost:8000 | 健康检查 `/health`，交互文档 `/docs` |
| PostgreSQL | 127.0.0.1:5432 | `postgres/postgres` |
| Redis | 127.0.0.1:6379 | 密码 `redis` |

## 本地化改动清单

### `docker-compose.local.yml`（新增）
- backend 构建切换到 `deploy/Dockerfile.dev.local`
- frontend 的 npm/pnpm registry 指向 `https://mirrors.tencent.com/npm/`

### `deploy/Dockerfile.dev.local`（新增，基于 `Dockerfile.dev`）
1. apt 源 → `mirrors.tencent.com/debian`（trixie），否则 curl / postgresql-client / tini 无法安装
2. `COPY --from=ghcr.io/astral-sh/uv` → `pip install uv`（ghcr.io 不可达）
3. `uv sync --frozen` → `uv export --frozen` 导出锁定版本 + `uv pip install` 走镜像源
   - 原因：`uv sync --frozen` 直接按 lock 里的 `files.pythonhosted.org` 绝对 URL 下载，index 覆盖对它不生效
   - 先 `uv pip install --no-deps -e .` 装 `finhub-core`，再装导出的依赖（因为 `finhub-cli` 依赖 `finhub-core`）
4. 浏览器安装（Playwright Chromium / Camoufox）改为 `ARG INSTALL_BROWSERS=false`，默认跳过
5. 追加 `VIRTUAL_ENV=/app/.venv`、`UV_NO_SYNC=1`，避免 `uv run` 启动时重新联网 sync

### `Dockerfile.sandbox.local`（新增，基于 `Dockerfile.sandbox`）
1. apt 源 → `mirrors.tencent.com/ubuntu`（必须走 http：ubuntu:24.04 镜像无 CA 证书，https 握手直接失败）
2. uv：`pip install uv` 替代 `astral.sh/install.sh`
3. Node.js：`mirrors.tencent.com/nodejs-release` 替代 `nodejs.org`
4. npm registry → 腾讯镜像；仅装 `docx`、`pptxgenjs`
5. **修复 CJK 字体**：上游把 matplotlibrc 写进 root 的 configdir，而容器以 `workspace` 用户运行，配置永不生效（中文标题全是豆腐块）。改为写入共享目录 `/opt/mplconfig` 并 `ENV MPLCONFIGDIR=/opt/mplconfig`，实测中文标题/轴标签渲染正常
6. **跳过**（源不可达，非核心链路）：GitHub CLI、polymarket-cli、Playwright 浏览器下载、`scrapling install`（Camoufox）、docker-ce

## 当前功能状态

- ✅ Web UI、API、PostgreSQL、Redis、LangGraph checkpointer 全部 healthy
- ✅ **LLM 已接通**：Agnes AI 网关（`https://apihub.agnes-ai.com/v1`），即 `hcn-gateway` 模型（`agnes-2.5-flash`）；在 `.env` 配 `HCN_BASE_URL` + `HCN_API_KEY`，前端默认模型即用
- ✅ **PTC 沙箱**：`SANDBOX_PROVIDER=docker` + `finhub-sandbox:latest`，实测沙箱内跑 Python、写文件成功（`123456*789 → result.txt`），matplotlib 画图链路正常
- ✅ **tiktoken 离线化**：`openaipublic.blob.core.windows.net` 不可达会炸掉整个 chat 链路；`.tiktoken_cache/` 里预置了从 HF 镜像词表精确重建的 `cl100k_base.tiktoken`（sha256 与官方完全一致 `223921b7…`），compose 已挂载并设 `TIKTOKEN_CACHE_DIR`
- ✅ **AUTH_USER_ID**：默认 `local-dev-user` 会让 research-loops 等 uuid 字段接口 500，已改为 UUID `00000000-0000-0000-0000-000000000001`
- ✅ Yahoo Finance 免密钥数据源可用
- ⚠️ 无 LLM API Key：Agent 对话不可用，需在 `.env` 填 `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` 等任一
- ⚠️ 沙箱用 Docker provider（`SANDBOX_PROVIDER=docker`），隔离性弱于 Daytona；需要 `finhub-sandbox:latest` 镜像
- ⚠️ `BYOK_ENCRYPTION_KEY` 仍是仓库默认值，仅本地开发可接受的用法
- ⚠️ 三级网页抓取（Camoufox stealth）与 LibreOffice 之外的高级导出链路：见上方跳过项

## Agnes AI 能力现场验证（key 属免费档）

| 能力 | 模型 | 结果 |
| --- | --- | --- |
| 文本对话 / Agent | agnes-2.5-flash | ✅ FinHub chat + PTC 全链路跑通 |
| 文生图 | agnes-image-2.5-flash | ✅ 1024×1024 PNG 生成成功 |
| 视频 | agnes-video-2.5-flash | ⚠️ 端点通（`/v1/video/generations`，需 `mode` 参数），免费额度触发 rate limit |
| `GET /v1/models` | — | ✅ 12 个模型（文本 2.5/3.0、图像 3 款、视频 3 款） |

## 端到端现场验证记录

| # | 场景 | 结果 |
| --- | --- | --- |
| 1 | flash 模式对话（「你是什么模型 + 1+1」） | ✅ 回答「FinHub Agent（Flash）… 1+1=2」，SSE 全事件流正常 |
| 2 | PTC 沙箱计算 + 写文件 | ✅ 沙箱内跑 Python，`result.txt` = `97406784`（123456×789） |
| 3 | PTC 沙箱画中文图表 | ✅ `work/chart_simulation/chart.png` 1484×734，中文标题/轴标签渲染正常，产生 `artifact` 事件 |
| 4 | 只读 API 冒烟（37 个端点） | ✅ 33 个 200；evals-report 404（未生成，预期）；research-loops 已修复 200 |
| 5 | news / skills / plugins / mcp / models | ✅ news 15KB、skills 16KB、models 18KB 真实数据 |
| 6 | 行情数据 | ❌ 本环境 Yahoo Finance 不可达；FMP 可达但需 key（401） |

## 安全提示

`.env` 已入 `.gitignore`（已验证），内含 Agnes key 与占位密钥，**不要提交**。`BYOK_ENCRYPTION_KEY` 当前是公开默认值，**不要**用于生产。生产请设 `HOST_MODE=platform` 并替换该密钥。
