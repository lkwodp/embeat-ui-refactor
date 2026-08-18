# Embeat UI Web

基于 FastAPI + React 的 Embeat 音乐推荐界面（模块化重构版），1:1 复刻
[embeat-ui-oss](https://github.com/lkwodp/embeat-ui) 的三页界面（搜索发现 /
歌单电台 / 设置），并补齐 oss 前端依赖的全部后端 API。

- 业务核心来自 embeat-ui-oss，已**复制到本项目并重写为细模块**
  （`backend/embeat/`），不再依赖 oss 仓库。
- ML 后端 [gdstudio-org/Embeat](https://github.com/gdstudio-org/Embeat)
  通过 git submodule 引入（`embeat/`，提供 Qdrant 向量检索与 `infer/Embeat.py`）。
- 后端 FastAPI 提供全部 API 并托管构建后的 React 前端；前端 Vite + React +
  TypeScript。

## 目录结构

```text
embeat-ui-web/
├── embeat/              # git submodule：Embeat ML 后端（EmbeatDatabase / infer）
├── backend/
│   ├── embeat/          # 复制的业务核心，拆分为细模块
│   │   ├── config.py        # 运行时配置（env / .env / 默认值三级解析）
│   │   ├── service.py       # EmbeatService 业务入口（search / recommend / discover …）
│   │   ├── search.py        # 曲名/歌手模糊搜索
│   │   ├── recommendations.py # 单曲 / 多曲 / 歌手推荐
│   │   ├── discover.py      # 流派 / 每周发现 / 歌单种子（每周发现、genre 分布）
│   │   ├── platforms.py     # 平台凭据管理（netease / kugou）
│   │   ├── netease_client.py / kugou_client.py # 平台 API 客户端与歌单抓取
│   │   ├── export_manager.py # 歌单导出任务（导入/状态/结果）
│   │   ├── qdrant.py / aliases.py / text_utils.py / app_database.py
│   │   ├── data/           # 歌手别名 / MB 查找 / 元数据缓存
│   │   └── tests/          # 业务核心单测（15 项）
│   ├── app/
│   │   ├── main.py         # FastAPI 入口（挂载路由 + SPA 托管 + 异常映射）
│   │   ├── api/            # 路由：health / search / recommend / discover /
│   │   │                   #   config / auth / history / platforms
│   │   ├── api/deps.py     # 依赖注入（auth / service / 速率限制 / 会话 Cookie）
│   │   ├── core/           # EmbeatService 桥接
│   │   └── schemas/        # Pydantic 模型（与前端 TS 类型对齐）
│   └── tests/              # API 冒烟测试（4 项）
└── frontend/               # React (Vite + TS) 前端
    └── src/
        ├── main.tsx / App.tsx   # 入口 + Router + Provider 装配
        ├── theme/               # ThemeProvider（9 主题 × 强调色，持久化 + 偏好同步）
        ├── auth/                # AuthProvider / AuthGate（认证门 + 开放模式）
        ├── components/          # ThemePicker / ExportModal / common（Toast、状态徽章…）
        ├── pages/               # Home（搜索发现）/ Radio（歌单电台）/ Settings
        ├── api/client.ts        # 全量 API 客户端
        ├── styles/app.css       # oss 原版样式（1:1）
        └── types/               # TS 类型（与 Pydantic 模型对齐）
```

## 前置要求

- [uv](https://docs.astral.sh/uv/)（Python >= 3.12, < 3.13）
- Node.js 18+
- 拉取 submodule：`git submodule update --init --recursive`
- Qdrant 向量库（默认 `http://127.0.0.1:6333`，集合 `spotify_tracks`），
  可用 `embeat/.env`（复制自 `embeat/.env.example`）配置 `infer/Embeat.py`
  的检索参数，或用后端 `backend/embeat/.env` 配置服务运行参数

## 配置

后端配置在 `backend/embeat/.env`（也可用环境变量覆盖，环境变量优先级最高）：

```ini
QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=spotify_tracks
NETEASE_API_URL=https://…
KUGOU_API_URL=https://…
PROXY_URL=http://127.0.0.1:20808
AUTH_ENABLED=false        # true=需要注册/登录，false=开放模式
PAIRING_CODE=             # 设备配对码（非空时启用 /api/device/pair）
UI_HOST=0.0.0.0
UI_PORT=8765
```

全部可配置项见 `backend/embeat/config.py` 的 `_ENV_KEYS`。

## 开发

启动后端（默认 `http://127.0.0.1:8765`）：

```powershell
cd backend
uv run uvicorn app.main:app --reload --port 8765
```

启动前端（Vite dev server，`/api` 代理到 `127.0.0.1:8765`）：

```powershell
cd frontend
npm install
npm run dev
```

## 生产构建

```powershell
cd frontend
npm run build
cd ../backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8765
```

FastAPI 检测到 `frontend/dist` 存在时自动挂载 `/assets` 并提供 SPA 回退
（`/`、`/radio`、`/settings` 均返回 index.html），未构建时返回 404 提示。

## API 概览

| 前缀 | 说明 |
| --- | --- |
| `/api/health` | 数据库就绪状态与曲目数 |
| `/api/search` | 曲名/歌手搜索（写入历史） |
| `/api/recommend` · `/api/recommend/multi` · `/api/recommend/artist` | 单曲 / 多曲 / 歌手推荐 |
| `/api/discover/genres` · `/genres`(按流派) · `/weekly` | 流派列表 / 流派浏览 / 每周发现 |
| `/api/playlist/seeds` | 歌单种子（电台手递） |
| `/api/config` · `/api/preferences` | 平台默认地址 / 主题偏好（GET/POST） |
| `/api/auth/me` · `/api/auth/register` · `/api/auth/login` · `/api/auth/logout` · `/api/device/pair` | 认证与会话 Cookie |
| `/api/history` · `/api/export/history` | 历史记录（GET/POST）/ 导出 |
| `/api/{netease,kugou}/status` · `/config` · `/playlists` | 平台状态 / 凭据 / 歌单 |
| `/api/{netease,kugou}/captcha/send` · `/captcha/login` | 验证码登录 |
| `/api/export/start` · `/api/export/status` | 歌单导出任务 |

认证会话使用 `embeat_session`（30 天）与 `embeat_device`（365 天）两个
HttpOnly SameSite=Lax Cookie；`AUTH_ENABLED=false` 时 `/api/auth/me` 自动
创建 device cookie 并以 `open_access` 开放访问。

## 测试

```powershell
cd backend
uv run python -m pytest tests -q          # API 冒烟（4 项）
$env:EMBEAT_ROOT = "<repo>\embeat"        # 业务核心测试需要 ML 后端
uv run python -m pytest embeat/tests -q   # 业务核心（15 项）
```

## 更新 ML 后端

```powershell
git submodule update --remote embeat
```

> 注意：`embeat/.env` 是本地配置（复制自 `.env.example`），已被 submodule
> 的 `.gitignore` 排除，不会被提交。