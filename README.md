# Embeat UI Web

基于 **FastAPI + React** 的 Embeat 音乐推荐界面（模块化重构版），1:1 复刻 [embeat-ui](https://github.com/lkwodp/embeat-ui) 的三页界面（搜索发现 / 歌单电台 / 设置），并补齐 oss 前端依赖的全部后端 API。

前端提供搜索、按流派 / 每周发现浏览、多曲电台、历史记录，并可将推荐结果保存到网易云或酷狗歌单。推荐逻辑调用 [Embeat ML 后端](https://github.com/gdstudio-org/Embeat)（git submodule）和 Qdrant 向量数据库。

- 业务核心来自 embeat-ui，已复制到本项目并重写为细模块（`backend/embeat/`），不再依赖 oss 仓库。
- ML 后端 [gdstudio-org/Embeat](https://github.com/gdstudio-org/Embeat) 通过 git submodule 引入（`embeat/`，提供 Qdrant 向量检索与 `infer/Embeat.py`）。
- 后端 FastAPI 提供全部 API 并托管构建后的 React 前端；前端 Vite + React + TypeScript。

---

## 目录

- [一、从 GitHub 拉取项目](#一从-github-拉取项目)
- [二、环境准备](#二环境准备)
- [三、安装后端依赖](#三安装后端依赖)
- [四、配置 Qdrant 与 ML 后端](#四配置-qdrant-与-ml-后端)
- [五、配置环境变量](#五配置环境变量)
- [六、安装前端依赖并构建](#六安装前端依赖并构建)
- [七、启动服务](#七启动服务)
- [八、验证运行](#八验证运行)
- [常见问题（FAQ）](#常见问题faq)
- [项目结构与配置说明](#项目结构与配置说明)
- [API 概览](#api-概览)
- [功能说明](#功能说明)
- [测试](#测试)
- [更新 ML 后端](#更新-ml-后端)
- [数据备份](#数据备份)
- [开源协议与许可](#开源协议与许可)
- [致谢](#致谢)

---

## 一、从 GitHub 拉取项目

### 1. 安装 Git

确保已安装 Git，并可通过命令行访问：

```powershell
git --version
```

未安装请前往 [git-scm.com](https://git-scm.com/downloads) 下载安装（Windows 一路默认即可，勾选 "Git from the command line and also from 3rd-party software"）。

### 2. 克隆主仓库（含 submodule）

```powershell
git clone --recurse-submodules https://github.com/lkwodp/embeat-ui-refactor.git
cd embeat-ui-refactor
```

`--recurse-submodules` 会同时拉取 `embeat/` 子模块（gdstudio-org/Embeat ML 后端）。

如果已经用普通方式克隆了仓库，补拉子模块：

```powershell
cd embeat-ui-refactor
git submodule update --init --recursive
```

### 3. 验证子模块

```powershell
git submodule status
```

输出应类似 `4a727495dda097f846e06b784e39f44f64beca40 embeat (heads/main)`。如果看到 `-` 前缀（未初始化），重复执行第 2 步的 `git submodule update --init --recursive`。

---

## 二、环境准备

| 软件                            | 版本要求                        | 说明                                                |
| ------------------------------- | ------------------------------- | --------------------------------------------------- |
| Python                          | **>= 3.12 且 < 3.13**     | 由 uv 自动安装/管理（见下方），无需手动安装         |
| [uv](https://docs.astral.sh/uv/) | 最新稳定版                      | Python 依赖管理器，自动安装`backend/.venv`        |
| Node.js                         | **18+**（推荐 20/22 LTS） | 构建前端，需同时包含 npm                            |
| Git                             | 任意较新版本                    | 已在上一步使用                                      |
| Qdrant                          | 任意较新版本                    | 向量数据库，需含`spotify_tracks` 集合（见第四节） |

### Windows 安装 uv

```powershell
winget install --id=astral-sh.uv  # 或
# PowerShell 官方脚本：
# irm https://astral.sh/uv/install.ps1 | iex
```

安装后重新打开终端，验证：

```powershell
uv --version
```

> uv 会读取 `backend/.python-version`（内容为 `3.12`）自动下载匹配的 Python，无需单独安装 Python。

### 验证 Node.js / npm

```powershell
node --version
npm --version
```

---

## 三、安装后端依赖

在项目根目录执行（uv 会自动创建 `.venv` 并读取 `uv.lock` 精确还原依赖）：

```powershell
cd backend
uv sync
```

首次会下载 Python 3.12 并安装所有依赖，耗时较长属正常。完成后验证：

```powershell
uv run python --version   # 应输出 Python 3.12.x
```

> **注意**：`uv sync` 会忽略 `backend/.python-version` 之外的 Python 版本；如果系统已有其他 Python，建议只使用 `uv run` 统一入口，不要直接调用系统 `python`。

---

## 四、配置 Qdrant 与 ML 后端

> 完整的 Qdrant 部署与数据准备教程见 [docs/qdrant-deploy.md](docs/qdrant-deploy.md)。
> 本节只给出快速上手步骤。

推荐逻辑需要 Qdrant 向量数据库，并且集合中要有歌曲数据（含 `spotify_tracks` 向量集合）。

### 1. 启动 Qdrant

任选一种方式：

```powershell
# Docker（推荐）
docker run -d --name qdrant -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant

# 或 直接运行 qdrant 可执行文件（从 https://qdrant.tech/install 下载后）
# 在解压目录执行
.\qdrant.exe
```

验证（返回 `{"title":"qdrant","version":...}` 即正常）：

```powershell
curl.exe http://127.0.0.1:6333
```

### 2. 准备歌曲数据（spotify_tracks 集合）

集合数据由 [gdstudio-org/Embeat](https://github.com/gdstudio-org/Embeat) 项目提供（在其仓库中运行向量化/导入脚本，或导入其导出的数据快照）。**本仓库不包含歌曲数据，必须自行准备。**

导入完成后确认集合存在：

```powershell
curl.exe http://127.0.0.1:6333/collections/spotify_tracks
```

返回中的 `points_count` 应为非零值（当前演示库为 4500 万+ 条）。

### 3. 配置 ML 后端（embeat 子模块）

子模块 `embeat/` 自带 `infer/Embeat.py`，需要通过 env 告知其 Qdrant 地址与集合名：

```powershell
cd embeat
Copy-Item .env.example .env
```

用文本编辑器打开 `embeat/.env`，至少确认以下项与你的 Qdrant 一致：

```ini
EMBEAT_QDRANT_URL=http://127.0.0.1:6333
EMBEAT_COLLECTION_NAME=spotify_tracks
EMBEAT_ENABLE_NAME_SEARCH=1
```

> `embeat/.env` 已被 submodule 的 `.gitignore` 排除，不会污染 git。

---

## 五、配置环境变量

后端配置文件位于 `backend/embeat/.env`。**该文件默认不存在（被 gitignore），需要手动创建。**

```powershell
cd ../backend/embeat   # 从 embeat/ 回到 backend/embeat
# 若当前在 backend/ 下，则执行：cd embeat
```

创建 `.env` 并写入：

```ini
QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=spotify_tracks
AUTH_ENABLED=false
PAIRING_CODE=
```

### 环境变量说明

| 变量                  | 默认值                    | 说明                                                                             |
| --------------------- | ------------------------- | -------------------------------------------------------------------------------- |
| `EMBEAT_ROOT`       | 自动探测                  | Embeat ML 后端仓库路径（含`infer/`）。默认向上查找，一般无需配置               |
| `QDRANT_URL`        | `http://127.0.0.1:6333` | Qdrant 地址（远程部署可改为服务器地址）                                          |
| `QDRANT_API_KEY`    | 空                        | Qdrant API Key（如启用）                                                         |
| `QDRANT_COLLECTION` | `spotify_tracks`        | 使用的集合名                                                                     |
| `QDRANT_TIMEOUT`    | `30`                    | Qdrant 请求超时（秒）                                                            |
| `NETEASE_API_URL`   | 空                        | 界面默认填写的网易云兼容 API 地址                                                |
| `KUGOU_API_URL`     | 空                        | 界面默认填写的酷狗兼容 API 地址                                                  |
| `PROXY_URL`         | 空                        | 界面默认填写的 HTTP 代理（本机直连被拦截时使用）                                 |
| `MB_LOOKUP_PATH`    | 空                        | MusicBrainz 别名数据库（`mb_lookup.db`）路径；留空自动用 `data/mb_lookup.db` |
| `UI_HOST`           | `0.0.0.0`               | 网页服务监听地址（`0.0.0.0` 表示允许局域网访问）                               |
| `UI_PORT`           | `8765`                  | 网页服务端口                                                                     |
| `INVITE_CODE`       | 空                        | 注册邀请码，留空允许开放注册                                                     |
| `AUTH_ENABLED`      | `true`                  | 是否启用账号登录/注册；`false` 时访问级别由 `PAIRING_CODE` 决定              |
| `PAIRING_CODE`      | 空                        | `AUTH_ENABLED=false` 时的访问控制：留空为开放模式，设固定码则为配对模式        |

访问控制说明：

- **开放模式**（`AUTH_ENABLED=false` 且 `PAIRING_CODE` 留空）：无需认证，访客打开即可使用，适合公开部署。
- **配对模式**（`AUTH_ENABLED=false` 且 `PAIRING_CODE` 设为固定码）：首次访问需输入配对码，成功后获得长期设备 Cookie。

> 若通过局域网/公网访问，请设置 `UI_HOST=0.0.0.0`，并在 Windows 防火墙放行端口（见 FAQ）。

---

## 六、安装前端依赖并构建

### 1. 安装 npm 依赖

```powershell
cd frontend
npm install
```

### 2. 构建生产包

```powershell
npm run build
```

构建产物输出到 `frontend/dist/`。后端会自动检测该目录并托管（SPA 回退）。

> 跳过构建也可以只用 Vite 开发服务器（见第七节"开发模式"），但后端托管模式必须 `npm run build`。

---

## 七、启动服务

### 方式一：生产模式（后端托管前端）

```powershell
cd backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8765
```

浏览器打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)（局域网设备访问 `http://<主机IP>:8765`）。

### 方式二：开发模式（Vite dev server + 后端 API）

终端 1 —— 后端：

```powershell
cd backend
uv run uvicorn app.main:app --reload --port 8765
```

终端 2 —— 前端（Vite 监听 5173，`/api` 代理到 `127.0.0.1:8765`）：

```powershell
cd frontend
npm run dev
```

浏览器打开 [http://127.0.0.1:5173](http://127.0.0.1:5173)。

---

## 八、验证运行

### 1. 健康检查

```powershell
curl.exe http://127.0.0.1:8765/api/health
```

期望返回 `ready: true` 及歌曲总数：

```json
{"ready": true, "points": 45059660, ...}
```

### 2. 页面

| 页面         | 地址                               | 说明              |
| ------------ | ---------------------------------- | ----------------- |
| 搜索发现     | `http://127.0.0.1:8765`          | 主页              |
| 歌单电台     | `http://127.0.0.1:8765/radio`    | 平台歌单生成电台  |
| 平台账号配置 | `http://127.0.0.1:8765/settings` | 网易云 / 酷狗凭据 |

### 3. 常见验证请求

```powershell
# 搜索（URL 编码中文）
curl.exe "http://127.0.0.1:8765/api/search?name=%E5%91%A8%E6%9D%B0%E5%80%AB&limit=5"

# 单曲推荐（PowerShell 语法）
curl.exe -X POST http://127.0.0.1:8765/api/recommend `
  -H "Content-Type: application/json" `
  -d '{"track_id": "0T5lRHVhPRX2nlZZBlvwTW", "limit": 20}'

# 流派列表
curl.exe "http://127.0.0.1:8765/api/discover/genres?limit=20"
```

---

## 常见问题（FAQ）

### Q1：`uv` 未找到 / `uv sync` 失败

- 确认 uv 已安装且 `uv --version` 可用（见第二节）。
- 若网络拉取慢，可设置镜像：
  ```powershell
  $env:UV_DEFAULT_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"
  ```

### Q2：`curl.exe` 请求失败 / 页面显示"数据库离线"

- 确认 Qdrant 已启动：`curl.exe http://127.0.0.1:6333`。
- 确认 `backend/embeat/.env` 中 `QDRANT_URL` / `QDRANT_COLLECTION` 与 Qdrant 一致。
- 页面服务每 5 秒轮询一次 `/api/health`，Qdrant 恢复后无需重启 UI 服务（自动重连）。

### Q3：局域网设备无法访问

- 后端需以 `--host 0.0.0.0` 启动，且 `backend/embeat/.env` 的 `UI_HOST=0.0.0.0`。
- 需要放行端口（管理员 PowerShell）：
  ```powershell
  netsh advfirewall firewall add rule name="Embeat Web 8765" dir=in action=allow protocol=TCP localport=8765 profile=private
  ```

### Q4：`git submodule status` 显示异常

- 重新初始化：`git submodule update --init --recursive`。
- 更新到远端最新：`git submodule update --remote embeat`。

### Q5：搜索无结果 / 推荐为空

- 确认 `spotify_tracks` 集合非空且字段与 ML 后端一致。
- 歌曲中文名会自动尝试简繁转换；试试点歌手搜索或直接粘贴 Spotify Track ID。

### Q6：Node 版本过低构建报错

- 升级到 Node 18+（推荐 20/22 LTS），或使用 `nvm`（Windows 用 `nvm-windows`）安装指定版本。

---

## 项目结构与配置说明

```text
embeat-ui-web/
├── embeat/              # git submodule：Embeat ML 后端（EmbeatDatabase / infer）
│   └── .env.example     # 复制为 .env 配置 ML 参数
├── backend/
│   ├── .venv/           # uv 创建的 Python 虚拟环境
│   ├── .python-version  # Python 3.12
│   ├── pyproject.toml   # 后端依赖声明
│   ├── uv.lock          # 锁定依赖版本
│   ├── embeat/          # 复制的业务核心，拆分为细模块
│   │   ├── config.py        # 运行时配置（env / .env / 默认值三级解析）
│   │   ├── service.py       # EmbeatService 业务入口（search / recommend / discover …）
│   │   ├── search.py        # 曲名/歌手模糊搜索
│   │   ├── recommendations.py # 单曲 / 多曲 / 歌手推荐
│   │   ├── discover.py      # 流派 / 每周发现 / 歌单种子
│   │   ├── platforms.py     # 平台凭据管理（netease / kugou）
│   │   ├── netease_client.py / kugou_client.py # 平台 API 客户端与歌单抓取
│   │   ├── export_manager.py # 歌单导出任务（导入/状态/结果）
│   │   ├── qdrant.py / aliases.py / text_utils.py / app_database.py
│   │   ├── data/           # 歌手别名 / MB 查找 / 元数据缓存
│   │   ├── .env            # UI 运行时配置（gitignore，手动创建）
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
    ├── package.json        # npm 依赖与脚本
    ├── vite.config.ts      # dev 代理：/api → 127.0.0.1:8765
    ├── public/             # 静态资源（genres-zh.json 等）
    ├── dist/               # npm run build 产物（gitignore，后端托管）
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

另外，ML 检索参数（召回权重、流派/热度阈值、简繁转换等）通过 `embeat/.env` 配置（复制自 `embeat/.env.example`），供 `infer/Embeat.py` 读取。

---

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

---

## 功能说明

### 搜索策略

- 主页支持"歌曲""歌手""歌曲+歌手"三种查询方式。
- 曲名搜索会自动尝试简体和繁体，并先展示 Qdrant 中的候选版本和实际艺人名。
- 歌手推荐支持中英文艺人名；后端会先解析为 Qdrant 中的标准艺人和 `artist_idx`，然后基于该歌手曲目的整体声学特征生成推荐。
- "歌曲+歌手"会使用艺人别名缩小候选范围；唯一候选直接推荐，存在录音室、Live 或翻唱等多版本时由用户确认。
- 选择候选后使用 Spotify Track ID 精确执行推荐。
- "歌曲+歌手"模式下若歌曲不在 Qdrant（如新歌），自动回退为歌手推荐并提示。
- Track2Vec 未开源时，歌单关联召回自动跳过，其余召回正常工作。

### 保存到网易云或酷狗歌单

推荐结果支持逐首勾选，然后点击"保存到歌单"，可选择"网易云""酷狗"或"两个都保存"。双平台模式下两边分别匹配和写入，一边失败时仍保留另一边的成功结果。

网易云需要准备：兼容 NeteaseCloudMusicApi 的服务地址、本机 HTTP 代理（如被拦截）、登录 Cookie、有权编辑的目标歌单（或新建）。

登录使用 PBKDF2-SHA256 密码哈希和 HttpOnly 会话 Cookie；可通过 `.env` 的 `INVITE_CODE` 开启邀请码注册。网易云 Cookie 和酷狗 Token 只提交到后端，使用 Fernet 加密后写入 `data/embeat.db`，密钥单独保存在 `data/secret.key`，前端和 `localStorage` 均不会保存或回显敏感值。建议仅在可信 LAN 使用，或通过 Tailscale / WireGuard 暴露服务。

酷狗凭据与网易云一样按用户加密保存在 `data/embeat.db`。页面只显示登录状态，不回显 Cookie、Token、userid、dfid 或 mid。`/settings` 支持直接填写 Cookie 和手机号验证码登录；验证码由配置的兼容 API 发送，登录成功后后端提取并校验 Cookie/Token，加密写入数据库。验证码不写入数据库，手机号随平台凭据保存以便下次使用。

酷狗匹配会尝试原名、简体名、艺人中英文别名和去除括号后缀的曲名。写入前读取目标歌单已有歌曲哈希，准确跳过重复歌曲。同时保存到两个平台时，网易云和酷狗分别显示独立进度条，完成后分别列出新增、已有和匹配失败明细。

### 主题

界面提供 9 种主题模式：跟随系统、录音室浅色、海风蓝调、林间唱片、石墨工作台、日光放映室、深夜黑胶、莓果夜色和高对比。主题及自定义强调色色相写入当前用户的 SQLite 偏好，同时保留浏览器本地缓存用于首屏无闪烁，并通过 `storage` 事件在同一浏览器多标签页间同步。主题菜单内置 WCAG AA 核心文字对比度检查；`auto` 模式随系统深浅色实时切换。

### 电台、筛选和历史

- 搜索结果可勾选多首歌曲，点击"用选中歌曲生成电台"。
- 网易云窗口可选择整张歌单作为电台来源；系统在歌单中均匀抽取最多 30 首并映射为 Embeat 种子。
- 多种子推荐按各自得分、候选排名和种子覆盖数融合，并排除所有种子歌曲。
- 推荐结果可请求 10 / 20 / 30 / 50 / 100 条；搜索候选和推荐结果可选择每页显示 5、10 或 20 条，切换候选页时已勾选的多曲种子不会丢失。
- 可按召回来源、流派、最低热度过滤，并按匹配度、热度或种子覆盖排序。
- 最近搜索、推荐、电台和导出记录按用户写入 SQLite，可在页面查看和导出 JSON。
- 后端启动时加载 `data/chinese_singers_extended.json`、`data/chinese_singers_generated.json` 与 MusicBrainz 别名库（`MB_LOOKUP_PATH`），合并为中英文艺人别名映射，用于歌手搜索、歌手推荐和平台匹配；JSON 条目优先级高于 MusicBrainz。
- "按流派找歌"根据 Qdrant 中的艺人流派索引和热度浏览歌曲；下拉框流派名支持中文标注（配置在 `frontend/public/genres-zh.json`，编辑后刷新即生效）。
- "每周新发现"按 ISO 周生成稳定轮换结果，并限制同艺人和同流派的集中度（代表每周轮换发现榜，而非歌曲在本周发行）。

### 移动端与发现入口

- 屏幕宽度不超过 840px 时，推荐结果自动切换为卡片布局；卡片支持勾选、查看双语名称、热度、流派、来源以及继续推荐。
- 桌面端左侧操作栏固定在视口中并独立滚动；移动端恢复普通上下布局。
- 主页"最近记录""平台账号配置""导出历史 JSON"三个入口在移动端同样显示。

### Qdrant 断线恢复

后端会识别 Qdrant 连接中断和超时，重建数据库客户端并自动重试一次当前请求。网页持续检查服务状态，因此 Qdrant 重启完成后无需重启 UI 服务；普通的"歌曲不存在"等业务错误不会触发重连。

---

## 测试

```powershell
cd backend
uv run python -m pytest tests -q          # API 冒烟（4 项）

# 业务核心测试需要 ML 后端（默认自动探测，或显式指定）
$env:EMBEAT_ROOT = "<仓库根目录>\embeat"
uv run python -m pytest embeat/tests -q   # 业务核心（15 项）
```

---

## 更新 ML 后端

```powershell
git submodule update --remote embeat
```

> 注意：`embeat/.env` 是本地配置（复制自 `.env.example`），已被 submodule 的 `.gitignore` 排除，不会被提交。

---

## 数据备份

认证数据库和加密密钥位于 `backend/embeat/data/embeat.db`、`backend/embeat/data/secret.key`，两者必须一起备份，且不要提交到 Git。`cryptography` 是必需依赖。

Qdrant 向量数据的备份方式（快照 / 存储目录）见 [docs/qdrant-deploy.md](docs/qdrant-deploy.md) 第 9 节。

---

## 开源协议与许可

### 本项目随附组件

下表为本项目随附（或依赖其运行）的组件及其许可条款，须遵守：

| 项目 / 组件 | 范围 | 协议 |
| ----------- | ---- | ---- |
| [gdstudio-org/Embeat](https://github.com/gdstudio-org/Embeat) | 代码、模型权重 | MIT |
| [gdstudio-org/Embeat](https://github.com/gdstudio-org/Embeat) | 数据集、数据库（含 `spotify_tracks` Qdrant 向量数据） | **CC-BY-NC 4.0** |

> **重要**：Embeat 的**数据集与数据库**采用 [CC-BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/deed.zh-hans)（署名-非商业性使用），仅限**非商业用途**；分发时须保留署名，且不得用于商业目的。本项目本身不产生新的专有数据，随项目分发的数据库均来自上述开源来源。

### 可选外部服务

本项目的歌单写入功能**可选**接入网易云 / 酷狗 API 服务（对应 `api-enhanced`、`KuGouMusicApi`）。它们属于部署时的第三方服务，**不随本项目分发**，具体部署方式由使用者自行选择（也可替换为其他 API）。如使用上述实现，请自行遵守其各自许可：

| 服务 | 协议 |
| ---- | ---- |
| [NeteaseCloudMusicApiEnhanced/api-enhanced](https://github.com/NeteaseCloudMusicApiEnhanced/api-enhanced) | MIT |
| [MakcRe/KuGouMusicApi](https://github.com/MakcRe/KuGouMusicApi) | MIT |

---

## 致谢

本项目感谢以下开源项目的支持：

- [gdstudio-org/Embeat](https://github.com/gdstudio-org/Embeat) — 原始 Embeat 项目，本界面调用了其 ML 推荐逻辑与数据库结构。
- [NeteaseCloudMusicApiEnhanced/api-enhanced](https://github.com/NeteaseCloudMusicApiEnhanced/api-enhanced) — 网易云兼容 API 服务，用于登录与歌单写入。
- [MakcRe/KuGouMusicApi](https://github.com/MakcRe/KuGouMusicApi) — 酷狗兼容 API 服务，用于登录与歌单写入。
