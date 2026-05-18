"""
北斗二维网格位置码网格引擎 — 可参数化的生成核心
基于 GB/T 39409-2020《北斗网格位置码》国家标准

将所有编码函数与生成逻辑从 generate_beidou_grid.py 中提取出来，
接受 beidou_params.BeiDou2DConfig 对象控制所有参数。
支持进度回调和取消（通过 threading.Event）。
不依赖 PySide6。
"""

import math
import os
import threading

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from beidou_params import (
    BeiDou2DConfig,
    LEVEL_SIZES,
    LEVEL_SUBDIVISIONS,
    LEVEL_LABELS,
    LEVEL_CODE_LENGTHS,
)


# ============================================================
# 编码字符集 — 模块级常量（不随配置变化）
# ============================================================

# Level 2 列字符集: 0-9, A, B (12个值)
L2_COL_CHARS = list("0123456789AB")
L2_COL_MAP = {c: i for i, c in enumerate(L2_COL_CHARS)}
# Level 2 行字符集: 0-7 (8个值)
L2_ROW_CHARS = list("01234567")
L2_ROW_MAP = {c: i for i, c in enumerate(L2_ROW_CHARS)}

# Level 4 列字符集: 0-9, A-E (15个值)
L4_COL_CHARS = list("0123456789ABCDE")
L4_COL_MAP = {c: i for i, c in enumerate(L4_COL_CHARS)}
# Level 4 行字符集: 0-9 (10个值)
L4_ROW_CHARS = list("0123456789")
L4_ROW_MAP = {c: i for i, c in enumerate(L4_ROW_CHARS)}

# Level 5 列/行字符集: 0-9, A-E (15个值)
L5_CHARS = list("0123456789ABCDE")
L5_MAP = {c: i for i, c in enumerate(L5_CHARS)}

# Level 7-10 列/行字符集: 0-7 (8个值)，延续 8×8 细分模式
L7_CHARS = list("01234567")
L7_MAP = {c: i for i, c in enumerate(L7_CHARS)}
L8_CHARS = list("01234567")
L8_MAP = {c: i for i, c in enumerate(L8_CHARS)}
L9_CHARS = list("01234567")
L9_MAP = {c: i for i, c in enumerate(L9_CHARS)}
L10_CHARS = list("01234567")
L10_MAP = {c: i for i, c in enumerate(L10_CHARS)}


# ============================================================
# Level 1 编码: 半球(1) + 经度带(2) + 纬度带(1) = 4字符
# ============================================================

def encode_level1(lon_band, lat_band, hemisphere):
    """
    Level 1 编码: 半球(1) + 经度带(2) + 纬度带(1) = 4字符
    lon_band: 1-60
    lat_band: 0-21 (映射到A-V)
    hemisphere: 'N' or 'S'
    """
    lat_char = chr(ord('A') + lat_band)
    return f"{hemisphere}{lon_band:02d}{lat_char}"


# ============================================================
# Level 2-10 编码函数
# ============================================================

def encode_level2(col, row):
    """Level 2 编码: 列(0-11) + 行(0-7) = 2字符"""
    return f"{L2_COL_CHARS[col]}{L2_ROW_CHARS[row]}"


def encode_level3(col, row):
    """Level 3 编码: Z序编码 0-5, 在2列x3行网格中"""
    # Z序: code = row * 2 + col
    code = row * 2 + col
    return str(code)


def encode_level4(col, row):
    """Level 4 编码: 列(0-14) + 行(0-9) = 2字符"""
    return f"{L4_COL_CHARS[col]}{L4_ROW_CHARS[row]}"


def encode_level5(col, row):
    """Level 5 编码: 列(0-14) + 行(0-14) = 2字符"""
    return f"{L5_CHARS[col]}{L5_CHARS[row]}"


def encode_level6(col, row):
    """Level 6 编码: Z序编码 0-3, 在2列x2行网格中"""
    code = row * 2 + col
    return str(code)


def encode_level7(col, row):
    """Level 7 编码: 列(0-7) + 行(0-7) = 2字符"""
    return f"{L7_CHARS[col]}{L7_CHARS[row]}"


def encode_level8(col, row):
    """Level 8 编码: 列(0-7) + 行(0-7) = 2字符"""
    return f"{L8_CHARS[col]}{L8_CHARS[row]}"


def encode_level9(col, row):
    """Level 9 编码: 列(0-7) + 行(0-7) = 2字符"""
    return f"{L9_CHARS[col]}{L9_CHARS[row]}"


