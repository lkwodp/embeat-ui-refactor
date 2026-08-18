# Qdrant 向量数据库部署与数据准备

> 本文档用于部署 Qdrant 向量数据库，并为 Embeat 准备 `spotify_tracks` 集合数据。
> 参考 [Qdrant 官方文档](https://qdrant.org.cn/documentation/)。

---

## 1. 环境要求

| 项目           | 要求                                                 |
| -------------- | ---------------------------------------------------- |
| 系统           | Windows 10/11 x64、Linux x64、macOS（单机部署）      |
| 磁盘空间       | **至少 40 GB 空闲**（Full 版解压后约 37.4 GB） |
| 内存           | 建议 16 GB 以上（加载 4500 万条向量时内存占用较高）  |
| 端口           | `6333`（REST API / Web UI）、`6334`（gRPC）      |
| Docker（可选） | 使用 Docker 方式部署时需要                           |

> 官方默认要求本机可运行 Docker，或直接下载 [Qdrant 二进制可执行文件](https://qdrant.tech/install/)。以下文档同时给出两种方式。

---

## 2. 获取数据库数据（夸克网盘）

> **数据来源说明**：本数据由**原作者开源**，最初通过**百度网盘**分享（见 `embeat/README_zh.md` 更新记录）：
>
> > **2026-07-02**：开源 Qdrant 数据库（提取码：0616）
> > `https://pan.baidu.com/share/init?surl=CWFzgM75Z4YjP1tZnGCZKg&pwd=0616`
>
> 本文档提供的夸克网盘链接是**从百度网盘原链接转存到自己夸克网盘后**的转发分享，数据内容一致。

Embeat 的 `spotify_tracks` 集合数据库提供 Lite 与 Full 两个版本：

| 版本 | 压缩包大小 | 解压后大小 | 说明                      |
| ---- | ---------- | ---------- | ------------------------- |
| Lite | 约 7.2 GB  | 约 20.1 GB | 数据量较小的快速体验版    |
| Full | 约 16.6 GB | 约 37.4 GB | 完整数据（4500 万条记录） |

获取方式（夸克网盘，本人转存分享）：

- 用夸克网盘 APP 打开分享链接：
- 链接：`https://pan.quark.cn/s/b79065151362`
- 口令：`/~2e893aHH8u~:/`

下载后得到一个压缩包（如 `embeat_qdrant_database.7z` ），解压得到 Qdrant 数据目录。

---

## 3. 安装 Qdrant

### 方式一：Windows 二进制（本仓库推荐）

1. 从 [Qdrant 官方下载页](https://qdrant.tech/install/) 下载 Windows x86_64 版本。
2. 解压到一个目录，例如：

   ```text
   G:\download\NDM\Compressed\qdrant-x86_64-pc-windows-msvc\
   ```

   该目录下应有 `qdrant.exe`。

### 方式二：Docker

```powershell
docker pull qdrant/qdrant
docker run -p 6333:6333 -p 6334:6334 `
  -v "$(pwd)/qdrant_storage:/qdrant/storage" `
  qdrant/qdrant
```

---

## 4. 解压数据库到 Qdrant 数据目录

### 重要：目录结构要求

**不要再嵌套一层同名目录**。将压缩包解压后，正确的目录结构应当是：

```text
embeat_qdrant_db
├── aliases
├── collections
│   └── spotify_tracks
└── raft_state.json
```

> 检查方法：解压后如果看到 `embeat_qdrant_db\embeat_qdrant_db\collections\...`（两层同名），说明多嵌套了一层，需要把内层目录移出来。

### 推荐放置位置

放到 Qdrant 可执行文件所在目录，例如：

```text
G:\download\NDM\Compressed\qdrant-x86_64-pc-windows-msvc\
├── qdrant.exe
└── embeat_qdrant_db\
    ├── aliases
    ├── collections\
    │   └── spotify_tracks
    └── raft_state.json
```

> 也可以放在任意位置，只要启动时用 `QDRANT__STORAGE__STORAGE_PATH` 指向它即可（见第 5 节）。

---

## 5. 启动 Qdrant

### Windows 二进制启动

```powershell
cd G:\download\NDM\Compressed\qdrant-x86_64-pc-windows-msvc

# 指定数据库存储目录（路径改成你的实际位置）
$env:QDRANT__STORAGE__STORAGE_PATH = "G:\download\NDM\Compressed\qdrant-x86_64-pc-windows-msvc\embeat_qdrant_db"

.\qdrant.exe
```

### 环境变量说明

`QDRANT__STORAGE__STORAGE_PATH` 对应 Qdrant 配置中的 `storage.storage_path`（每级配置用双下划线分隔），即数据存储根目录。指向 `embeat_qdrant_db` 后，Qdrant 会加载其中的 `spotify_tracks` 集合。

如需长期固定路径，也可以在 qdrant 的 `config/config.yaml` 中设置：

```yaml
storage:
  storage_path: G:\download\NDM\Compressed\qdrant-x86_64-pc-windows-msvc\embeat_qdrant_db
```

### 验证启动成功

启动后访问：

```
http://127.0.0.1:6333/collections/spotify_tracks
```

能返回集合信息（包含 `points_count` 等字段）即表示数据库加载成功。

加载成功时的返回示例（浏览器访问 `http://127.0.0.1:6333/collections/spotify_tracks`）：

```json
{
  "result": {
    "status": "green",
    "optimizer_status": "ok",
    "indexed_vectors_count": 45059660,
    "points_count": 45059660,
    "segments_count": 8,
    "config": {
      "params": {
        "vectors": {
          "size": 64,
          "distance": "Cosine",
          "datatype": "uint8"
        },
        "shard_number": 1,
        "replication_factor": 1,
        "write_consistency_factor": 1,
        "on_disk_payload": true
      },
      "hnsw_config": {
        "m": 8,
        "ef_construct": 200,
        "full_scan_threshold": 10000,
        "max_indexing_threads": 0,
        "on_disk": false
      },
      "optimizer_config": {
        "deleted_threshold": 0.2,
        "vacuum_min_vector_number": 1000,
        "default_segment_number": 0,
        "max_segment_size": null,
        "memmap_threshold": null,
        "indexing_threshold": 1,
        "flush_interval_sec": 5,
        "max_optimization_threads": null,
        "prevent_unoptimized": null
      },
      "wal_config": {
        "wal_capacity_mb": 32,
        "wal_segments_ahead": 0,
        "wal_retain_closed": 1
      },
      "quantization_config": null
    },
    "payload_schema": {
      "artist_idx": { "data_type": "integer", "points": 45059660 },
      "popularity": { "data_type": "float", "points": 45059660 },
      "artist_genre_idx": { "data_type": "integer", "points": 45059660 },
      "track_name": {
        "data_type": "text",
        "params": { "type": "text", "tokenizer": "word", "lowercase": true, "on_disk": true },
        "points": 45055777
      },
      "artist_name": {
        "data_type": "text",
        "params": { "type": "text", "tokenizer": "word", "lowercase": true, "on_disk": true },
        "points": 45057631
      }
    },
    "update_queue": { "length": 0 }
  },
  "status": "ok",
  "time": 0.0059689
}
```

> 关键字段解读：`status: "green"` 表示集合健康；`points_count: 45059660` 表示共 4506 万条曲目；`vectors` 为 64 维、Cosine 距离、`uint8` 量化类型；`payload_schema` 列出了可检索的负载字段（艺人索引 `artist_idx`、热度 `popularity`、流派索引 `artist_genre_idx`、曲名 `track_name`、艺人名 `artist_name`）。

首次加载 4500 万条记录可能需要**几分钟**，期间 Qdrant 会重建内存索引，属正常现象。

Web UI（Dashboard）：`http://127.0.0.1:6333/dashboard`

---

## 6. 集合配置说明

从网盘导入的 `spotify_tracks` 集合已包含完整配置，无需手动创建。集合实际参数如下：

| 参数             | 值                                        |
| ---------------- | ----------------------------------------- |
| 集合名           | `spotify_tracks`                        |
| 向量维度         | 64                                        |
| 距离度量         | Cosine                                    |
| 向量数据类型     | `uint8`（量化存储）                     |
| 分片数           | 1（`shard_number: 1`）                  |
| 副本因子         | 1（`replication_factor: 1`）            |
| 负载存储         | `on_disk_payload: true`（负载存磁盘）   |
| HNSW 参数        | `m: 8`、`ef_construct: 200`、内存索引   |
| 曲目总数         | 45059660（约 4506 万）                  |
| 负载字段         | `artist_idx`、`popularity`、`artist_genre_idx`、`track_name`、`artist_name` |

> 若需要从零构建集合（例如使用 `embeat/infer/hf_to_qdrant.py` 自行灌入数据），参考官方 [集合管理](https://qdrant.org.cn/documentation/manage-data/collections/) 文档。网盘数据已就绪，通常无需重建。

---

## 7. 与 Embeat UI 连接配置

Qdrant 启动后，需要在项目里配置两处连接：

### backend/embeat/.env

```ini
QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=spotify_tracks
```

### embeat/.env（子模块，ML 后端）

```ini
EMBEAT_QDRANT_URL=http://127.0.0.1:6333
EMBEAT_COLLECTION_NAME=spotify_tracks
```

> 远程部署时，将 `QDRANT_URL` 改为 Qdrant 服务器地址；如启用 API Key，还需设置 `QDRANT_API_KEY`。

---

## 8. 常见问题

### 端口被占用

- 关闭占用 `6333`/`6334` 的进程，或换端口启动 Qdrant 并在 `.env` 同步修改。
- Windows 查看占用：`Get-NetTCPConnection -LocalPort 6333`

### 集合返回 404 / 找不到 spotify_tracks

- 确认 `QDRANT__STORAGE__STORAGE_PATH` 指向的目录确实含 `collections/spotify_tracks`。
- 确认解压没有多嵌套一层同名目录（见第 4 节）。

### 首次加载很慢 / 页面显示"数据库初始化中"

- 4500 万条记录的首次加载需要几分钟，等待 Qdrant 完成即可。
- Embeat UI 后端有断线自动重连，Qdrant 就绪后无需重启 UI 服务。

### 启动报错缺少存储路径

- 检查环境变量名是否为 `QDRANT__STORAGE__STORAGE_PATH`（双下划线分隔层级）。
- 或在 `config/config.yaml` 中设置 `storage.storage_path`。

---

## 9. 备份与恢复

> 官方推荐用**快照（snapshot）**备份/恢复集合。参考 [官方快照教程](https://qdrant.org.cn/documentation/tutorials-operations/create-snapshot/)。

### 方式一：快照（推荐，用于迁移/备份）

在 Qdrant 运行中创建集合快照：

```powershell
# 请求创建快照
curl.exe -X POST "http://127.0.0.1:6333/collections/spotify_tracks/snapshots"

# 列出快照（返回快照文件名与大小）
curl.exe "http://127.0.0.1:6333/collections/spotify_tracks/snapshots"
```

快照文件生成在 Qdrant 的 `snapshots` 子目录中。恢复到一个新集合：

```powershell
curl.exe -X POST "http://127.0.0.1:6333/collections/spotify_tracks_restore/snapshots/upload?priority=snapshot" `
  -H "Content-Type: multipart/form-data" `
  -F "snapshot=@<快照文件路径>.snapshot"
```

### 方式二：直接备份存储目录（适合本项目的离线分发场景）

本项目的网盘数据库本质上就是 Qdrant **存储目录的打包**。备份时：

1. **先停止 Qdrant**（避免写入不一致）。
2. 直接复制整个 `embeat_qdrant_db` 目录（含 `aliases/`、`collections/`、`raft_state.json`）。
3. 恢复时把备份目录放回原位置（或改 `QDRANT__STORAGE__STORAGE_PATH` 指向它）再启动。

> 网络盘数据库的分发方式即属此类：压缩 = 备份，解压 + 指向路径 = 恢复。

---

## 10. 官方文档参考

- 快速入门：[https://qdrant.org.cn/documentation/quickstart/](https://qdrant.org.cn/documentation/quickstart/)
- 安装指南：[https://qdrant.org.cn/documentation/installation/](https://qdrant.org.cn/documentation/installation/)
- 集合管理：[https://qdrant.org.cn/documentation/manage-data/collections/](https://qdrant.org.cn/documentation/manage-data/collections/)
- 快照备份/恢复：[https://qdrant.org.cn/documentation/tutorials-operations/create-snapshot/](https://qdrant.org.cn/documentation/tutorials-operations/create-snapshot/)
- 存储与索引：[https://qdrant.org.cn/documentation/manage-data/storage/](https://qdrant.org.cn/documentation/manage-data/storage/)
