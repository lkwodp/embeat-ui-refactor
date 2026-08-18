# Embeat UI Web

基于 FastAPI + React 的 Embeat 音乐推荐界面（模块化重构版），1:1 复刻
[embeat-ui](https://github.com/lkwodp/embeat-ui) 的三页界面（搜索发现 / 歌单电台 /
设置），并补齐 oss 前端依赖的全部后端 API。前端提供搜索、按流派/每周发现浏览、
多曲电台、历史记录，并可将推荐结果保存到网易云或酷狗歌单。推荐逻辑调用
[Embeat ML 后端](https://github.com/gdstudio-org/Embeat)（需自行准备）和 Qdrant
向量数据库。

- 业务核心来自 embeat-ui，已**复制到本项目并重写为细模块**（`backend/embeat/`），
  不再依赖 oss 仓库。
- ML 后端 [gdstudio-org/Embeat](https://github.com/gdstudio-org/Embeat) 通过 git
  submodule 引入（`embeat/`，提供 Qdrant 向量检索与 `infer/Embeat.py`）。
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

## 前置要求与依赖

- [uv](https://docs.astral.sh/uv/)（Python >= 3.12, < 3.13）
- Node.js 18+
- 拉取 submodule：`git submodule update --init --recursive`
- Embeat ML 后端：包含 `infer/` 目录的仓库（提供 `EmbeatDatabase` 与 `qdrant_models`）
- Qdrant 向量数据库，含 `spotify_tracks` 集合
- （可选）网易云 / 酷狗兼容 API 服务，用于登录与歌单写入

## 配置

后端配置在 `backend/embeat/.env`（也可用同名环境变量覆盖，环境变量优先级最高）：

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

全部可配置项见 `backend/embeat/config.py` 的 `_ENV_KEYS`：

| 变量                 | 默认值                    | 说明                                                                                 |
| -------------------- | ------------------------- | ------------------------------------------------------------------------------------ |
| `EMBEAT_ROOT`      | `../Embeat`（自动探测） | Embeat ML 后端仓库路径（含 `infer/`）                                                |
| `QDRANT_URL`       | `http://127.0.0.1:6333` | Qdrant 地址（远程部署可改为服务器地址）                                               |
| `QDRANT_API_KEY`   | 空                        | Qdrant API Key（如启用）                                                             |
| `QDRANT_COLLECTION` | `spotify_tracks`        | 使用的集合名                                                                         |
| `QDRANT_TIMEOUT`   | `30`                    | Qdrant 请求超时（秒）                                                                |
| `NETEASE_API_URL`  | 空                        | 界面默认填写的网易云兼容 API 地址                                                     |
| `KUGOU_API_URL`    | 空                        | 界面默认填写的酷狗兼容 API 地址                                                       |
| `PROXY_URL`        | 空                        | 界面默认填写的 HTTP 代理（本机直连被拦截时使用）                                      |
| `MB_LOOKUP_PATH`   | 空                        | MusicBrainz 别名数据库（`mb_lookup.db`）路径；留空时自动使用 `data/mb_lookup.db`    |
| `UI_HOST`          | `0.0.0.0`               | 网页服务监听地址                                                                     |
| `UI_PORT`          | `8765`                  | 网页服务端口                                                                         |
| `INVITE_CODE`      | 空                        | 注册邀请码，留空允许开放注册                                                         |
| `AUTH_ENABLED`     | `true`                  | 是否启用账号登录/注册；`false` 时访问级别由 `PAIRING_CODE` 决定                    |
| `PAIRING_CODE`     | 空                        | `AUTH_ENABLED=false` 时的访问控制：留空为开放模式，设为固定码则为配对模式         |

另外，ML 检索参数（召回权重、流派/热度阈值、简体转繁体等）通过
`embeat/.env` 配置（复制自 `embeat/.env.example`），供 `infer/Embeat.py` 读取。

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

浏览器打开：

```text
http://127.0.0.1:8765
```

平台账号配置页面：

```text
http://127.0.0.1:8765/settings
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

| 前缀                                                                                                              | 说明                                |
| ----------------------------------------------------------------------------------------------------------------- | ----------------------------------- |
| `/api/health`                                                                                                   | 数据库就绪状态与曲目数              |
| `/api/search`                                                                                                   | 曲名/歌手搜索（写入历史）           |
| `/api/recommend` · `/api/recommend/multi` · `/api/recommend/artist`                                       | 单曲 / 多曲 / 歌手推荐              |
| `/api/discover/genres` · `/genres`(按流派) · `/weekly`                                                    | 流派列表 / 流派浏览 / 每周发现      |
| `/api/playlist/seeds`                                                                                           | 歌单种子（电台手递）                |
| `/api/config` · `/api/preferences`                                                                           | 平台默认地址 / 主题偏好（GET/POST） |
| `/api/auth/me` · `/api/auth/register` · `/api/auth/login` · `/api/auth/logout` · `/api/device/pair` | 认证与会话 Cookie                   |
| `/api/history` · `/api/export/history`                                                                       | 历史记录（GET/POST）/ 导出          |
| `/api/{netease,kugou}/status` · `/config` · `/playlists`                                                  | 平台状态 / 凭据 / 歌单              |
| `/api/{netease,kugou}/captcha/send` · `/captcha/login`                                                       | 验证码登录                          |
| `/api/export/start` · `/api/export/status`                                                                   | 歌单导出任务                        |

## 搜索策略

- 主页支持"歌曲""歌手""歌曲+歌手"三种查询方式。
- 曲名搜索会自动尝试简体和繁体，并先展示 Qdrant 中的候选版本和实际艺人名。
- 歌手推荐支持中英文艺人名；后端会先解析为 Qdrant 中的标准艺人和 `artist_idx`，
  然后基于该歌手曲目的整体声学特征生成推荐。
- "歌曲+歌手"会使用艺人别名缩小候选范围；唯一候选直接推荐，存在录音室、Live 或
  翻唱等多版本时由用户确认。
- 选择候选后使用 Spotify Track ID 精确执行推荐。
- Track2Vec 未开源时，歌单关联召回自动跳过，其余召回正常工作。

## 保存到网易云或酷狗歌单

推荐结果支持逐首勾选，然后点击"保存到歌单"，可选择"网易云""酷狗"或"两个都保存"。
双平台模式下两边分别匹配和写入，一边失败时仍保留另一边的成功结果。

网易云需要准备：

- 一个兼容 NeteaseCloudMusicApi 的服务地址；
- 如果本机直连被防火墙拦截，填写本机 HTTP 代理；
- 当前网易云登录 Cookie；
- 有权编辑的目标歌单，或者直接创建新歌单。

首次访问会显示注册/登录门禁。登录使用 PBKDF2-SHA256 密码哈希和 HttpOnly 会话
Cookie；可通过 `.env` 的 `INVITE_CODE` 开启邀请码注册。网易云 Cookie 和酷狗
Token 只提交到后端，使用 Fernet 加密后写入 `data/embeat.db`，密钥单独保存在
`data/secret.key`，前端和 `localStorage` 均不会保存或回显敏感值。建议仅在可信
LAN 使用，或通过 Tailscale/WireGuard 暴露服务。

设置 `AUTH_ENABLED=false` 可关闭账号登录/注册，此时访问级别由 `PAIRING_CODE`
决定：

- **开放模式**（`PAIRING_CODE` 留空）：无需任何认证，访客打开页面即可使用，
  适合公开公益部署。所有访客共享本地 `local` 用户的凭据与记录。
- **配对模式**（`PAIRING_CODE` 设为固定码）：浏览器首次访问时需输入配对码，
  成功后获得长期有效的 HttpOnly 设备 Cookie；未完成配对的访客无法读写平台凭据，
  配对码不随页面下发。

界面提供 9 种主题模式：跟随系统、录音室浅色、海风蓝调、林间唱片、石墨工作台、
日光放映室、深夜黑胶、莓果夜色和高对比。主题及自定义强调色色相会写入当前用户的
SQLite 偏好，同时保留浏览器本地缓存用于首屏无闪烁，并通过 `storage` 事件在同一
浏览器的多个标签页间同步。主题菜单内置 WCAG AA 核心文字对比度检查；`auto` 模式
会随系统深浅色实时切换。

匹配会尝试原始名称、简体名称和去除括号后缀的曲名，并对网易云搜索候选按曲名与
艺人相似度评分。导入窗口会显示逐首匹配和写入进度。

酷狗凭据与网易云凭据一样，按当前 Embeat 用户加密保存在 `data/embeat.db`。页面只
显示登录状态，不回显 Cookie、Token、userid、dfid 或 mid；凭据失效后需在页面重新
连接。

`/settings` 同时支持直接填写 Cookie 和手机号验证码登录。验证码由配置的网易云或
酷狗兼容 API 发送；登录成功后，后端会提取并校验 Cookie/Token，再使用 Fernet 加密
写入当前用户的数据库记录。验证码不会写入数据库，手机号会随平台凭据保存以便下次
使用。

酷狗匹配会尝试原名、简体名、艺人中英文别名和去除括号后缀的曲名。写入前会读取目标
歌单已有歌曲哈希，准确跳过重复歌曲。同时保存到两个平台时，网易云和酷狗分别显示
独立进度条，完成后分别列出新增、已有和匹配失败明细。

## 电台、筛选和历史

- 搜索结果可勾选多首歌曲，点击"用选中歌曲生成电台"。
- 网易云窗口可选择整张歌单作为电台来源；系统会在歌单中均匀抽取最多 30 首并映射
  为 Embeat 种子。
- 多种子推荐按各自得分、候选排名和种子覆盖数融合，并排除所有种子歌曲。
- 推荐结果可请求 20 或 50 条；搜索候选和推荐结果均可选择每页显示 5、10 或 20 条，
  切换候选页时已勾选的多曲种子不会丢失。
- 可按召回来源、流派、最低热度过滤，并按匹配度、热度或种子覆盖排序。
- 最近搜索、推荐、电台和导出记录按用户写入 SQLite，可在登录后的页面查看和导出；
  旧版本浏览器历史会在首次登录后自动迁移并清理。
- 后端启动时加载 `data/chinese_singers_extended.json`、
  `data/chinese_singers_generated.json` 与 MusicBrainz 别名库
  （`MB_LOOKUP_PATH`），合并为中英文艺人别名映射，用于歌手搜索、歌手推荐和网易云/
  酷狗匹配；JSON 条目优先级高于 MusicBrainz。

## 移动端与发现入口

- 屏幕宽度不超过 840px 时，推荐结果自动切换为卡片布局；卡片支持勾选、查看双语名称、
  热度、流派、来源以及继续推荐。
- 桌面端左侧操作栏固定在视口中并独立滚动；移动端恢复普通上下布局。
- "按流派找歌"根据 Qdrant 中的艺人流派索引和热度浏览歌曲。
- "每周新发现"按 ISO 周生成稳定轮换结果，并限制同艺人和同流派的集中度。数据库
  没有发行日期字段，因此它是每周轮换发现榜，不代表歌曲在本周发行。

## Qdrant 断线恢复

后端会识别 Qdrant 连接中断和超时，重建数据库客户端并自动重试一次当前请求。网页
也会持续检查服务状态，因此 Qdrant 重启完成后无需重启 UI 服务；普通的"歌曲不存在"
等业务错误不会触发重连。

## 数据备份

认证数据库和加密密钥位于 `data/embeat.db`、`data/secret.key`，两者必须一起备份，
且不要提交到 Git。`cryptography` 是必需依赖。

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

## 致谢

本项目感谢以下开源项目的支持：

- [gdstudio-org/Embeat](https://github.com/gdstudio-org/Embeat) — 原始 Embeat
  项目，本界面调用了其 ML 推荐逻辑与数据库结构。
- [NeteaseCloudMusicApiEnhanced/api-enhanced](https://github.com/NeteaseCloudMusicApiEnhanced/api-enhanced)
  — 网易云兼容 API 服务，用于登录与歌单写入。
- [MakcRe/KuGouMusicApi](https://github.com/MakcRe/KuGouMusicApi) — 酷狗兼容 API
  服务，用于登录与歌单写入。