def encode_level10(col, row):
    """Level 10 编码: 列(0-7) + 行(0-7) = 2字符"""
    return f"{L10_CHARS[col]}{L10_CHARS[row]}"


# ============================================================
# Level 1 相关计算
# ============================================================

def get_l1_params(lon, lat):
    """根据经纬度计算 Level 1 参数"""
    hemisphere = 'N' if lat >= 0 else 'S'
    abs_lat = abs(lat)

    # 经度带号: 1-60, 从180degW开始每6deg一个带
    lon_band = int(math.floor((lon + 180) / 6)) + 1
    if lon_band > 60:
        lon_band = 60

    # 纬度带号: 0-21 (A-V), 从赤道开始每4deg一个带
    lat_band = int(math.floor(abs_lat / 4))
    if lat_band > 21:
        lat_band = 21

    return hemisphere, lon_band, lat_band


def get_l1_bounds(hemisphere, lon_band, lat_band):
    """计算 Level 1 网格的地理边界"""
    west = (lon_band - 1) * 6 - 180
    east = west + 6
    south = lat_band * 4
    north = south + 4
    if hemisphere == 'S':
        south, north = -north, -south
    return west, east, south, north


# ============================================================
# 生成范围计算（参数化）
# ============================================================

def get_generation_bounds(level, config):
    """
    计算生成范围 — 全部级别使用完整地理区域，不做缩减。
    """
    return config.west, config.east, config.south, config.north


# ============================================================
# 完整编码计算
# ============================================================

