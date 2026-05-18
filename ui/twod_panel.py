"""
2D 网格生成面板
包含共用参数 + 输出方式选择 + SpatiaLite/PostGIS 配置 + 生成按钮。
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
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from beidou_grid_engine import test_postgis_connection
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

        # ========== 输出方式选择 ==========
        output_type_group = QGroupBox("输出方式")
        output_type_row = QHBoxLayout()

        self._spatialite_radio = QRadioButton("SpatiaLite (本地文件)")
        self._spatialite_radio.setChecked(True)
        self._postgis_radio = QRadioButton("PostGIS (远程数据库)")

        output_type_row.addWidget(self._spatialite_radio)
        output_type_row.addWidget(self._postgis_radio)
        output_type_row.addStretch()
        output_type_group.setLayout(output_type_row)

        # ========== SpatiaLite 配置 ==========
        self._spatialite_widget = QWidget()
        sl_layout = QFormLayout(self._spatialite_widget)

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

        sl_layout.addRow("数据库文件:", db_row)
        sl_layout.addRow("坐标参考系:", self._crs_combo)

        # ========== PostGIS 配置 ==========
        self._postgis_widget = QWidget()
        pg_layout = QFormLayout(self._postgis_widget)

        self._pg_host_edit = QLineEdit("localhost")
        self._pg_port_spin = QSpinBox()
        self._pg_port_spin.setRange(1, 65535)
        self._pg_port_spin.setValue(5432)
        self._pg_port_spin.setFixedWidth(100)

        port_row = QHBoxLayout()
        port_row.addWidget(self._pg_host_edit, 1)
        port_row.addWidget(QLabel("端口:"))
        port_row.addWidget(self._pg_port_spin)
        port_row.addStretch()

        self._pg_database_edit = QLineEdit("gx_low_altitude")
        self._pg_schema_edit = QLineEdit("public")
        self._pg_user_edit = QLineEdit("postgres")
        self._pg_password_edit = QLineEdit('123456')
        self._pg_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pg_table_prefix_edit = QLineEdit("grid_level_")

        pg_layout.addRow("主机:端口:", port_row)
        pg_layout.addRow("数据库:", self._pg_database_edit)
        pg_layout.addRow("Schema:", self._pg_schema_edit)
        pg_layout.addRow("用户名:", self._pg_user_edit)
        pg_layout.addRow("密码:", self._pg_password_edit)
        pg_layout.addRow("表名前缀:", self._pg_table_prefix_edit)

        # 测试连接按钮
        self._test_conn_btn = QPushButton("测试连接")
        self._test_conn_btn.setFixedWidth(100)
        self._test_conn_btn.clicked.connect(self._on_test_connection)

        test_row = QHBoxLayout()
        test_row.addWidget(self._test_conn_btn)
        test_row.addStretch()
        pg_layout.addRow(test_row)

        # ========== 输出配置堆叠（切换 SpatiaLite / PostGIS） ==========
        self._output_stack = QStackedWidget()
        self._output_stack.addWidget(self._spatialite_widget)  # index 0
        self._output_stack.addWidget(self._postgis_widget)      # index 1

        # ========== 按钮 ==========
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
        content_layout.addWidget(output_type_group)
        content_layout.addWidget(self._output_stack)
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

        # --- 信号连线 ---
        self._spatialite_radio.toggled.connect(self._on_output_type_changed)
        self._postgis_radio.toggled.connect(self._on_output_type_changed)

        # 初始状态
        self._output_stack.setCurrentIndex(0)

    # --- 公开接口 ---

    def get_config(self) -> BeiDou2DConfig:
        config = self._common.get_2d_config()

        # SpatiaLite 参数
        full_path = self._db_path_edit.text().strip()
        if full_path:
            db_dir = os.path.dirname(full_path) or config.output_dir
            db_name = os.path.basename(full_path)
            config.output_dir = db_dir
            config.output_db_name = db_name
        config.crs = self._crs_combo.currentText()

        # 输出方式
        config.output_type = "postgis" if self._postgis_radio.isChecked() else "spatialite"

        # PostGIS 参数
        config.pg_host = self._pg_host_edit.text().strip()
        config.pg_port = self._pg_port_spin.value()
        config.pg_database = self._pg_database_edit.text().strip()
        config.pg_schema = self._pg_schema_edit.text().strip()
        config.pg_user = self._pg_user_edit.text().strip()
        config.pg_password = self._pg_password_edit.text()
        config.pg_table_prefix = self._pg_table_prefix_edit.text().strip()

        return config

    def set_config(self, config: BeiDou2DConfig):
        self._common.set_2d_config(config)

        # SpatiaLite
        db_path = os.path.join(config.output_dir, config.output_db_name)
        self._db_path_edit.setText(db_path)
        idx = self._crs_combo.findText(config.crs)
        if idx >= 0:
            self._crs_combo.setCurrentIndex(idx)
        else:
            self._crs_combo.setEditText(config.crs)

        # Output type
        is_postgis = config.output_type == "postgis"
        self._postgis_radio.setChecked(is_postgis)
        self._spatialite_radio.setChecked(not is_postgis)

        # PostGIS
        self._pg_host_edit.setText(config.pg_host)
        self._pg_port_spin.setValue(config.pg_port)
        self._pg_database_edit.setText(config.pg_database)
        self._pg_schema_edit.setText(config.pg_schema)
        self._pg_user_edit.setText(config.pg_user)
        self._pg_password_edit.setText(config.pg_password)
        self._pg_table_prefix_edit.setText(config.pg_table_prefix)

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
        self._test_conn_btn.setEnabled(not running)
        self._common.setEnabled(not running)
        self._spatialite_radio.setEnabled(not running)
        self._postgis_radio.setEnabled(not running)
        if running:
            self._generate_btn.setText("生成中...")
        else:
            self._generate_btn.setText("▶ 生成 2D 网格")

    # --- 槽 ---

    def _on_output_type_changed(self, checked):
        """切换输出方式"""
        if self._postgis_radio.isChecked():
            self._output_stack.setCurrentIndex(1)
        else:
            self._output_stack.setCurrentIndex(0)

    def _browse_db_path(self):
        """打开文件保存对话框，选择或新建数据库"""
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
            db_dir = os.path.dirname(path)
            if db_dir:
                self._common.set_output_dir(db_dir)

    def _on_test_connection(self):
        """测试 PostGIS 连接"""
        config = self._common.get_2d_config()
        config.pg_host = self._pg_host_edit.text().strip()
        config.pg_port = self._pg_port_spin.value()
        config.pg_database = self._pg_database_edit.text().strip()
        config.pg_schema = self._pg_schema_edit.text().strip()
        config.pg_user = self._pg_user_edit.text().strip()
        config.pg_password = self._pg_password_edit.text()

        # 基本参数验证
        errors = []
        if not config.pg_host:
            errors.append("主机地址不能为空")
        if not config.pg_database:
            errors.append("数据库名不能为空")
        if not config.pg_user:
            errors.append("用户名不能为空")

        if errors:
            QMessageBox.warning(self, "参数不完整", "\n".join(errors))
            return

        # 执行连接测试（在 UI 线程中同步执行，可能短暂卡顿）
        self._test_conn_btn.setEnabled(False)
        self._test_conn_btn.setText("连接中...")

        try:
            ok, msg = test_postgis_connection(config)
            if ok:
                QMessageBox.information(self, "连接成功", msg)
            else:
                QMessageBox.warning(self, "连接失败", msg)
        except Exception as e:
            QMessageBox.critical(self, "测试失败", f"无法执行连接测试:\n{e}")
        finally:
            self._test_conn_btn.setEnabled(True)
            self._test_conn_btn.setText("测试连接")
