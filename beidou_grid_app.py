#!/usr/bin/env python
"""
BeiDou Grid Generator - 桌面端应用程序入口
基于 GB/T 39409-2020 北斗网格位置码国家标准

用法:
    python beidou_grid_app.py          # 启动 GUI
"""

import sys
import traceback
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

# 确保当前目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent))

from ui.main_window import MainWindow, APP_NAME, ORG_NAME


def setup_exception_hook():
    """全局未捕获异常捕获"""
    original_hook = sys.excepthook

    def exception_hook(exc_type, exc_value, exc_tb):
        # 打印到 stderr
        original_hook(exc_type, exc_value, exc_tb)
        # 如果是 GUI 线程异常，弹窗显示
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        if QApplication.instance():
            QMessageBox.critical(None, "未处理的异常", f"发生未捕获的异常:\n\n{tb_str[:1000]}")

    sys.excepthook = exception_hook


def main():
    # 全局异常捕获
    setup_exception_hook()

    # 创建 QApplication
    app = QApplication(sys.argv)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationName(APP_NAME.replace(" ", ""))
    app.setApplicationVersion("1.0")

    # 设置 Fusion 风格（跨平台一致）
    app.setStyle("Fusion")

    # 全局字体
    font = QFont()
    if sys.platform == "win32":
        font.setFamilies(["Microsoft YaHei", "Segoe UI", "Arial"])
    else:
        font.setFamilies(["Noto Sans CJK SC", "WenQuanYi Micro Hei", "Arial"])
    font.setPointSize(10)
    app.setFont(font)

    # 全局样式表
    app.setStyleSheet("""
        QMainWindow { background-color: #f5f6fa; }
        QGroupBox {
            font-weight: bold;
            border: 2px solid #dcdde1;
            border-radius: 6px;
            margin-top: 12px;
            padding-top: 16px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
        }
        QTabWidget::pane {
            border: 1px solid #dcdde1;
            background-color: #ffffff;
            border-radius: 4px;
        }
        QTabBar::tab {
            padding: 8px 20px;
            margin-right: 2px;
            border: 1px solid #dcdde1;
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            background-color: #ecf0f1;
        }
        QTabBar::tab:selected {
            background-color: #ffffff;
            font-weight: bold;
        }
        QTabBar::tab:hover:!selected {
            background-color: #dfe6e9;
        }
        QPushButton {
            padding: 6px 16px;
            border: 1px solid #bdc3c7;
            border-radius: 4px;
            background-color: #ffffff;
        }
        QPushButton:hover {
            background-color: #ecf0f1;
        }
        QPushButton:disabled {
            color: #bdc3c7;
        }
        QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
            padding: 4px 8px;
            border: 1px solid #bdc3c7;
            border-radius: 3px;
        }
        QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {
            border-color: #3498db;
        }
        QTableWidget {
            border: 1px solid #dcdde1;
            gridline-color: #ecf0f1;
        }
        QHeaderView::section {
            background-color: #ecf0f1;
            padding: 4px;
            border: 1px solid #dcdde1;
        }
    """)

    # 创建并显示主窗口
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