def compute_full_code(lon, lat, level):
    """
    根据经纬度和目标级别计算完整的北斗网格编码。
    返回 (code, west, east, south, north) - 编码及该网格的边界。
    """
    hemisphere, lon_band, lat_band = get_l1_params(lon, lat)

    # Level 1
    code = encode_level1(lon_band, lat_band, hemisphere)
    l1_w, l1_e, l1_s, l1_n = get_l1_bounds(hemisphere, lon_band, lat_band)

    if level == 1:
        return code, l1_w, l1_e, l1_s, l1_n

    # Level 2
    l2_col = int(math.floor((lon - l1_w) / LEVEL_SIZES[2][0]))
    l2_row = int(math.floor((lat - l1_s) / LEVEL_SIZES[2][1]))
    l2_col = min(l2_col, 11)
    l2_row = min(l2_row, 7)
    code += encode_level2(l2_col, l2_row)
    l2_w = l1_w + l2_col * LEVEL_SIZES[2][0]
    l2_s = l1_s + l2_row * LEVEL_SIZES[2][1]

    if level == 2:
        return code, l2_w, l2_w + LEVEL_SIZES[2][0], l2_s, l2_s + LEVEL_SIZES[2][1]

    # Level 3
    l3_col = int(math.floor((lon - l2_w) / LEVEL_SIZES[3][0]))
    l3_row = int(math.floor((lat - l2_s) / LEVEL_SIZES[3][1]))
    l3_col = min(l3_col, 1)
    l3_row = min(l3_row, 2)
    code += encode_level3(l3_col, l3_row)
    l3_w = l2_w + l3_col * LEVEL_SIZES[3][0]
    l3_s = l2_s + l3_row * LEVEL_SIZES[3][1]

    if level == 3:
        return code, l3_w, l3_w + LEVEL_SIZES[3][0], l3_s, l3_s + LEVEL_SIZES[3][1]

    # Level 4
    l4_col = int(math.floor((lon - l3_w) / LEVEL_SIZES[4][0]))
    l4_row = int(math.floor((lat - l3_s) / LEVEL_SIZES[4][1]))
    l4_col = min(l4_col, 14)
    l4_row = min(l4_row, 9)
    code += encode_level4(l4_col, l4_row)
    l4_w = l3_w + l4_col * LEVEL_SIZES[4][0]
    l4_s = l3_s + l4_row * LEVEL_SIZES[4][1]

    if level == 4:
        return code, l4_w, l4_w + LEVEL_SIZES[4][0], l4_s, l4_s + LEVEL_SIZES[4][1]

    # Level 5
    l5_col = int(math.floor((lon - l4_w) / LEVEL_SIZES[5][0]))
    l5_row = int(math.floor((lat - l4_s) / LEVEL_SIZES[5][1]))
    l5_col = min(l5_col, 14)
    l5_row = min(l5_row, 14)
    code += encode_level5(l5_col, l5_row)
    l5_w = l4_w + l5_col * LEVEL_SIZES[5][0]
    l5_s = l4_s + l5_row * LEVEL_SIZES[5][1]

    if level == 5:
        return code, l5_w, l5_w + LEVEL_SIZES[5][0], l5_s, l5_s + LEVEL_SIZES[5][1]

    # Level 6
    l6_col = int(math.floor((lon - l5_w) / LEVEL_SIZES[6][0]))
    l6_row = int(math.floor((lat - l5_s) / LEVEL_SIZES[6][1]))
    l6_col = min(l6_col, 1)
    l6_row = min(l6_row, 1)
    code += encode_level6(l6_col, l6_row)
    l6_w = l5_w + l6_col * LEVEL_SIZES[6][0]
    l6_s = l5_s + l6_row * LEVEL_SIZES[6][1]

    if level == 6:
        return code, l6_w, l6_w + LEVEL_SIZES[6][0], l6_s, l6_s + LEVEL_SIZES[6][1]

    # Level 7
    l7_col = int(math.floor((lon - l6_w) / LEVEL_SIZES[7][0]))
    l7_row = int(math.floor((lat - l6_s) / LEVEL_SIZES[7][1]))
    l7_col = min(l7_col, 7)
    l7_row = min(l7_row, 7)
    code += encode_level7(l7_col, l7_row)
    l7_w = l6_w + l7_col * LEVEL_SIZES[7][0]
    l7_s = l6_s + l7_row * LEVEL_SIZES[7][1]

    if level == 7:
        return code, l7_w, l7_w + LEVEL_SIZES[7][0], l7_s, l7_s + LEVEL_SIZES[7][1]

    # Level 8
    l8_col = int(math.floor((lon - l7_w) / LEVEL_SIZES[8][0]))
    l8_row = int(math.floor((lat - l7_s) / LEVEL_SIZES[8][1]))
    l8_col = min(l8_col, 7)
    l8_row = min(l8_row, 7)
    code += encode_level8(l8_col, l8_row)
    l8_w = l7_w + l8_col * LEVEL_SIZES[8][0]
    l8_s = l7_s + l8_row * LEVEL_SIZES[8][1]

    if level == 8:
        return code, l8_w, l8_w + LEVEL_SIZES[8][0], l8_s, l8_s + LEVEL_SIZES[8][1]

    # Level 9
    l9_col = int(math.floor((lon - l8_w) / LEVEL_SIZES[9][0]))
    l9_row = int(math.floor((lat - l8_s) / LEVEL_SIZES[9][1]))
    l9_col = min(l9_col, 7)
    l9_row = min(l9_row, 7)
    code += encode_level9(l9_col, l9_row)
    l9_w = l8_w + l9_col * LEVEL_SIZES[9][0]
    l9_s = l8_s + l9_row * LEVEL_SIZES[9][1]

    if level == 9:
        return code, l9_w, l9_w + LEVEL_SIZES[9][0], l9_s, l9_s + LEVEL_SIZES[9][1]

    # Level 10
    l10_col = int(math.floor((lon - l9_w) / LEVEL_SIZES[10][0]))
    l10_row = int(math.floor((lat - l9_s) / LEVEL_SIZES[10][1]))
    l10_col = min(l10_col, 7)
    l10_row = min(l10_row, 7)
    code += encode_level10(l10_col, l10_row)
    l10_w = l9_w + l10_col * LEVEL_SIZES[10][0]
    l10_s = l9_s + l10_row * LEVEL_SIZES[10][1]

    return code, l10_w, l10_w + LEVEL_SIZES[10][0], l10_s, l10_s + LEVEL_SIZES[10][1]


# ============================================================
# 从编码提取 col/row
# ============================================================

def _extract_col_row_from_code(code, level):
    """从编码中提取当前级别的col和row索引"""
    # L6 使用1位Z序编码，特殊处理
    if level == 6:
        offset = 11
        code_val = int(code[offset])
        col_idx = code_val % 2
        row_idx = code_val // 2
        return col_idx, row_idx

    # 各级编码字符集的反向映射 (char → index, O(1) 查找)
    charsets = {
        5: (L5_MAP, L5_MAP),
        7: (L7_MAP, L7_MAP),
        8: (L8_MAP, L8_MAP),
        9: (L9_MAP, L9_MAP),
        10: (L10_MAP, L10_MAP),
    }
    # 各级编码在完整code中的起始位置（L6为1位Z序，影响后续偏移）
    level_offsets = {5: 9, 7: 12, 8: 14, 9: 16, 10: 18}

    offset = level_offsets[level]
    col_char = code[offset]
    row_char = code[offset + 1]

    col_map, row_map = charsets[level]
    col_idx = col_map[col_char]
    row_idx = row_map[row_char]

    return col_idx, row_idx


