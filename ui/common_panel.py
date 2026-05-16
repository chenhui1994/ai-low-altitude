"""
共用参数面板
2D 和 3D 标签页共用的地理范围、层级、输出目录等参数设置。
"""

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from beidou_params import BeiDou2DConfig, DEFAULT_OUTPUT_DIR


def _make_section_label(text: str) -> QLabel:
    """创建分区标签（替代嵌套 QGroupBox 的标题）"""
    label = QLabel(text)
    label.setStyleSheet(
        "font-weight: bold; color: #2c3e50; font-size: 13px;"
        "padding-top: 8px; padding-bottom: 2px;"
        "border-bottom: 1px solid #dcdde1; margin-bottom: 4px;"
    )
    return label


class CommonPanel(QWidget):
    """共用的地理范围和层级参数面板（扁平化布局）"""

    config_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # ========== 地理范围 ==========
        main_layout.addWidget(_make_section_label("地理范围 (WGS84 经纬度)"))

        self._west_spin = self._make_lon_spin(113.7)
        self._east_spin = self._make_lon_spin(114.5)
        self._south_spin = self._make_lat_spin(22.4)
        self._north_spin = self._make_lat_spin(23.5)
        self._center_lon_spin = self._make_lon_spin(114.1)
        self._center_lat_spin = self._make_lat_spin(22.95)

        geo_form = QFormLayout()
        geo_form.setSpacing(6)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("西:"))
        row1.addWidget(self._west_spin)
        row1.addWidget(QLabel("东:"))
        row1.addWidget(self._east_spin)
        geo_form.addRow(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("南:"))
        row2.addWidget(self._south_spin)
        row2.addWidget(QLabel("北:"))
        row2.addWidget(self._north_spin)
        geo_form.addRow(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("中心经度:"))
        row3.addWidget(self._center_lon_spin)
        row3.addWidget(QLabel("中心纬度:"))
        row3.addWidget(self._center_lat_spin)
        geo_form.addRow(row3)

        main_layout.addLayout(geo_form)

        # ========== 输出目录 ==========
        main_layout.addWidget(_make_section_label("输出目录"))

        self._output_dir_edit = QLineEdit(DEFAULT_OUTPUT_DIR)
        browse_btn = QPushButton("浏览...")
        browse_btn.setFixedWidth(70)
        browse_btn.clicked.connect(self._browse_output_dir)

        dir_row = QHBoxLayout()
        dir_row.addWidget(self._output_dir_edit, 1)
        dir_row.addWidget(browse_btn)
        main_layout.addLayout(dir_row)

        # ========== 生成层级 ==========
        main_layout.addWidget(_make_section_label("生成层级"))
        self._level_checkboxes = {}
        level_row = QHBoxLayout()
        for lvl in range(1, 11):
            cb = QCheckBox(str(lvl))
            cb.setChecked(lvl <= 7)
            cb.setStyleSheet("font-size: 14px; padding: 2px 6px;")
            self._level_checkboxes[lvl] = cb
            level_row.addWidget(cb)
        level_row.addStretch()
        main_layout.addLayout(level_row)

        main_layout.addStretch()

        # --- 信号 ---
        for w in [self._west_spin, self._east_spin, self._south_spin, self._north_spin,
                  self._center_lon_spin, self._center_lat_spin]:
            w.valueChanged.connect(lambda: self.config_changed.emit())
        self._output_dir_edit.textChanged.connect(lambda: self.config_changed.emit())
        for cb in self._level_checkboxes.values():
            cb.toggled.connect(lambda: self.config_changed.emit())

    # --- 控件工厂 ---

    def _make_lon_spin(self, default):
        spin = QDoubleSpinBox()
        spin.setRange(-180, 180)
        spin.setDecimals(6)
        spin.setValue(default)
        spin.setMinimumWidth(120)
        return spin

    def _make_lat_spin(self, default):
        spin = QDoubleSpinBox()
        spin.setRange(-90, 90)
        spin.setDecimals(6)
        spin.setValue(default)
        spin.setMinimumWidth(120)
        return spin

    # --- 公开接口 ---

    def get_2d_config(self) -> BeiDou2DConfig:
        levels = [lvl for lvl, cb in self._level_checkboxes.items() if cb.isChecked()]
        return BeiDou2DConfig(
            west=self._west_spin.value(),
            east=self._east_spin.value(),
            south=self._south_spin.value(),
            north=self._north_spin.value(),
            center_lon=self._center_lon_spin.value(),
            center_lat=self._center_lat_spin.value(),
            levels=levels,
            output_dir=self._output_dir_edit.text(),
        )

    def set_2d_config(self, config: BeiDou2DConfig):
        self._west_spin.setValue(config.west)
        self._east_spin.setValue(config.east)
        self._south_spin.setValue(config.south)
        self._north_spin.setValue(config.north)
        self._center_lon_spin.setValue(config.center_lon)
        self._center_lat_spin.setValue(config.center_lat)
        self._output_dir_edit.setText(config.output_dir)
        for lvl, cb in self._level_checkboxes.items():
            cb.setChecked(lvl in config.levels)

    def get_3d_geo_params(self) -> dict:
        levels = [lvl for lvl, cb in self._level_checkboxes.items() if cb.isChecked()]
        return {
            "west": self._west_spin.value(),
            "east": self._east_spin.value(),
            "south": self._south_spin.value(),
            "north": self._north_spin.value(),
            "center_lon": self._center_lon_spin.value(),
            "center_lat": self._center_lat_spin.value(),
            "levels": levels,
            "output_dir": self._output_dir_edit.text(),
        }

    def highlight_invalid(self, field_names: list):
        field_map = {
            "west": self._west_spin, "east": self._east_spin,
            "south": self._south_spin, "north": self._north_spin,
            "center_lon": self._center_lon_spin, "center_lat": self._center_lat_spin,
        }
        for name, w in field_map.items():
            w.setStyleSheet(
                "border: 2px solid red;" if name in field_names else ""
            )

    # --- 槽 ---

    def output_dir(self) -> str:
        return self._output_dir_edit.text()

    def set_output_dir(self, path: str):
        self._output_dir_edit.setText(path)
        self.config_changed.emit()

    def _browse_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_dir())
        if dir_path:
            self.set_output_dir(dir_path)
