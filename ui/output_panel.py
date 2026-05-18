"""
输出面板
显示生成的文件列表和汇总统计表。
"""

import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from beidou_params import LEVEL_LABELS


class OutputPanel(QWidget):
    """输出文件列表 + 汇总统计"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # --- 文件列表 ---
        file_group = QGroupBox("生成的文件")
        self._file_list = QListWidget()
        self._file_list.setAlternatingRowColors(True)
        self._file_list.setStyleSheet("QListWidget { font-size: 13px; }")
        self._file_list.itemDoubleClicked.connect(self._on_file_double_clicked)

        open_btn = QPushButton("打开所在文件夹")
        open_btn.clicked.connect(self._on_open_folder)

        file_layout = QVBoxLayout(file_group)
        file_layout.addWidget(self._file_list)
        file_layout.addWidget(open_btn)

        # --- 汇总表 ---
        summary_group = QGroupBox("各级别汇总")
        self._summary_table = QTableWidget()
        self._summary_table.setColumnCount(5)
        self._summary_table.setHorizontalHeaderLabels(["级别", "网格单元数", "单元尺寸", "高度层", "文件大小"])
        self._summary_table.horizontalHeader().setStretchLastSection(True)
        self._summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._summary_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._summary_table.setAlternatingRowColors(True)

        summary_layout = QVBoxLayout(summary_group)
        summary_layout.addWidget(self._summary_table)

        # --- 主布局 ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(file_group)
        layout.addWidget(summary_group)

    # --- 公开接口 ---

    def show_results(self, results: dict):
        """显示生成结果"""
        gen_type = results.get("_type", "2d")
        files = results.get("_files", [])
        output_type = results.get("_output_type", "spatialite")

        # 更新文件列表
        self._file_list.clear()
        if output_type == "postgis":
            pg_info = results.get("_pg_info", "PostGIS")
            self._file_list.addItem(f"PostGIS: {pg_info}")
            # 列出各级别表名
            levels = sorted([k for k in results.keys() if isinstance(k, int)])
            for lvl in levels:
                self._file_list.addItem(f"  → grid_level_{lvl}")
        else:
            for fpath in files:
                if os.path.exists(fpath):
                    size_kb = os.path.getsize(fpath) / 1024
                    if size_kb > 1024:
                        size_str = f"{size_kb / 1024:.1f} MB"
                    else:
                        size_str = f"{size_kb:.1f} KB"
                    self._file_list.addItem(f"{os.path.basename(fpath)}  ({size_str})")
                    self._file_list.item(self._file_list.count() - 1).setData(Qt.UserRole, fpath)
                else:
                    self._file_list.addItem(fpath)

        # 更新汇总表
        levels = sorted([k for k in results.keys() if isinstance(k, int)])
        self._summary_table.setRowCount(len(levels))

        for i, level in enumerate(levels):
            info = results[level]
            cells = info.get("cells", 0)

            self._summary_table.setItem(i, 0, QTableWidgetItem(str(level)))
            self._summary_table.setItem(i, 1, QTableWidgetItem(f"{cells:,}"))
            self._summary_table.setItem(i, 2, QTableWidgetItem(LEVEL_LABELS.get(level, "")))

            if "height_layers" in info:
                self._summary_table.setItem(i, 3, QTableWidgetItem(str(info["height_layers"])))

            if "size_kb" in info:
                size = info["size_kb"]
                if size > 1024:
                    self._summary_table.setItem(i, 4, QTableWidgetItem(f"{size / 1024:.1f} MB"))
                else:
                    self._summary_table.setItem(i, 4, QTableWidgetItem(f"{size:.1f} KB"))

    def clear(self):
        """清除显示"""
        self._file_list.clear()
        self._summary_table.setRowCount(0)

    # --- 槽 ---

    def _on_file_double_clicked(self, item):
        """双击文件项打开"""
        fpath = item.data(Qt.UserRole)
        if fpath and os.path.exists(fpath):
            QDesktopServices.openUrl(QUrl.fromLocalFile(fpath))

    def _on_open_folder(self):
        """打开输出文件夹"""
        if self._file_list.count() > 0:
            fpath = self._file_list.item(0).data(Qt.UserRole)
            if fpath and os.path.exists(fpath):
                folder = os.path.dirname(fpath)
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