# ============================================================
# 网格生成函数
# ============================================================

def generate_level1(config, bounds):
    """
    生成 Level 1 网格数据。
    bounds: (west, east, south, north)
    """
    bounds_w, bounds_e, bounds_s, bounds_n = bounds
    records = []

    # 确定覆盖范围的经度带和纬度带
    for lon_band in range(1, 61):
        l1_w = (lon_band - 1) * 6 - 180
        l1_e = l1_w + 6
        if l1_e <= bounds_w or l1_w >= bounds_e:
            continue

        for hemisphere in ['N', 'S']:
            for lat_band in range(22):
                l1_s = lat_band * 4
                l1_n = l1_s + 4
                if hemisphere == 'S':
                    actual_s, actual_n = -l1_n, -l1_s
                else:
                    actual_s, actual_n = l1_s, l1_n

                if actual_n <= bounds_s or actual_s >= bounds_n:
                    continue

                code = encode_level1(lon_band, lat_band, hemisphere)
                geom = box(l1_w, actual_s, l1_e, actual_n)
                records.append({
                    "grid_code": code,
                    "level": 1,
                    "col_idx": lon_band,
                    "row_idx": lat_band,
                    "west": float(l1_w),
                    "east": float(l1_e),
                    "south": float(actual_s),
                    "north": float(actual_n),
                    "parent_code": None,
                    "geometry": geom,
                })

    return gpd.GeoDataFrame(records, crs="EPSG:4326")


def generate_level_n(parent_gdf, level, config, bounds):
    """
    通用的子级网格生成函数（Level 2-10）。
    在每个父网格内按指定的列行数细分，过滤超出范围的子网格。
    使用 numpy 预计算坐标并批量过滤，减少逐格边界检查开销。
    bounds: (west, east, south, north)
    """
    bounds_w, bounds_e, bounds_s, bounds_n = bounds
    num_cols, num_rows = LEVEL_SUBDIVISIONS[level]
    cell_lon, cell_lat = LEVEL_SIZES[level]

    encode_funcs = {
        2: encode_level2,
        3: encode_level3,
        4: encode_level4,
        5: encode_level5,
        6: encode_level6,
        7: encode_level7,
        8: encode_level8,
        9: encode_level9,
        10: encode_level10,
    }
    encode_fn = encode_funcs[level]

    # 预计算行列偏移数组
    col_indices = np.arange(num_cols, dtype=np.int32)
    row_indices = np.arange(num_rows, dtype=np.int32)
    col_offsets = col_indices * cell_lon
    row_offsets = row_indices * cell_lat

    records = []

    for _, parent in parent_gdf.iterrows():
        p_west = parent["west"]
        p_south = parent["south"]
        p_code = parent["grid_code"]

        # 批量计算所有子格的东西/南北边界
        child_west_all = p_west + col_offsets
        child_east_all = child_west_all + cell_lon
        child_south_all = p_south + row_offsets
        child_north_all = child_south_all + cell_lat

        # 布尔掩码过滤超出范围的列和行
        valid_col_mask = (child_east_all > bounds_w) & (child_west_all < bounds_e)
        valid_row_mask = (child_north_all > bounds_s) & (child_south_all < bounds_n)

        valid_cols = col_indices[valid_col_mask]
        valid_rows = row_indices[valid_row_mask]

        if len(valid_cols) == 0 or len(valid_rows) == 0:
            continue

        # 列表推导批量生成子格记录
        records.extend([
            {
                "grid_code": p_code + encode_fn(int(c), int(r)),
                "level": level,
                "col_idx": int(c),
                "row_idx": int(r),
                "west": float(p_west + c * cell_lon),
                "east": float(p_west + c * cell_lon + cell_lon),
                "south": float(p_south + r * cell_lat),
                "north": float(p_south + r * cell_lat + cell_lat),
                "parent_code": p_code,
                "geometry": box(
                    float(p_west + c * cell_lon),
                    float(p_south + r * cell_lat),
                    float(p_west + c * cell_lon + cell_lon),
                    float(p_south + r * cell_lat + cell_lat),
                ),
            }
            for c in valid_cols
            for r in valid_rows
        ])

    if not records:
        return gpd.GeoDataFrame(
            columns=["grid_code", "level", "col_idx", "row_idx",
                     "west", "east", "south", "north", "parent_code", "geometry"],
            geometry="geometry",
            crs="EPSG:4326"
        )

    return gpd.GeoDataFrame(records, crs="EPSG:4326")


