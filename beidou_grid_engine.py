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
# Level 2 行字符集: 0-7 (8个值)
L2_ROW_CHARS = list("01234567")

# Level 4 列字符集: 0-9, A-E (15个值)
L4_COL_CHARS = list("0123456789ABCDE")
# Level 4 行字符集: 0-9 (10个值)
L4_ROW_CHARS = list("0123456789")

# Level 5 列/行字符集: 0-9, A-E (15个值)
L5_CHARS = list("0123456789ABCDE")

# Level 6 列/行字符集: 0-1 (2个值)
L6_CHARS = list("01")

# Level 7-10 列/行字符集: 0-7 (8个值)，延续 8×8 细分模式
L7_CHARS = list("01234567")
L8_CHARS = list("01234567")
L9_CHARS = list("01234567")
L10_CHARS = list("01234567")


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
    """Level 6 编码: 列(0-1) + 行(0-1) = 2字符"""
    return f"{L6_CHARS[col]}{L6_CHARS[row]}"


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
    # 各级编码字符集的反向映射
    charsets = {
        5: (L5_CHARS, L5_CHARS),       # col: 0-9,A-E, row: 0-9,A-E
        6: (L6_CHARS, L6_CHARS),       # col: 0-1, row: 0-1
        7: (L7_CHARS, L7_CHARS),       # col: 0-7, row: 0-7
        8: (L8_CHARS, L8_CHARS),       # col: 0-7, row: 0-7
        9: (L9_CHARS, L9_CHARS),       # col: 0-7, row: 0-7
        10: (L10_CHARS, L10_CHARS),    # col: 0-7, row: 0-7
    }
    # 各级编码在完整code中的起始位置
    level_offsets = {5: 9, 6: 11, 7: 13, 8: 15, 9: 17, 10: 19}

    offset = level_offsets[level]
    col_char = code[offset]
    row_char = code[offset + 1]

    col_charset, row_charset = charsets[level]
    col_idx = col_charset.index(col_char)
    row_idx = row_charset.index(row_char)

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

    records = []

    for _, parent in parent_gdf.iterrows():
        p_west = parent["west"]
        p_south = parent["south"]
        p_code = parent["grid_code"]

        for col in range(num_cols):
            child_w = p_west + col * cell_lon
            child_e = child_w + cell_lon

            # 快速跳过超范围的列
            if child_e <= bounds_w or child_w >= bounds_e:
                continue

            for row in range(num_rows):
                child_s = p_south + row * cell_lat
                child_n = child_s + cell_lat

                # 快速跳过超范围的行
                if child_n <= bounds_s or child_s >= bounds_n:
                    continue

                child_code = p_code + encode_fn(col, row)
                geom = box(child_w, child_s, child_e, child_n)

                records.append({
                    "grid_code": child_code,
                    "level": level,
                    "col_idx": col,
                    "row_idx": row,
                    "west": child_w,
                    "east": child_e,
                    "south": child_s,
                    "north": child_n,
                    "parent_code": p_code,
                    "geometry": geom,
                })

    return gpd.GeoDataFrame(records, crs="EPSG:4326") if records else gpd.GeoDataFrame(
        columns=["grid_code", "level", "col_idx", "row_idx",
                 "west", "east", "south", "north", "parent_code", "geometry"],
        geometry="geometry",
        crs="EPSG:4326"
    )


def generate_high_level(level, config, bounds):
    """
    高级别网格独立生成（Level 5-10）。
    直接从指定范围遍历生成，不依赖逐级父子遍历以节省内存。
    bounds: (west, east, south, north)
    """
    bounds_w, bounds_e, bounds_s, bounds_n = bounds
    cell_lon, cell_lat = LEVEL_SIZES[level]

    records = []

    # 从范围左下角开始，逐个生成网格
    lon = bounds_w
    while lon < bounds_e:
        lat = bounds_s
        while lat < bounds_n:
            # 使用网格中心点计算完整编码
            center_lon = lon + cell_lon / 2
            center_lat = lat + cell_lat / 2

            code, g_w, g_e, g_s, g_n = compute_full_code(center_lon, center_lat, level)

            geom = box(g_w, g_s, g_e, g_n)

            # 确定父编码
            parent_code = code[:-2] if level > 3 else code[:-1]

            # 从编码提取当前级别的col和row
            col_idx, row_idx = _extract_col_row_from_code(code, level)

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
                "geometry": geom,
            })

            lat += cell_lat

        lon += cell_lon

    # 去除重复编码（边界处可能重复）
    df = pd.DataFrame(records)
    if not df.empty:
        df = df.drop_duplicates(subset=["grid_code"])

    return gpd.GeoDataFrame(df, crs="EPSG:4326", geometry="geometry") if not df.empty else gpd.GeoDataFrame(
        columns=["grid_code", "level", "col_idx", "row_idx",
                 "west", "east", "south", "north", "parent_code", "geometry"],
        geometry="geometry",
        crs="EPSG:4326"
    )


