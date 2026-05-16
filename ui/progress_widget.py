"""
进度显示控件
包含进度条、状态标签和日志区域。
"""

from datetime import datetime

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ProgressWidget(QWidget):
    """进度条 + 状态消息 + 日志 + 取消按钮"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # --- 进度行 ---
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%p%")

        self._status_label = QLabel("就绪")
        self._status_label.setStyleSheet("color: #666; font-size: 13px;")

        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setFixedWidth(80)
        self._cancel_btn.setStyleSheet("""
            QPushButton { background-color: #e74c3c; color: white; border: none; padding: 6px 12px; border-radius: 4px; }
            QPushButton:hover { background-color: #c0392b; }
            QPushButton:disabled { background-color: #bdc3c7; }
        """)

        progress_row = QHBoxLayout()
        progress_row.addWidget(QLabel("进度:"))
        progress_row.addWidget(self._progress_bar, 1)
        progress_row.addWidget(self._cancel_btn)

        # --- 日志区域 ---
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        self._log.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: Consolas, monospace;
                font-size: 12px;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
            }
        """)

        # --- 布局 ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(progress_row)
        layout.addWidget(self._status_label)
        layout.addWidget(self._log)

    # --- 公开接口 ---

    def set_cancel_callback(self, callback):
        """设置取消按钮的回调"""
        self._cancel_btn.clicked.connect(callback)

    def set_running(self, running: bool):
        """设置运行状态（启用/禁用取消按钮）"""
        self._cancel_btn.setEnabled(running)

    def update_progress(self, percent: int, message: str):
        """更新进度"""
        self._progress_bar.setValue(percent)
        self._status_label.setText(message)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log.appendPlainText(f"[{timestamp}] {message}")

    def reset(self):
        """重置为初始状态"""
        self._progress_bar.setValue(0)
        self._status_label.setText("就绪")
        self._cancel_btn.setEnabled(False)
        self._log.clear()

    def log_info(self, text: str):
        """添加信息日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log.appendPlainText(f"[{timestamp}] {text}")

    def log_error(self, text: str):
        """添加错误日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log.appendPlainText(f"[{timestamp}] [错误] {text}")