def generate_high_level(level, config, bounds):
    """
    高级别网格独立生成（Level 5-10），无 L6 父网格时使用。
    使用网格对齐的整数循环，set O(1) 去重，避免浮点累积误差。
    bounds: (west, east, south, north)
    """
    bounds_w, bounds_e, bounds_s, bounds_n = bounds
    cell_lon, cell_lat = LEVEL_SIZES[level]

    # 从范围左下角第一个网格中心点获取对齐原点
    first_center_lon = bounds_w + cell_lon / 2
    first_center_lat = bounds_s + cell_lat / 2
    _, origin_w, _, origin_s, _ = compute_full_code(first_center_lon, first_center_lat, level)

    num_cols = int((bounds_e - origin_w) / cell_lon) + 1
    num_rows = int((bounds_n - origin_s) / cell_lat) + 1

    seen_codes = set()
    records = []

    encode_fn = {
        5: encode_level5, 6: encode_level6, 7: encode_level7,
        8: encode_level8, 9: encode_level9, 10: encode_level10,
    }[level]

    for col in range(num_cols):
        w = origin_w + col * cell_lon
        if w >= bounds_e:
            break
        e = w + cell_lon

        for row in range(num_rows):
            s = origin_s + row * cell_lat
            if s >= bounds_n:
                break

            center_lon = w + cell_lon / 2
            center_lat = s + cell_lat / 2
            code, g_w, g_e, g_s, g_n = compute_full_code(center_lon, center_lat, level)

            if code in seen_codes:
                continue
            seen_codes.add(code)

            col_idx, row_idx = _extract_col_row_from_code(code, level)
            parent_code = code[:LEVEL_CODE_LENGTHS[level - 1]] if level > 1 else None

            records.append({
                "grid_code": code,
                "level": level,
                "col_idx": col_idx,
                "row_idx": row_idx,
                "west": g_w,
                "east": g_e,
                "south": g_s,
                "north": g_n,
                "parent_code": parent_code,
                "geometry": box(g_w, g_s, g_e, g_n),
            })

    if not records:
        return gpd.GeoDataFrame(
            columns=["grid_code", "level", "col_idx", "row_idx",
                     "west", "east", "south", "north", "parent_code", "geometry"],
            geometry="geometry", crs="EPSG:4326"
        )

    return gpd.GeoDataFrame(records, crs="EPSG:4326")


def _get_pg_engine(config):
    """创建 SQLAlchemy PostGIS 引擎（调用方负责 dispose）"""
    from sqlalchemy import create_engine
    from urllib.parse import quote_plus
    encoded_user = quote_plus(config.pg_user)
    encoded_pwd = quote_plus(config.pg_password)
    conn_str = (
        f"postgresql://{encoded_user}:{encoded_pwd}"
        f"@{config.pg_host}:{config.pg_port}/{config.pg_database}"
    )
    return create_engine(conn_str)


def _write_gdf_to_postgis(gdf, engine, table_name, schema, if_exists="replace"):
    """将单个 GeoDataFrame 写入 PostGIS"""
    if gdf.empty:
        return
    gdf = gdf.copy()
    gdf["level"] = gdf["level"].astype(int)
    gdf["col_idx"] = gdf["col_idx"].astype(int)
    gdf["row_idx"] = gdf["row_idx"].astype(int)
    gdf.to_postgis(
        table_name, engine, schema=schema,
        if_exists=if_exists, index=False,
    )


def write_to_postgis(gdfs, config, skip_levels=None):
    """将所有级别的 GeoDataFrame 写入 PostGIS 数据库"""
    engine = _get_pg_engine(config)
    skip_levels = skip_levels or set()

    try:
        for level, gdf in gdfs.items():
            if level in skip_levels:
                continue

            table_name = f"{config.pg_table_prefix}{level}"
            count = gdf.attrs.get("cell_count", len(gdf))
            print(f"  写入表 {config.pg_schema}.{table_name}: {count} 个网格...")

            if gdf.empty:
                print(f"  [警告] Level {level} 无数据，跳过")
                continue

            _write_gdf_to_postgis(gdf, engine, table_name, config.pg_schema)
    finally:
        engine.dispose()


