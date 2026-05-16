"""
3D 网格生成面板
包含共用参数 + 高度/CRS/材质等 3D 专有参数。
"""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
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

from beidou_params import BeiDou2DConfig, BeiDou3DConfig
from ui.common_panel import CommonPanel


class ThreeDPanel(QWidget):
    """3D 标签页内容"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # --- 可滚动内容 ---
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(8)

        # 共用面板
        self._common = CommonPanel()

        # ========== 高度设置 ==========
        height_group = QGroupBox("高度设置")
        h_form = QFormLayout(height_group)
        h_form.setSpacing(4)

        self._h_min_spin = QDoubleSpinBox()
        self._h_min_spin.setRange(-1000, 50000)
        self._h_min_spin.setDecimals(1)
        self._h_min_spin.setValue(0.0)
        self._h_min_spin.setSuffix(" m")
        self._h_min_spin.setMinimumWidth(120)

        self._h_max_spin = QDoubleSpinBox()
        self._h_max_spin.setRange(-1000, 50000)
        self._h_max_spin.setDecimals(1)
        self._h_max_spin.setValue(1000.0)
        self._h_max_spin.setSuffix(" m")
        self._h_max_spin.setMinimumWidth(120)

        h_form.addRow("最低高度:", self._h_min_spin)
        h_form.addRow("最高高度:", self._h_max_spin)

        # ========== 坐标系 ==========
        crs_group = QGroupBox("坐标系")
        crs_form = QFormLayout(crs_group)

        self._source_crs_combo = QComboBox()
        self._source_crs_combo.addItems(["EPSG:4326", "EPSG:4490"])
        self._source_crs_combo.setEditable(True)

        self._target_crs_combo = QComboBox()
        self._target_crs_combo.addItems(["EPSG:4547", "EPSG:4548", "EPSG:4549", "EPSG:4326"])
        self._target_crs_combo.setEditable(True)

        crs_form.addRow("源 CRS:", self._source_crs_combo)
        crs_form.addRow("目标 CRS:", self._target_crs_combo)

        # ========== MTL 材质 ==========
        mtl_group = QGroupBox("MTL 材质设置")
        mtl_form = QFormLayout(mtl_group)
        mtl_form.setSpacing(4)

        self._color_btns = {}
        color_keys = [
            ("Ka (环境光)", "mtl_ka", (26, 26, 77)),
            ("Kd (漫反射)", "mtl_kd", (77, 128, 230)),
            ("Ks (镜面反射)", "mtl_ks", (26, 26, 26)),
        ]
        for label, key, default_rgb in color_keys:
            btn = QPushButton()
            btn.setFixedSize(28, 20)
            btn.setStyleSheet(
                f"background-color: rgb({default_rgb[0]},{default_rgb[1]},{default_rgb[2]});"
                f"border: 1px solid #999; border-radius: 2px;"
            )
            btn.clicked.connect(lambda checked=False, k=key: self._pick_color(k))
            self._color_btns[key] = {"btn": btn, "rgb": default_rgb}

            row = QHBoxLayout()
            row.addWidget(btn)
            row.addWidget(QLabel(label))
            row.addStretch()
            mtl_form.addRow(row)

        self._ns_spin = QDoubleSpinBox()
        self._ns_spin.setRange(0, 1000)
        self._ns_spin.setDecimals(1)
        self._ns_spin.setValue(30.0)

        self._d_spin = QDoubleSpinBox()
        self._d_spin.setRange(0.0, 1.0)
        self._d_spin.setDecimals(2)
        self._d_spin.setValue(0.3)
        self._d_spin.setSingleStep(0.05)

        self._illum_combo = QComboBox()
        self._illum_combo.addItem("2 (漫反射+镜面)", 2)
        self._illum_combo.addItem("1 (仅漫反射+环境)", 1)
        self._illum_combo.addItem("0 (仅环境)", 0)

        mtl_form.addRow("高光指数 (Ns):", self._ns_spin)
        mtl_form.addRow("不透明度 (d):", self._d_spin)
        mtl_form.addRow("光照模型:", self._illum_combo)

        # ========== 文件名模板 ==========
        file_group = QGroupBox("输出文件名")
        file_form = QFormLayout(file_group)
        self._obj_pattern_edit = QLineEdit("beidou_3d_level_{level}")
        file_form.addRow("模板 ({level}=层级号):", self._obj_pattern_edit)

        # ========== 按钮 ==========
        btn_layout = QHBoxLayout()
        self._estimate_btn = QPushButton("预估网格数")
        self._generate_btn = QPushButton("▶ 生成 3D 网格")
        self._generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60; color: white; border: none;
                padding: 8px 24px; border-radius: 4px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #2ecc71; }
            QPushButton:disabled { background-color: #95a5a6; }
        """)

        btn_layout.addWidget(self._estimate_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self._generate_btn)

        # ========== 组装 ==========
        content_layout.addWidget(self._common)
        content_layout.addWidget(height_group)
        content_layout.addWidget(crs_group)
        content_layout.addWidget(mtl_group)
        content_layout.addWidget(file_group)
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

    def get_config(self) -> BeiDou3DConfig:
        geo = self._common.get_3d_geo_params()
        ka_r, ka_g, ka_b = self._color_btns["mtl_ka"]["rgb"]
        kd_r, kd_g, kd_b = self._color_btns["mtl_kd"]["rgb"]
        ks_r, ks_g, ks_b = self._color_btns["mtl_ks"]["rgb"]

        illum = self._illum_combo.currentData()

        return BeiDou3DConfig(
            **geo,
            h_min=self._h_min_spin.value(),
            h_max=self._h_max_spin.value(),
            source_crs=self._source_crs_combo.currentText(),
            target_crs=self._target_crs_combo.currentText(),
            mtl_ka_r=ka_r / 255.0,
            mtl_ka_g=ka_g / 255.0,
            mtl_ka_b=ka_b / 255.0,
            mtl_kd_r=kd_r / 255.0,
            mtl_kd_g=kd_g / 255.0,
            mtl_kd_b=kd_b / 255.0,
            mtl_ks_r=ks_r / 255.0,
            mtl_ks_g=ks_g / 255.0,
            mtl_ks_b=ks_b / 255.0,
            mtl_ns=self._ns_spin.value(),
            mtl_d=self._d_spin.value(),
            mtl_illum=illum,
            obj_pattern=self._obj_pattern_edit.text(),
        )

    def set_config(self, config: BeiDou3DConfig):
        self._common.set_2d_config(
            BeiDou2DConfig(
                west=config.west, east=config.east,
                south=config.south, north=config.north,
                center_lon=config.center_lon, center_lat=config.center_lat,
                levels=config.levels,
                output_dir=config.output_dir,
            )
        )
        self._h_min_spin.setValue(config.h_min)
        self._h_max_spin.setValue(config.h_max)

        for combo, val in [(self._source_crs_combo, config.source_crs),
                            (self._target_crs_combo, config.target_crs)]:
            idx = combo.findText(val)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setEditText(val)

        color_keys = {
            "mtl_ka": (config.mtl_ka_r, config.mtl_ka_g, config.mtl_ka_b),
            "mtl_kd": (config.mtl_kd_r, config.mtl_kd_g, config.mtl_kd_b),
            "mtl_ks": (config.mtl_ks_r, config.mtl_ks_g, config.mtl_ks_b),
        }
        for key, (r, g, b) in color_keys.items():
            rgb = (int(r * 255), int(g * 255), int(b * 255))
            self._color_btns[key]["rgb"] = rgb
            self._color_btns[key]["btn"].setStyleSheet(
                f"background-color: rgb({rgb[0]},{rgb[1]},{rgb[2]});"
                f"border: 1px solid #999; border-radius: 2px;"
            )

        self._ns_spin.setValue(config.mtl_ns)
        self._d_spin.setValue(config.mtl_d)

        idx = self._illum_combo.findData(config.mtl_illum)
        if idx >= 0:
            self._illum_combo.setCurrentIndex(idx)

        self._obj_pattern_edit.setText(config.obj_pattern)

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
            self._generate_btn.setText("▶ 生成 3D 网格")

    # --- 槽 ---

    def _pick_color(self, key: str):
        r, g, b = self._color_btns[key]["rgb"]
        qcolor = QColor(r, g, b)
        color = QColorDialog.getColor(qcolor, self, f"选择 {key} 颜色")
        if color.isValid():
            rgb = (color.red(), color.green(), color.blue())
            self._color_btns[key]["rgb"] = rgb
            self._color_btns[key]["btn"].setStyleSheet(
                f"background-color: rgb({rgb[0]},{rgb[1]},{rgb[2]});"
                f"border: 1px solid #999; border-radius: 2px;"
            )