# ============================================================
# 写入 SpatiaLite
# ============================================================

def write_to_spatialite(gdfs, config):
    """将所有级别的 GeoDataFrame 写入 SpatiaLite 数据库"""
    output_path = os.path.join(config.output_dir, config.output_db_name)

    # 删除已有文件
    if os.path.exists(output_path):
        os.remove(output_path)

    for level, gdf in gdfs.items():
        layer_name = f"grid_level_{level}"
        print(f"  写入图层 {layer_name}: {len(gdf)} 个网格...")

        if gdf.empty:
            print(f"  [警告] Level {level} 无数据，跳过")
            continue

        # 确保类型正确
        gdf = gdf.copy()
        gdf["level"] = gdf["level"].astype(int)
        gdf["col_idx"] = gdf["col_idx"].astype(int)
        gdf["row_idx"] = gdf["row_idx"].astype(int)

        if not os.path.exists(output_path):
            # 第一个图层: 创建新文件
            gdf.to_file(output_path, driver="SQLite", layer=layer_name, SPATIALITE="YES")
        else:
            # 后续图层: 追加到已有文件
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
    n_phases = len(levels) + 1  # 每层级一个阶段 + 写入

    # 内部存储所有已生成的层（包括中间层）
    all_gdfs = {}
    # 用于追踪 config.levels 的进度
    phase_idx = 0

    for level in range(1, max_level + 1):
        # ---- 取消检查 ----
        if stop_event is not None and stop_event.is_set():
            break

        # ---- 计算生成范围 ----
        bounds = get_generation_bounds(level, config)

        # ---- 生成网格 ----
        if level == 1:
            gdf = generate_level1(config, bounds)
        elif level <= 4:
            parent_gdf = all_gdfs[level - 1]
            gdf = generate_level_n(parent_gdf, level, config, bounds)
        else:
            gdf = generate_high_level(level, config, bounds)

        all_gdfs[level] = gdf

        # ---- 进度报告（仅对 config.levels 中的层级） ----
        if level in config.levels and progress_callback is not None:
            percent = int((phase_idx + 1) / n_phases * 100)
            size_label = LEVEL_LABELS.get(level, "")
            progress_callback(percent, f"生成 Level {level}: {len(gdf)} 个网格...")
            phase_idx += 1

    # ---- 筛选结果 ----
    result = {k: v for k, v in all_gdfs.items() if k in config.levels}

    if not result:
        return result

    # ---- 再次取消检查 ----
    if stop_event is not None and stop_event.is_set():
        return result

    # ---- 写入 SpatiaLite ----
    write_to_spatialite(result, config)

    if progress_callback is not None:
        progress_callback(100, "写入 SpatiaLite 完成")

    return result


# ============================================================
# 命令行入口（兼容旧的独立运行方式）
# ============================================================

if __name__ == "__main__":
    from beidou_params import BeiDou2DConfig

    config = BeiDou2DConfig()
    config.levels = [1, 2, 3, 4, 5, 6, 7]

    print("=" * 60)
    print("北斗二维网格位置码 SpatiaLite 数据库生成（引擎模式）")
    print("标准: GB/T 39409-2020")
    print(f"区域: {config.west}-{config.east}E, {config.south}-{config.north}N")
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
        count = len(result[level])
        code_len = LEVEL_CODE_LENGTHS.get(level, "?")
        size_label = LEVEL_LABELS.get(level, "?")
        print(f"  {level:<4}{count:<10}{str(code_len):<10}{size_label}")

    # 打印编码示例
    print(f"\n编码示例:")
    for level in sorted(result.keys()):
        if not result[level].empty:
            sample = result[level].iloc[0]
            print(f"  Level {level}: {sample['grid_code']}")

    output_path = os.path.join(config.output_dir, config.output_db_name)
    print(f"\n完成! 数据库已保存至: {output_path}")
    if os.path.exists(output_path):
        print(f"文件大小: {os.path.getsize(output_path) / 1024 / 1024:.2f} MB")