def _write_gdf_to_spatialite(gdf, output_path, layer_name, is_first=False):
    """将 GeoDataFrame 写入 SpatiaLite（首次创建/后续追加）"""
    if gdf.empty:
        return
    gdf = gdf.copy()
    gdf["level"] = gdf["level"].astype(int)
    gdf["col_idx"] = gdf["col_idx"].astype(int)
    gdf["row_idx"] = gdf["row_idx"].astype(int)
    if is_first and (not os.path.exists(output_path)):
        gdf.to_file(output_path, driver="SQLite", layer=layer_name, SPATIALITE="YES")
    else:
        gdf.to_file(output_path, driver="SQLite", layer=layer_name, mode="a", SPATIALITE="YES")


def generate_high_level_chunked(level, config, bounds, l6_parent_gdf=None):
    """
    Level 7-10 分块流式生成：从 L6 父网格逐格细分至目标级别，
    分批写入 SpatiaLite 或 PostGIS，避免内存溢出。若 L6 不可用则回退到 generate_high_level。
    返回 (GeoDataFrame | None, cell_count)。
    """
    if l6_parent_gdf is None or l6_parent_gdf.empty:
        gdf = generate_high_level(level, config, bounds)
        return gdf, len(gdf)

    use_postgis = config.output_type == "postgis"
    table_name = f"{config.pg_table_prefix}{level}"
    layer_name = f"grid_level_{level}"
    output_path = os.path.join(config.output_dir, config.output_db_name)
    bounds_w, bounds_e, bounds_s, bounds_n = bounds

    # PostGIS 引擎（一次创建，复用）
    pg_engine = None
    if use_postgis:
        pg_engine = _get_pg_engine(config)

    WRITE_BATCH = 100000
    PARENT_CHUNK = 100
    batch_records = []
    total_count = 0
    is_first_write = True

    try:
        n_l6 = len(l6_parent_gdf)
        for start in range(0, n_l6, PARENT_CHUNK):
            end = min(start + PARENT_CHUNK, n_l6)
            chunk = l6_parent_gdf.iloc[start:end]
            current_gdf = gpd.GeoDataFrame(chunk, crs="EPSG:4326")

            for sub_level in range(7, level + 1):
                if current_gdf.empty:
                    break
                current_gdf = generate_level_n(current_gdf, sub_level, config, bounds)
                if current_gdf.empty:
                    break

            if not current_gdf.empty:
                sub_records = current_gdf.to_dict("records")
                batch_records.extend(sub_records)
                total_count += len(sub_records)

            # 批次写入，释放内存
            if len(batch_records) >= WRITE_BATCH:
                batch_gdf = gpd.GeoDataFrame(batch_records, crs="EPSG:4326", geometry="geometry")
                if use_postgis:
                    _write_gdf_to_postgis(
                        batch_gdf, pg_engine, table_name, config.pg_schema,
                        if_exists="replace" if is_first_write else "append"
                    )
                else:
                    _write_gdf_to_spatialite(batch_gdf, output_path, layer_name, is_first_write)
                is_first_write = False
                batch_records.clear()

        # 写入剩余记录
        if batch_records:
            batch_gdf = gpd.GeoDataFrame(batch_records, crs="EPSG:4326", geometry="geometry")
            if use_postgis:
                _write_gdf_to_postgis(
                    batch_gdf, pg_engine, table_name, config.pg_schema,
                    if_exists="replace" if is_first_write else "append"
                )
            else:
                _write_gdf_to_spatialite(batch_gdf, output_path, layer_name, is_first_write)
            batch_records.clear()
    finally:
        if pg_engine is not None:
            pg_engine.dispose()

    # 返回空的占位 GeoDataFrame（数据已写入目标）
    result_gdf = gpd.GeoDataFrame(
        {"grid_code": [], "level": [], "col_idx": [], "row_idx": [],
         "west": [], "east": [], "south": [], "north": [],
         "parent_code": [], "geometry": []},
        geometry="geometry", crs="EPSG:4326"
    )
    return result_gdf, total_count


# ============================================================
# 写入 SpatiaLite
# ============================================================

