"""
主窗口
包含 2D/3D 标签页、输出面板、进度控件、菜单栏和配置持久化。
"""

import json
import os

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from beidou_params import BeiDou2DConfig, BeiDou3DConfig
from ui.common_panel import CommonPanel
from ui.twod_panel import TwoDPanel
from ui.threed_panel import ThreeDPanel
from ui.output_panel import OutputPanel
from ui.progress_widget import ProgressWidget
from ui.worker_thread import run_generation

APP_NAME = "BeiDou Grid Generator"
APP_VERSION = "1.0"
ORG_NAME = "BeiDouGrid"


class MainWindow(QMainWindow):
    """应用主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} - GB/T 39409-2020")
        self.setMinimumSize(960, 720)
        self.resize(1100, 800)

        self._settings = QSettings(ORG_NAME, APP_NAME.replace(" ", ""))
        self._current_thread = None
        self._current_worker = None

        # --- 中心控件 ---
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # 标签页
        self._tabs = QTabWidget()
        self._twod_panel = TwoDPanel()
        self._threed_panel = ThreeDPanel()
        self._tabs.addTab(self._twod_panel, "2D 网格生成 (SpatiaLite)")
        self._tabs.addTab(self._threed_panel, "3D 网格生成 (OBJ/MTL)")

        # 进度 + 输出 (水平分割)
        bottom_splitter = QSplitter(Qt.Orientation.Vertical)
        self._progress = ProgressWidget()
        self._output = OutputPanel()
        bottom_splitter.addWidget(self._progress)
        bottom_splitter.addWidget(self._output)
        bottom_splitter.setSizes([200, 300])

        main_layout.addWidget(self._tabs, 2)
        main_layout.addWidget(bottom_splitter, 1)

        # --- 菜单栏 ---
        self._setup_menu()

        # --- 信号连线 ---
        self._setup_signals()

        # --- 加载上次配置 ---
        self._load_config()

        # --- 状态栏 ---
        self.statusBar().showMessage("就绪")

    # ============================================================
    # 菜单设置
    # ============================================================

    def _setup_menu(self):
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")

        save_action = QAction("保存配置", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_config)
        file_menu.addAction(save_action)

        load_action = QAction("加载配置", self)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self._load_config_from_file)
        file_menu.addAction(load_action)

        file_menu.addSeparator()

        exit_action = QAction("退出", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # ============================================================
    # 信号连线
    # ============================================================

    def _setup_signals(self):
        # 2D
        self._twod_panel.generate_button.clicked.connect(self._on_2d_generate)
        self._twod_panel.estimate_button.clicked.connect(self._on_2d_estimate)

        # 3D
        self._threed_panel.generate_button.clicked.connect(self._on_3d_generate)
        self._threed_panel.estimate_button.clicked.connect(self._on_3d_estimate)

        # 取消
        self._progress.set_cancel_callback(self._on_cancel)

    # ============================================================
    # 生成逻辑
    # ============================================================

    def _on_2d_generate(self):
        config = self._twod_panel.get_config()
        errors = config.validate()
        if errors:
            self._show_validation_errors(errors)
            return

        self._start_generation("2d", config)

    def _on_3d_generate(self):
        config = self._threed_panel.get_config()
        errors = config.validate()
        if errors:
            self._show_validation_errors(errors)
            return

        self._start_generation("3d", config)

    def _start_generation(self, gen_type, config):
        """启动异步生成"""
        if self._current_thread is not None:
            return  # 已有任务在运行，忽略重复点击

        self._output.clear()
        self._progress.reset()
        self._progress.set_running(True)

        # 禁用面板
        self._twod_panel.set_running(True)
        self._threed_panel.set_running(True)

        self.statusBar().showMessage("正在生成...")

        thread, worker = run_generation(
            self,
            gen_type,
            config,
            on_progress=self._on_progress,
            on_finished=self._on_finished,
            on_error=self._on_error,
        )
        self._current_thread = thread
        self._current_worker = worker

    def _on_progress(self, percent: int, message: str):
        self._progress.update_progress(percent, message)
        self.statusBar().showMessage(message)

    def _on_finished(self, results: dict):
        self._progress.set_running(False)
        self._twod_panel.set_running(False)
        self._threed_panel.set_running(False)
        self._output.show_results(results)
        self.statusBar().showMessage("生成完成")
        self._current_thread = None
        self._current_worker = None

    def _on_error(self, error_msg: str):
        self._progress.set_running(False)
        self._twod_panel.set_running(False)
        self._threed_panel.set_running(False)
        self._progress.log_error(error_msg[:500])
        self.statusBar().showMessage("生成失败")

        QMessageBox.critical(self, "生成错误", f"生成过程中发生错误:\n\n{error_msg[:800]}")
        self._current_thread = None
        self._current_worker = None

    def _on_cancel(self):
        if self._current_worker:
            self._progress.log_info("正在取消...")
            self._current_worker.stop()

    def _on_2d_estimate(self):
        config = self._twod_panel.get_config()
        errors = config.validate()
        if errors:
            self._show_validation_errors(errors)
            return
        estimates = config.estimate_2d_cells()
        msg = "预估 2D 网格数:\n\n"
        for level in sorted(estimates.keys()):
            msg += f"  Level {level}: {estimates[level]:,} cells\n"
        msg += f"\n总计: {sum(estimates.values()):,} cells"
        QMessageBox.information(self, "预估结果", msg)

    def _on_3d_estimate(self):
        config = self._threed_panel.get_config()
        errors = config.validate()
        if errors:
            self._show_validation_errors(errors)
            return
        estimates = config.estimate_3d_cells()
        msg = "预估 3D 网格数:\n\n"
        for level in sorted(estimates.keys()):
            h_layers = len(config.get_height_layers(level))
            msg += f"  Level {level}: {estimates[level]:,} cells ({h_layers} 高度层)\n"
        msg += f"\n总计: {sum(estimates.values()):,} cells"
        QMessageBox.information(self, "预估结果", msg)

    def _show_validation_errors(self, errors: list):
        QMessageBox.warning(
            self,
            "参数验证失败",
            "以下参数有误:\n\n" + "\n".join(f"  - {e}" for e in errors),
        )

    # ============================================================
    # 配置持久化
    # ============================================================

    def _save_config(self):
        """保存当前标签页的配置到 QSettings 和可选 JSON 文件"""
        path, _ = QFileDialog.getSaveFileName(
            self, "保存配置", "beidou_config.json", "JSON 文件 (*.json)"
        )
        if not path:
            return

        if self._tabs.currentIndex() == 0:
            config = self._twod_panel.get_config()
            data = {"type": "2d", "config": config.to_dict()}
        else:
            config = self._threed_panel.get_config()
            data = {"type": "3d", "config": config.to_dict()}

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self._save_last_config()
        self.statusBar().showMessage(f"配置已保存: {path}")

    def _load_config_from_file(self):
        """从 JSON 文件加载配置"""
        path, _ = QFileDialog.getOpenFileName(
            self, "加载配置", "", "JSON 文件 (*.json)"
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if data.get("type") == "2d":
                config = BeiDou2DConfig.from_dict(data["config"])
                self._twod_panel.set_config(config)
                self._tabs.setCurrentIndex(0)
            else:
                config = BeiDou3DConfig.from_dict(data["config"])
                self._threed_panel.set_config(config)
                self._tabs.setCurrentIndex(1)

            self.statusBar().showMessage(f"配置已加载: {path}")
        except Exception as e:
            QMessageBox.warning(self, "加载失败", f"无法加载配置文件:\n{e}")

    def _save_last_config(self):
        """保存上次配置到 QSettings (应用关闭时自动调用)"""
        try:
            # 保存 2D 配置
            cfg_2d = self._twod_panel.get_config()
            d2 = cfg_2d.to_dict()
            for k, v in d2.items():
                self._settings.setValue(f"2d/{k}", v)

            # 保存 3D 配置
            cfg_3d = self._threed_panel.get_config()
            d3 = cfg_3d.to_dict()
            for k, v in d3.items():
                self._settings.setValue(f"3d/{k}", v)
        except Exception:
            pass  # 静默忽略保存失败

    def _load_config(self):
        """从 QSettings 恢复上次的配置"""
        try:
            # 2D
            d2 = {}
            for key in BeiDou2DConfig.__dataclass_fields__:
                val = self._settings.value(f"2d/{key}")
                if val is not None:
                    d2[key] = val
            if d2:
                config_2d = BeiDou2DConfig.from_dict(d2)
                self._twod_panel.set_config(config_2d)

            # 3D
            d3 = {}
            for key in BeiDou3DConfig.__dataclass_fields__:
                val = self._settings.value(f"3d/{key}")
                if val is not None:
                    d3[key] = val
            if d3:
                config_3d = BeiDou3DConfig.from_dict(d3)
                self._threed_panel.set_config(config_3d)
        except Exception:
            pass  # 恢复失败使用默认值

    def _show_about(self):
        QMessageBox.about(
            self,
            "关于",
            f"<h3>{APP_NAME} v{APP_VERSION}</h3>"
            f"<p>北斗网格位置码生成工具</p>"
            f"<p>基于 GB/T 39409-2020 国家标准</p>"
            f"<p>支持 2D (SpatiaLite) 和 3D (OBJ/MTL) 网格生成</p>"
            f"<hr>"
            f"<p>Python + PySide6 + geopandas + pyproj</p>",
        )

    # ============================================================
    # 生命周期
    # ============================================================

    def closeEvent(self, event):
        """关闭时保存配置"""
        if self._current_thread is not None:
            self._current_worker.stop()
            self._current_thread.quit()
            if not self._current_thread.wait(3000):
                self._current_thread.terminate()
                self._current_thread.wait()
        self._save_last_config()
        super().closeEvent(event)
