# Embeat UI Web

基于 FastAPI + React 的 Embeat 音乐推荐界面（模块化重构版）。

业务核心来自 [embeat-ui-oss](https://github.com/lkwodp/embeat-ui)，已**复制到
本项目并重写**（`backend/embeat/`），不再依赖 submodule；ML 后端
[gdstudio-org/Embeat](https://github.com/gdstudio-org/Embeat) 通过 git
submodule 引入。

## 目录结构

```text
embeat-ui-web/
├── embeat/             # git submodule：Embeat ML 后端（EmbeatDatabase / infer）
├── backend/
│   ├── embeat/         # 复制的业务核心（config / service / artist_aliases / kugou_client ...）
│   ├── app/
│   │   ├── main.py     # FastAPI 入口
│   │   ├── api/        # 路由（health / search / recommend）
│   │   ├── core/       # EmbeatService 桥接
│   │   └── schemas/    # Pydantic 模型
│   └── tests/
├── frontend/           # React (Vite + TS) 组件化前端
│   └── src/
│       ├── api/        # API 客户端
│       ├── components/ # 组件（SearchForm / TrackList / RecommendationView）
│       ├── pages/      # 页面
│       └── types/      # TS 类型（与 Pydantic 模型对齐）
└── README.md
```

## 前置要求

- [uv](https://docs.astral.sh/uv/)
- Node.js 18+
- 拉取 submodule：`git submodule update --init --recursive`
- Embeat ML 后端由 `embeat/` submodule 提供；默认自动探测，也可用环境变量
  `EMBEAT_ROOT` 覆盖

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

FastAPI 会自动挂载 `frontend/dist`（若已构建）并提供 SPA 回退。

## 测试

```powershell
cd backend
uv run pytest -q
```

## 更新 ML 后端

```powershell
git submodule update --remote embeat
```