"""
异步生成工作线程
将耗时的网格生成操作移到 QThread 中执行，避免阻塞 UI。
"""

import os
import threading
import traceback

from PySide6.QtCore import QObject, QThread, Signal, Slot

from beidou_3d_engine import generate_3d_grid
from beidou_grid_engine import generate_2d_grid


class GenerationWorker(QObject):
    """在后台线程中执行网格生成的 Worker"""

    # 信号
    progress = Signal(int, str)          # (percent: 0-100, message)
    finished = Signal(dict)               # results dict
    error = Signal(str)                   # error message

    def __init__(self, generation_type, config):
        """
        generation_type: '2d' 或 '3d'
        config: BeiDou2DConfig 或 BeiDou3DConfig
        """
        super().__init__()
        self._type = generation_type
        self._config = config
        self._stop_event = threading.Event()

    def stop(self):
        """请求停止生成"""
        self._stop_event.set()

    @Slot()
    def run(self):
        """在主线程中通过信号触发，在 QThread 中执行"""
        try:
            if self._type == "2d":
                results_by_level = {}
                def on_progress(pct, msg):
                    self.progress.emit(pct, msg)

                gdfs = generate_2d_grid(
                    self._config,
                    progress_callback=on_progress,
                    stop_event=self._stop_event,
                )

                # 转换为可序列化的结果
                for level, gdf in gdfs.items():
                    cell_count = gdf.attrs.get("cell_count", len(gdf))
                    results_by_level[level] = {
                        "cells": int(cell_count),
                        "type": "2d",
                    }

                if self._config.output_type == "postgis":
                    # PostGIS 输出：记录连接和表信息
                    results_by_level["_files"] = []
                    results_by_level["_type"] = "2d"
                    results_by_level["_output_type"] = "postgis"
                    results_by_level["_pg_info"] = (
                        f"{self._config.pg_host}:{self._config.pg_port}/"
                        f"{self._config.pg_database} [{self._config.pg_schema}]"
                    )
                else:
                    output_path = os.path.join(self._config.output_dir, self._config.output_db_name)
                    results_by_level["_files"] = [output_path]
                    results_by_level["_type"] = "2d"

                self.finished.emit(results_by_level)

            elif self._type == "3d":
                def on_progress(pct, msg):
                    self.progress.emit(pct, msg)

                results = generate_3d_grid(
                    self._config,
                    progress_callback=on_progress,
                    stop_event=self._stop_event,
                )

                # 收集文件列表
                files = []
                for level, info in sorted(results.items()):
                    if isinstance(info, dict):
                        if "obj_path" in info:
                            files.append(info["obj_path"])
                        if "mtl_path" in info:
                            files.append(info["mtl_path"])

                results["_files"] = files
                results["_type"] = "3d"

                self.finished.emit(results)

            else:
                self.error.emit(f"未知的生成类型: {self._type}")

        except Exception as e:
            tb = traceback.format_exc()
            self.error.emit(f"{e}\n\n{tb}")


def run_generation(parent, generation_type, config, on_progress, on_finished, on_error):
    """
    启动异步生成。

    参数:
        parent: QObject 父对象 (用于线程生命周期管理)
        generation_type: '2d' 或 '3d'
        config: BeiDou2DConfig 或 BeiDou3DConfig
        on_progress: callable(percent, message)
        on_finished: callable(results_dict)
        on_error: callable(error_message_str)

    返回: (QThread, GenerationWorker) — 用于 cancel
    """
    thread = QThread(parent)
    worker = GenerationWorker(generation_type, config)
    worker.moveToThread(thread)

    # 连线
    worker.progress.connect(on_progress)
    worker.finished.connect(on_finished)
    worker.error.connect(on_error)

    # 线程完成时清理
    worker.finished.connect(thread.quit)
    worker.error.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)

    # 启动
    thread.started.connect(worker.run)
    thread.start()

    return thread, worker
