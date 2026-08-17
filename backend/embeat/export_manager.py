from __future__ import annotations

import copy
import threading
import uuid
from typing import Any


class ExportManager:
    """Runs one or both playlist exports under one progress/status contract."""

    def __init__(self, netease: Any, kugou: Any) -> None:
        self.netease = netease
        self.kugou = kugou
        self.jobs: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()

    def start(self, target: str, tracks: list[dict[str, Any]], netease_config: dict[str, Any], kugou_config: dict[str, Any], user_id: int = 0, clients: dict[str, Any] | None = None, app_db: Any = None) -> dict[str, str]:
        targets = [target] if target in {"netease", "kugou"} else ["netease", "kugou"]
        if target not in {"netease", "kugou", "both"}:
            raise ValueError("保存目标必须是 netease、kugou 或 both")
        if not tracks:
            raise ValueError("请至少选择一首歌曲")
        job_id = uuid.uuid4().hex
        platform_jobs = {
            platform: {"status": "queued", "phase": "等待开始", "current": "", "processed": 0, "total": len(tracks), "percent": 0, "error": ""}
            for platform in targets
        }
        job = {"id": job_id, "user_id": user_id, "clients": clients or {}, "app_db": app_db, "status": "queued", "phase": "准备保存", "current": "", "processed": 0, "total": len(tracks) * len(targets), "percent": 0, "platforms": platform_jobs, "result": None, "error": ""}
        with self.lock:
            self.jobs[job_id] = job
        threading.Thread(target=self._run, args=(job_id, targets, tracks, netease_config, kugou_config), name=f"export-{job_id[:8]}", daemon=True).start()
        return {"job_id": job_id}

    def status(self, job_id: str, user_id: int | None = None) -> dict[str, Any]:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or (user_id is not None and job.get("user_id") != user_id):
                raise LookupError("保存任务不存在或已过期")
            snapshot = copy.deepcopy({key: value for key, value in job.items() if key not in {"clients", "app_db"}})
            return snapshot

    def _update(self, job_id: str, **values: Any) -> None:
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id].update(values)

    def _update_platform(self, job_id: str, platform: str, **values: Any) -> None:
        with self.lock:
            job = self.jobs.get(job_id)
            if job and platform in job.get("platforms", {}):
                job["platforms"][platform].update(values)

    def _run(self, job_id: str, targets: list[str], tracks: list[dict[str, Any]], netease_config: dict[str, Any], kugou_config: dict[str, Any]) -> None:
        results: dict[str, Any] = {}
        for index, platform in enumerate(targets):
            job = self.jobs.get(job_id) or {}
            client = (job.get("clients") or {}).get(platform) or (self.netease if platform == "netease" else self.kugou)
            config = netease_config if platform == "netease" else kugou_config
            base = index * len(tracks)
            self._update_platform(job_id, platform, status="running", phase="准备目标歌单")
            try:
                with client.lock:
                    result = client.export(tracks, str(config.get("playlist_id") or "NEW"), str(config.get("playlist_name") or ""), progress=lambda **values: self._progress(job_id, platform, base, len(tracks), len(targets), **values))
                results[platform] = {"ok": True, **result}
                app_db = job.get("app_db")
                if app_db:
                    app_db.add_export_log(job.get("user_id", 0), "both" if len(targets) == 2 else platform, platform, results[platform], config, len(tracks))
                self._update_platform(job_id, platform, status="completed", phase="保存完成", current="", processed=len(tracks), percent=100)
            except Exception as exc:
                results[platform] = {"ok": False, "error": str(exc)}
                self._update_platform(job_id, platform, status="failed", phase="保存失败", current="", error=str(exc))
        failed = [platform for platform, result in results.items() if not result.get("ok")]
        self._update(job_id, status="completed", phase="保存完成" if not failed else "保存完成（部分失败）", current="", processed=len(tracks) * len(targets), percent=100, result={"targets": results})

    def _progress(self, job_id: str, platform: str, base: int, total: int, target_count: int, **values: Any) -> None:
        platform_name = "网易云" if platform == "netease" else "酷狗"
        processed = base + int(values.get("processed") or 0)
        job_total = max(total * target_count, total)
        percent = int((processed / job_total) * 92)
        if "percent" in values:
            local_percent = max(0, min(100, int(values["percent"])))
            percent = int(((base + local_percent / 100 * total) / job_total) * 100)
        else:
            local_percent = int(int(values.get("processed") or 0) / max(total, 1) * 100)
        self._update_platform(
            job_id,
            platform,
            status="running",
            phase=values.get("phase") or "处理中",
            current=values.get("current") or "",
            processed=int(values.get("processed") or 0),
            percent=max(0, min(99, local_percent)),
        )
        self._update(job_id, status="running", phase=f"{platform_name}：{values.get('phase') or '处理中'}", current=values.get("current") or "", processed=processed, percent=max(0, min(99, percent)))