def write_to_spatialite(gdfs, config, skip_levels=None):
    """将所有级别的 GeoDataFrame 写入 SpatiaLite 数据库。
    skip_levels: 已在流式生成中写入的级别集合，跳过不重复写入。
    """
    output_path = os.path.join(config.output_dir, config.output_db_name)
    skip_levels = skip_levels or set()
    streaming_done = bool(skip_levels)

    if not streaming_done and os.path.exists(output_path):
        os.remove(output_path)

    for level, gdf in gdfs.items():
        if level in skip_levels:
            continue

        layer_name = f"grid_level_{level}"
        print(f"  写入图层 {layer_name}: {len(gdf)} 个网格...")

        if gdf.empty:
            print(f"  [警告] Level {level} 无数据，跳过")
            continue

        gdf = gdf.copy()
        gdf["level"] = gdf["level"].astype(int)
        gdf["col_idx"] = gdf["col_idx"].astype(int)
        gdf["row_idx"] = gdf["row_idx"].astype(int)

        if not os.path.exists(output_path):
            gdf.to_file(output_path, driver="SQLite", layer=layer_name, SPATIALITE="YES")
        else:
            gdf.to_file(output_path, driver="SQLite", layer=layer_name, mode="a", SPATIALITE="YES")


# ============================================================
# 主入口函数
# ============================================================

def generate_2d_grid(config, progress_callback=None, stop_event=None):
    """
    根据配置生成北斗二维网格 1-10 级的完整空间数据。

    参数
    ----------
    config : BeiDou2DConfig
        包含所有范围、中心点、层级、输出路径等配置。
    progress_callback : callable | None
        签名 f(percent: int, message: str)，每完成一个层级调用一次。
    stop_event : threading.Event | None
        设置后，在下一个层级开始前停止生成并返回已完成的层级。

    返回
    ----------
    dict[int, GeoDataFrame]
        {level: GeoDataFrame}，仅包含 config.levels 中指定的层级。
    """
    levels = sorted(config.levels)
    if not levels:
        return {}

    max_level = max(levels)
    # 计算进度阶段数：每层级一个阶段 + 写入
    n_phases = len(levels) + 1

    # 内部存储所有已生成的层（包括中间层）
    all_gdfs = {}
    chunked_level_counts = {}  # 流式生成的级别 → 单元格数量
    phase_idx = 0

    for level in range(1, max_level + 1):
        # ---- 取消检查 ----
        if stop_event is not None and stop_event.is_set():
            break

        bounds = get_generation_bounds(level, config)

        # ---- 生成网格 ----
        if level == 1:
            gdf = generate_level1(config, bounds)
            all_gdfs[level] = gdf
            cell_count = len(gdf)
        elif level <= 6:
            # Level 2-6: 父子层级细分，避免逐格 compute_full_code
            parent_gdf = all_gdfs[level - 1]
            gdf = generate_level_n(parent_gdf, level, config, bounds)
            all_gdfs[level] = gdf
            cell_count = len(gdf)
        else:
            # Level 7-10: 流式分批写入 SpatiaLite
            gdf, cell_count = generate_high_level_chunked(
                level, config, bounds, all_gdfs.get(6)
            )
            all_gdfs[level] = gdf
            # 仅当GDF为空占位符时标记为已流式写入
            if cell_count > 0 and gdf.empty:
                chunked_level_counts[level] = cell_count

        # ---- 进度报告 ----
        if level in config.levels and progress_callback is not None:
            percent = int((phase_idx + 1) / n_phases * 100)
            size_label = LEVEL_LABELS.get(level, "")
            progress_callback(percent, f"生成 Level {level}: {cell_count} 个网格...")
            phase_idx += 1

    # ---- 筛选结果 ----
    result = {k: v for k, v in all_gdfs.items() if k in config.levels}

    # ---- 补充流式级别的计数 ----
    for lv, count in chunked_level_counts.items():
        if lv in result:
            result[lv].attrs["cell_count"] = count

    if not result:
        return result

    # ---- 取消检查 ----
    if stop_event is not None and stop_event.is_set():
        return result

    # ---- 写入输出（SpatiaLite 或 PostGIS） ----
    skip_set = set(chunked_level_counts.keys())
    if config.output_type == "postgis":
        write_to_postgis(result, config, skip_levels=skip_set)
        if progress_callback is not None:
            progress_callback(100, "写入 PostGIS 完成")
    else:
        write_to_spatialite(result, config, skip_levels=skip_set)
        if progress_callback is not None:
            progress_callback(100, "写入 SpatiaLite 完成")

    return result


