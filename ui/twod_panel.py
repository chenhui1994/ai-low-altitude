"""
2D 网格生成面板
包含共用参数 + 2D 专有参数 + 生成按钮。
"""

import os

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from beidou_params import BeiDou2DConfig
from ui.common_panel import CommonPanel


class TwoDPanel(QWidget):
    """2D 标签页内容"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # --- 可滚动内容 ---
        content = QWidget()
        content_layout = QVBoxLayout(content)

        # 共用面板
        self._common = CommonPanel()

        # 2D 专有参数
        twod_group = QGroupBox("2D 专有参数")

        # 数据库路径 — 支持选择目录新建文件
        self._db_path_edit = QLineEdit("beidou_grid.sqlite")
        self._db_path_edit.setMinimumWidth(200)

        db_browse_btn = QPushButton("另存为...")
        db_browse_btn.setFixedWidth(80)
        db_browse_btn.clicked.connect(self._browse_db_path)

        db_row = QHBoxLayout()
        db_row.addWidget(self._db_path_edit, 1)
        db_row.addWidget(db_browse_btn)

        self._crs_combo = QComboBox()
        self._crs_combo.addItems(["EPSG:4326", "EPSG:4490", "EPSG:4547"])
        self._crs_combo.setEditable(True)

        twod_layout = QFormLayout(twod_group)
        twod_layout.addRow("数据库文件:", db_row)
        twod_layout.addRow("坐标参考系:", self._crs_combo)

        # 按钮
        btn_layout = QHBoxLayout()
        self._estimate_btn = QPushButton("预估网格数")
        self._generate_btn = QPushButton("▶ 生成 2D 网格")
        self._generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #2980b9; color: white; border: none;
                padding: 8px 24px; border-radius: 4px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #3498db; }
            QPushButton:disabled { background-color: #95a5a6; }
        """)

        btn_layout.addWidget(self._estimate_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self._generate_btn)

        content_layout.addWidget(self._common)
        content_layout.addWidget(twod_group)
        content_layout.addLayout(btn_layout)
        content_layout.addStretch()

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    # --- 公开接口 ---

    def get_config(self) -> BeiDou2DConfig:
        config = self._common.get_2d_config()
        # 从完整路径中解析目录和文件名
        full_path = self._db_path_edit.text().strip()
        if full_path:
            db_dir = os.path.dirname(full_path) or config.output_dir
            db_name = os.path.basename(full_path)
            config.output_dir = db_dir
            config.output_db_name = db_name
        config.crs = self._crs_combo.currentText()
        return config

    def set_config(self, config: BeiDou2DConfig):
        self._common.set_2d_config(config)
        # 显示完整路径（如果已有 output_dir + db_name）
        db_path = os.path.join(config.output_dir, config.output_db_name)
        self._db_path_edit.setText(db_path)
        idx = self._crs_combo.findText(config.crs)
        if idx >= 0:
            self._crs_combo.setCurrentIndex(idx)
        else:
            self._crs_combo.setEditText(config.crs)

    @property
    def common_panel(self):
        return self._common

    @property
    def generate_button(self):
        return self._generate_btn

    @property
    def estimate_button(self):
        return self._estimate_btn

    def set_running(self, running: bool):
        self._generate_btn.setEnabled(not running)
        self._estimate_btn.setEnabled(not running)
        self._common.setEnabled(not running)
        if running:
            self._generate_btn.setText("生成中...")
        else:
            self._generate_btn.setText("▶ 生成 2D 网格")

    # --- 槽 ---

    def _browse_db_path(self):
        """打开文件保存对话框，选择或新建数据库"""
        # 解析当前路径作为默认起点
        current = self._db_path_edit.text().strip()
        if not current or not os.path.dirname(current):
            current = os.path.join(self._common.output_dir(), current or "beidou_grid.sqlite")

        path, _ = QFileDialog.getSaveFileName(
            self,
            "选择数据库保存位置",
            current,
            "SQLite 数据库 (*.sqlite *.db);;所有文件 (*)"
        )
        if path:
            self._db_path_edit.setText(path)
            # 同步更新 output_dir
            db_dir = os.path.dirname(path)
            if db_dir:
                self._common.set_output_dir(db_dir)
