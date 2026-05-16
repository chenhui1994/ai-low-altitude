"""
北斗网格生成器 — 参数模型
定义 2D 和 3D 网格生成的所有可配置参数、默认值、验证和序列化。

无最大网格数限制 — 全地理范围按自然分辨率生成。
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path


# ============================================================
# 常量
# ============================================================

# 各级网格单元尺寸 (经度°, 纬度°)
LEVEL_SIZES = {
    1: (6.0, 4.0),
    2: (30 / 60, 30 / 60),
    3: (15 / 60, 10 / 60),
    4: (1 / 60, 1 / 60),
    5: (4 / 3600, 4 / 3600),
    6: (2 / 3600, 2 / 3600),
    7: (0.25 / 3600, 0.25 / 3600),
    8: (0.03125 / 3600, 0.03125 / 3600),
    9: (0.00390625 / 3600, 0.00390625 / 3600),
    10: (0.00048828125 / 3600, 0.00048828125 / 3600),
}

# 各级子分划数 (列数, 行数)
LEVEL_SUBDIVISIONS = {
    2: (12, 8),
    3: (2, 3),
    4: (15, 10),
    5: (15, 15),
    6: (2, 2),
    7: (8, 8),
    8: (8, 8),
    9: (8, 8),
    10: (8, 8),
}

# 各级代码长度
LEVEL_CODE_LENGTHS = {1: 4, 2: 6, 3: 7, 4: 9, 5: 11, 6: 13, 7: 15, 8: 17, 9: 19, 10: 21}

# 各级高度分辨率 (米) — 与纬度分辨率对应
HEIGHT_RESOLUTIONS = {
    1: 445280.0,
    2: 55660.0,
    3: 18553.0,
    4: 1855.3,
    5: 123.7,
    6: 61.8,
    7: 7.7,
    8: 0.97,
    9: 0.12,
    10: 0.015,
}

# 各级标签
LEVEL_LABELS = {
    1: "6°×4°",
    2: "30'×30'",
    3: "15'×10'",
    4: "1'×1'",
    5: '4"×4"',
    6: '2"×2"',
    7: '0.25"×0.25"',
    8: '0.03125"×0.03125"',
    9: '0.00390625"×0.00390625"',
    10: '0.00048828"×0.00048828"',
}

# 默认输出目录（脚本所在目录）
DEFAULT_OUTPUT_DIR = str(Path(__file__).parent)


# ============================================================
# 2D 配置类
# ============================================================

@dataclass
class BeiDou2DConfig:
    """北斗二维网格生成配置（无数据量限制，全范围生成）"""

    # 地理范围 (度)
    west: float = 113.7
    east: float = 114.5
    south: float = 22.4
    north: float = 23.5

    # 中心点 (高级别缩小范围用)
    center_lon: float = 114.1
    center_lat: float = 22.95

    # 要生成的层级 (1-10)
    levels: list = field(default_factory=lambda: [1, 2, 3, 4, 5, 6, 7])

    # 输出
    output_dir: str = DEFAULT_OUTPUT_DIR
    output_db_name: str = "beidou_grid.sqlite"
    crs: str = "EPSG:4326"

    def validate(self) -> list[str]:
        """验证配置，返回错误信息列表（空=合法）"""
        errors = []

        # 经纬度范围
        if not (-180 <= self.west < self.east <= 180):
            errors.append(f"经度范围无效: {self.west} ~ {self.east}（需 -180 ≤ west < east ≤ 180）")
        if not (-90 <= self.south < self.north <= 90):
            errors.append(f"纬度范围无效: {self.south} ~ {self.north}（需 -90 ≤ south < north ≤ 90）")
        if not (self.west <= self.center_lon <= self.east):
            errors.append(f"中心经度 {self.center_lon} 不在范围 {self.west}~{self.east} 内")
        if not (self.south <= self.center_lat <= self.north):
            errors.append(f"中心纬度 {self.center_lat} 不在范围 {self.south}~{self.north} 内")

        # 层级
        if not self.levels:
            errors.append("至少需要选择一个生成层级")
        for lvl in self.levels:
            if lvl not in range(1, 11):
                errors.append(f"无效层级: {lvl}（仅支持 1-10）")

        # 输出
        if not self.output_dir:
            errors.append("输出目录不能为空")
        if not self.output_db_name or not self.output_db_name.strip():
            errors.append("数据库文件名不能为空")
        if not self.crs or not self.crs.strip():
            errors.append("CRS 不能为空")

        return errors

    def to_dict(self) -> dict:
        """序列化为字典"""
        d = asdict(self)
        d["levels"] = ",".join(str(l) for l in self.levels)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "BeiDou2DConfig":
        """从字典反序列化"""
        d = dict(d)
        if "levels" in d and isinstance(d["levels"], str):
            d["levels"] = [int(l) for l in d["levels"].split(",") if l.strip()]
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def estimate_2d_cells(self) -> dict[int, int]:
        """预估各级的2D网格数（全地理范围）"""
        estimates = {}
        for level in self.levels:
            cell_lon, cell_lat = LEVEL_SIZES[level]
            lon_range = self.east - self.west
            lat_range = self.north - self.south
            cols = max(1, int(lon_range / cell_lon))
            rows = max(1, int(lat_range / cell_lat))
            estimates[level] = cols * rows
        return estimates


# ============================================================
# 3D 配置类
# ============================================================

@dataclass
class BeiDou3DConfig:
    """北斗三维网格生成配置（无高度层上限，无数据量限制）"""

    # 地理范围 (度)
    west: float = 113.7
    east: float = 114.5
    south: float = 22.4
    north: float = 23.5

    # 中心点
    center_lon: float = 114.1
    center_lat: float = 22.95

    # 要生成的层级 (1-10)
    levels: list = field(default_factory=lambda: [1, 2, 3, 4, 5, 6, 7])

    # 输出
    output_dir: str = DEFAULT_OUTPUT_DIR
    obj_pattern: str = "beidou_3d_level_{level}"

    # 高度设置
    h_min: float = 0.0
    h_max: float = 1000.0

    # 坐标系
    source_crs: str = "EPSG:4326"
    target_crs: str = "EPSG:4547"

    # MTL 材质 — 颜色 (0.0 ~ 1.0)
    mtl_ka_r: float = 0.1
    mtl_ka_g: float = 0.1
    mtl_ka_b: float = 0.3
    mtl_kd_r: float = 0.3
    mtl_kd_g: float = 0.5
    mtl_kd_b: float = 0.9
    mtl_ks_r: float = 0.1
    mtl_ks_g: float = 0.1
    mtl_ks_b: float = 0.1

    # MTL 材质 — 其他
    mtl_ns: float = 30.0
    mtl_d: float = 0.3
    mtl_illum: int = 2

    @property
    def mtl_ka(self) -> tuple:
        return (self.mtl_ka_r, self.mtl_ka_g, self.mtl_ka_b)

    @property
    def mtl_kd(self) -> tuple:
        return (self.mtl_kd_r, self.mtl_kd_g, self.mtl_kd_b)

    @property
    def mtl_ks(self) -> tuple:
        return (self.mtl_ks_r, self.mtl_ks_g, self.mtl_ks_b)

    def get_height_resolution(self, level: int) -> float:
        """获取指定层级的高度分辨率"""
        return HEIGHT_RESOLUTIONS.get(level, 1.0)

    def get_height_layers(self, level: int) -> list:
        """计算指定层级的高度层列表 [(h_bottom, h_top), ...]，无上限限制"""
        import math

        h_res = self.get_height_resolution(level)
        if h_res >= self.h_max:
            return [(self.h_min, self.h_max)]

        num_layers = int(math.ceil((self.h_max - self.h_min) / h_res))

        layers = []
        for i in range(num_layers):
            h_bottom = self.h_min + i * h_res
            h_top = h_bottom + h_res
            if h_bottom >= self.h_max:
                break
            layers.append((h_bottom, min(h_top, self.h_max)))
        return layers

    def validate(self) -> list[str]:
        """验证配置，返回错误信息列表"""
        errors = []

        # 经纬度范围
        if not (-180 <= self.west < self.east <= 180):
            errors.append(f"经度范围无效: {self.west} ~ {self.east}")
        if not (-90 <= self.south < self.north <= 90):
            errors.append(f"纬度范围无效: {self.south} ~ {self.north}")
        if not (self.west <= self.center_lon <= self.east):
            errors.append(f"中心经度 {self.center_lon} 不在范围内")
        if not (self.south <= self.center_lat <= self.north):
            errors.append(f"中心纬度 {self.center_lat} 不在范围内")

        # 层级
        if not self.levels:
            errors.append("至少选择一个生成层级")
        for lvl in self.levels:
            if lvl not in range(1, 11):
                errors.append(f"无效层级: {lvl}（仅支持 1-10）")

        # 高度
        if self.h_min >= self.h_max:
            errors.append(f"高度范围无效: {self.h_min} ~ {self.h_max}（需 h_min < h_max）")

        # CRS
        if not self.source_crs or not self.target_crs:
            errors.append("源/目标 CRS 不能为空")

        # MTL 颜色
        for name, val in [("Ka_R", self.mtl_ka_r), ("Ka_G", self.mtl_ka_g), ("Ka_B", self.mtl_ka_b),
                          ("Kd_R", self.mtl_kd_r), ("Kd_G", self.mtl_kd_g), ("Kd_B", self.mtl_kd_b),
                          ("Ks_R", self.mtl_ks_r), ("Ks_G", self.mtl_ks_g), ("Ks_B", self.mtl_ks_b)]:
            if not (0.0 <= val <= 1.0):
                errors.append(f"MTL {name}={val} 需在 0.0~1.0 之间")
        if not (0.0 <= self.mtl_d <= 1.0):
            errors.append(f"MTL 不透明度 d={self.mtl_d} 需在 0.0~1.0 之间")

        # 文件名模板
        if "{level}" not in self.obj_pattern:
            errors.append(f"OBJ 文件名模板需包含 {{level}} 占位符")

        return errors

    def to_dict(self) -> dict:
        """序列化"""
        d = asdict(self)
        d["levels"] = ",".join(str(l) for l in self.levels)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "BeiDou3DConfig":
        """反序列化"""
        d = dict(d)
        if "levels" in d and isinstance(d["levels"], str):
            d["levels"] = [int(l) for l in d["levels"].split(",") if l.strip()]
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def estimate_3d_cells(self) -> dict[int, int]:
        """预估各级的3D网格数（全地理范围）"""
        estimates = {}
        for level in self.levels:
            cell_lon, cell_lat = LEVEL_SIZES[level]
            lon_range = self.east - self.west
            lat_range = self.north - self.south
            cols = max(1, int(lon_range / cell_lon))
            rows = max(1, int(lat_range / cell_lat))
            h_layers = len(self.get_height_layers(level))
            estimates[level] = cols * rows * h_layers
        return estimates