def test_postgis_connection(config) -> tuple[bool, str]:
    """测试 PostGIS 数据库连接。
    先验证 PostgreSQL 连通性，再检测 PostGIS 扩展是否安装。
    返回 (ok: bool, message: str)
    """
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        return False, "缺少 SQLAlchemy 依赖，请安装: pip install sqlalchemy psycopg2-binary"

    engine = None
    try:
        engine = _get_pg_engine(config)
        with engine.connect() as conn:
            # 1. 验证 PostgreSQL 版本
            result = conn.execute(text("SELECT version();"))
            pg_version = result.scalar()

            # 2. 检查 schema 是否存在
            schema_check = conn.execute(
                text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = :schema"),
                {"schema": config.pg_schema}
            ).scalar()
            if not schema_check:
                return False, (
                    f"Schema '{config.pg_schema}' 不存在。\n"
                    f"请在数据库中执行: CREATE SCHEMA {config.pg_schema};"
                )

            # 3. 检查 PostGIS 扩展
            ext_check = conn.execute(
                text(
                    "SELECT extname FROM pg_extension "
                    "WHERE extname = 'postgis' AND extnamespace = "
                    "(SELECT oid FROM pg_namespace WHERE nspname = :schema)"
                ),
                {"schema": config.pg_schema}
            ).scalar()
            if not ext_check:
                # 检查是否在 public schema 中
                ext_public = conn.execute(
                    text("SELECT extname FROM pg_extension WHERE extname = 'postgis'")
                ).scalar()
                if ext_public:
                    return True, f"PostgreSQL 连接成功，PostGIS 在 public schema 中已安装"
                return False, (
                    f"PostgreSQL 连接成功，但 PostGIS 扩展未安装。\n"
                    f"请在数据库中执行: CREATE EXTENSION postgis;"
                )

            # 4. PostGIS 版本
            pgis_version = conn.execute(text("SELECT PostGIS_version();")).scalar()
            return True, f"连接成功\nPostgreSQL: {pg_version[:40]}...\nPostGIS: {pgis_version}"
    except Exception as e:
        error_msg = str(e)
        if "password" in error_msg.lower():
            return False, f"认证失败: 用户名或密码错误"
        if "could not" in error_msg.lower() and "connect" in error_msg.lower():
            return False, f"无法连接到 {config.pg_host}:{config.pg_port}: {error_msg.split(chr(10))[0]}"
        return False, f"连接失败: {error_msg.split(chr(10))[0]}"
    finally:
        if engine is not None:
            engine.dispose()


# ============================================================
# 命令行入口（兼容旧的独立运行方式）
# ============================================================

if __name__ == "__main__":
    from beidou_params import BeiDou2DConfig

    config = BeiDou2DConfig()
    config.levels = [1, 2, 3, 4, 5, 6, 7]

    output_label = "PostGIS" if config.output_type == "postgis" else "SpatiaLite"
    print("=" * 60)
    print(f"北斗二维网格位置码 {output_label} 数据库生成（引擎模式）")
    print("标准: GB/T 39409-2020")
    print(f"区域: {config.west}-{config.east}E, {config.south}-{config.north}N")
    if config.output_type == "postgis":
        print(f"PostGIS: {config.pg_host}:{config.pg_port}/{config.pg_database} [{config.pg_schema}]")
    print("=" * 60)

    def progress(percent, message):
        print(f"  [{percent:3d}%] {message}")

    result = generate_2d_grid(config, progress_callback=progress)

    # 打印汇总
    print(f"\n{'=' * 60}")
    print("各级别网格汇总:")
    print(f"{'级别':<6}{'网格数':<10}{'编码长度':<10}{'网格尺寸'}")
    print("-" * 50)
    for level in sorted(result.keys()):
        gdf = result[level]
        # 流式写入的级别从 attrs 获取计数
        count = gdf.attrs.get("cell_count", len(gdf))
        code_len = LEVEL_CODE_LENGTHS.get(level, "?")
        size_label = LEVEL_LABELS.get(level, "?")
        print(f"  {level:<4}{count:<10}{str(code_len):<10}{size_label}")

    # 打印编码示例
    print(f"\n编码示例:")
    for level in sorted(result.keys()):
        if not result[level].empty:
            sample = result[level].iloc[0]
            print(f"  Level {level}: {sample['grid_code']}")
        elif result[level].attrs.get("cell_count", 0) > 0:
            print(f"  Level {level}: (数据已流式写入 SpatiaLite)")

    if config.output_type == "postgis":
        print(f"\n完成! 数据已写入 PostGIS: "
              f"{config.pg_host}:{config.pg_port}/{config.pg_database} [{config.pg_schema}]")
    else:
        output_path = os.path.join(config.output_dir, config.output_db_name)
        print(f"\n完成! 数据库已保存至: {output_path}")
        if os.path.exists(output_path):
            print(f"文件大小: {os.path.getsize(output_path) / 1024 / 1024:.2f} MB")
