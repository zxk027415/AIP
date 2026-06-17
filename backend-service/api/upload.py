# @AI_GENERATED: Kiro v1.0
"""
文件上传与数据分析 API
支持 CSV/Excel 文件上传，自动分析列信息并推荐时间列
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
import os
import uuid
import json
from datetime import datetime

router = APIRouter(prefix="/api/upload", tags=["upload"])

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _analyze_csv(file_path: str, delimiter: str = ",", encoding: str = "utf-8"):
    """分析 CSV 文件，返回列信息和推荐时间列"""
    import pandas as pd

    # 尝试多种编码
    encodings = [encoding, "utf-8", "gbk", "gb2312", "latin1"]
    df = None
    used_encoding = encoding
    for enc in encodings:
        try:
            df = pd.read_csv(file_path, delimiter=delimiter, encoding=enc, nrows=100)
            used_encoding = enc
            break
        except (UnicodeDecodeError, Exception):
            continue

    if df is None:
        raise ValueError("无法解析文件，请检查编码和分隔符")

    columns = []
    recommended_timestamp = None
    timestamp_score = {}

    for col in df.columns:
        col_info = {
            "name": str(col),
            "dtype": str(df[col].dtype),
            "non_null_count": int(df[col].notna().sum()),
            "total_count": len(df),
            "sample_values": [str(v) for v in df[col].dropna().head(5).tolist()],
            "is_numeric": bool(pd.api.types.is_numeric_dtype(df[col])),
            "is_datetime": False,
            "timestamp_likelihood": 0.0,
        }

        # 检测是否为时间列
        score = 0.0
        col_lower = str(col).lower()

        # 列名匹配
        time_keywords = ["time", "date", "timestamp", "datetime", "时间", "日期", "时刻"]
        for kw in time_keywords:
            if kw in col_lower:
                score += 0.5
                break

        # 尝试解析为时间
        if not pd.api.types.is_numeric_dtype(df[col]) or col_lower in ["time", "timestamp"]:
            try:
                parsed = pd.to_datetime(df[col].dropna().head(20), errors="coerce")
                valid_ratio = parsed.notna().sum() / max(len(parsed), 1)
                if valid_ratio > 0.8:
                    score += 0.4
                    col_info["is_datetime"] = True
            except Exception:
                pass

        # 如果是 object 类型且样本值看起来像日期
        if df[col].dtype == "object":
            samples = df[col].dropna().head(5).tolist()
            date_patterns = ["-", "/", ":", "T", "年", "月", "日"]
            for s in samples:
                s_str = str(s)
                if any(p in s_str for p in date_patterns) and len(s_str) >= 8:
                    score += 0.1
                    break

        col_info["timestamp_likelihood"] = round(score, 2)
        timestamp_score[str(col)] = score
        columns.append(col_info)

    # 推荐得分最高的列作为时间列
    if timestamp_score:
        best_col = max(timestamp_score, key=timestamp_score.get)
        if timestamp_score[best_col] >= 0.4:
            recommended_timestamp = best_col

    # 数值列列表
    numeric_columns = [c["name"] for c in columns if c["is_numeric"]]

    return {
        "columns": columns,
        "recommended_timestamp": recommended_timestamp,
        "numeric_columns": numeric_columns,
        "total_rows": int(len(df)),
        "encoding": used_encoding,
        "delimiter": delimiter,
    }


@router.post("/file", summary="上传文件并自动分析")
async def upload_file(file: UploadFile = File(...)):
    """
    上传 CSV/Excel 文件，自动分析列信息并推荐时间列

    返回:
    - file_id: 上传文件ID（用于后续引用）
    - filename: 原始文件名
    - file_size: 文件大小
    - analysis: 列分析结果（列名、类型、推荐时间列等）
    """
    # 验证文件类型
    allowed_extensions = {".csv", ".xlsx", ".xls", ".tsv"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(400, f"不支持的文件类型: {ext}，支持: {', '.join(allowed_extensions)}")

    # 生成唯一文件ID
    file_id = f"upload-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    save_filename = f"{file_id}{ext}"
    save_path = os.path.join(UPLOAD_DIR, save_filename)

    # 保存文件
    content = await file.read()
    file_size = len(content)
    if file_size > 100 * 1024 * 1024:  # 100MB limit
        raise HTTPException(400, "文件大小超过100MB限制")

    with open(save_path, "wb") as f:
        f.write(content)

    # 分析文件
    try:
        if ext in {".csv", ".tsv"}:
            delimiter = "\t" if ext == ".tsv" else ","
            analysis = _analyze_csv(save_path, delimiter=delimiter)
        elif ext in {".xlsx", ".xls"}:
            import pandas as pd
            df = pd.read_excel(save_path, nrows=100)
            # 保存为临时 CSV 再分析
            tmp_csv = save_path + ".tmp.csv"
            df.to_csv(tmp_csv, index=False)
            analysis = _analyze_csv(tmp_csv)
            os.remove(tmp_csv)
        else:
            analysis = {}
    except Exception as e:
        analysis = {"error": str(e)}

    # 保存元数据
    meta = {
        "file_id": file_id,
        "original_filename": file.filename,
        "save_path": save_path,
        "file_size": file_size,
        "extension": ext,
        "upload_time": datetime.now().isoformat(),
    }
    meta_path = os.path.join(UPLOAD_DIR, f"{file_id}.meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return {
        "file_id": file_id,
        "filename": file.filename,
        "file_size": file_size,
        "analysis": analysis,
    }


@router.get("/file/{file_id}/preview", summary="预览上传文件数据")
async def preview_file(file_id: str, rows: int = 10):
    """预览上传文件的前N行数据"""
    import pandas as pd

    meta_path = os.path.join(UPLOAD_DIR, f"{file_id}.meta.json")
    if not os.path.exists(meta_path):
        raise HTTPException(404, f"文件不存在: {file_id}")

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    file_path = meta["save_path"]
    ext = meta["extension"]

    try:
        if ext in {".csv", ".tsv"}:
            delimiter = "\t" if ext == ".tsv" else ","
            df = pd.read_csv(file_path, delimiter=delimiter, nrows=rows)
        else:
            df = pd.read_excel(file_path, nrows=rows)

        return {
            "columns": list(df.columns),
            "data": df.fillna("").to_dict(orient="records"),
            "total_preview_rows": len(df),
        }
    except Exception as e:
        raise HTTPException(500, f"预览失败: {str(e)}")
# @AI_GENERATED: end


# @AI_GENERATED: Kiro v1.0
# ============ 光伏示例数据 API ============

DEMO_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "demo")


@router.get("/demo/pv-power/stats", summary="获取光伏示例数据统计信息")
async def get_pv_demo_stats():
    """获取光伏发电功率预测示例数据的统计信息"""
    stats_path = os.path.join(DEMO_DIR, "pv_power_data_stats.json")
    if not os.path.exists(stats_path):
        raise HTTPException(404, "示例数据统计文件不存在")
    
    with open(stats_path, "r", encoding="utf-8") as f:
        stats = json.load(f)
    
    return stats


@router.get("/demo/pv-power/sample", summary="获取光伏示例数据样本")
async def get_pv_demo_sample(rows: int = 96):
    """
    获取光伏发电功率预测示例数据样本
    
    参数:
    - rows: 返回行数，默认96行（1天的数据）
    """
    sample_path = os.path.join(DEMO_DIR, "pv_power_sample.csv")
    if not os.path.exists(sample_path):
        raise HTTPException(404, "示例数据文件不存在")
    
    # 读取CSV文件
    data = []
    with open(sample_path, "r", encoding="utf-8") as f:
        import csv
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= rows:
                break
            # 转换数值类型
            data.append({
                "timestamp": row["timestamp"],
                "irradiance": float(row["irradiance"]),
                "temperature": float(row["temperature"]),
                "humidity": float(row["humidity"]),
                "wind_speed": float(row["wind_speed"]),
                "cloud_cover": float(row["cloud_cover"]),
                "power_actual": float(row["power_actual"])
            })
    
    return {
        "columns": ["timestamp", "irradiance", "temperature", "humidity", "wind_speed", "cloud_cover", "power_actual"],
        "data": data,
        "total_rows": len(data),
        "description": "光伏发电功率预测示例数据 - 宁夏银川10MW电站"
    }


@router.get("/demo/pv-power/chart-data", summary="获取光伏示例数据图表数据")
async def get_pv_demo_chart_data():
    """获取用于图表展示的光伏示例数据"""
    sample_path = os.path.join(DEMO_DIR, "pv_power_sample.csv")
    if not os.path.exists(sample_path):
        raise HTTPException(404, "示例数据文件不存在")
    
    timestamps = []
    irradiance = []
    temperature = []
    power = []
    
    with open(sample_path, "r", encoding="utf-8") as f:
        import csv
        reader = csv.DictReader(f)
        for row in reader:
            timestamps.append(row["timestamp"].split(" ")[1])  # 只取时间部分
            irradiance.append(float(row["irradiance"]))
            temperature.append(float(row["temperature"]))
            power.append(float(row["power_actual"]))
    
    return {
        "timestamps": timestamps,
        "series": {
            "irradiance": {
                "name": "辐照度",
                "unit": "W/m²",
                "data": irradiance
            },
            "temperature": {
                "name": "温度",
                "unit": "°C",
                "data": temperature
            },
            "power": {
                "name": "发电功率",
                "unit": "kW",
                "data": power
            }
        }
    }


@router.get("/demo/datasets", summary="获取所有示例数据集列表")
async def get_demo_datasets():
    """获取所有可用的示例数据集，包含详细的列配置信息"""
    return {
        "datasets": [
            {
                "id": "pv-power-yinchuan",
                "name": "光伏发电功率预测 - 宁夏银川",
                "scenario": "renewable-energy",
                "template": "pv_power_forecast",
                "description": "10MW光伏电站1年历史数据，包含气象特征和发电功率",
                "records": 35040,
                "features": ["irradiance", "temperature", "humidity", "wind_speed", "cloud_cover"],
                "target": "power_actual",
                "time_column": "timestamp",
                "interval": "15min",
                "date_range": "2025-01-01 ~ 2025-12-31",
                "available": True,
                "columns": [
                    {"name": "timestamp", "type": "datetime", "description": "时间戳"},
                    {"name": "irradiance", "type": "float", "unit": "W/m²", "description": "太阳辐照度"},
                    {"name": "temperature", "type": "float", "unit": "°C", "description": "环境温度"},
                    {"name": "humidity", "type": "float", "unit": "%", "description": "相对湿度"},
                    {"name": "wind_speed", "type": "float", "unit": "m/s", "description": "风速"},
                    {"name": "cloud_cover", "type": "float", "unit": "%", "description": "云量"},
                    {"name": "power_actual", "type": "float", "unit": "kW", "description": "实际发电功率"}
                ]
            },
            {
                "id": "wind-power-neimeng",
                "name": "风力发电功率预测 - 内蒙古",
                "scenario": "renewable-energy",
                "template": "wind_power_forecast",
                "description": "50MW风电场历史数据，包含风速、风向等气象特征",
                "records": 0,
                "features": ["wind_speed", "wind_direction", "temperature", "pressure"],
                "target": "power_actual",
                "time_column": "timestamp",
                "interval": "10min",
                "date_range": "-",
                "available": False,
                "columns": [
                    {"name": "timestamp", "type": "datetime", "description": "时间戳"},
                    {"name": "wind_speed", "type": "float", "unit": "m/s", "description": "风速"},
                    {"name": "wind_direction", "type": "float", "unit": "°", "description": "风向"},
                    {"name": "temperature", "type": "float", "unit": "°C", "description": "环境温度"},
                    {"name": "pressure", "type": "float", "unit": "hPa", "description": "气压"},
                    {"name": "power_actual", "type": "float", "unit": "kW", "description": "实际发电功率"}
                ]
            },
            {
                "id": "load-forecast-huadong",
                "name": "负荷预测 - 华东电网",
                "scenario": "power-grid",
                "template": "load_forecast",
                "description": "华东电网区域负荷数据，包含历史负荷和气象因素",
                "records": 0,
                "features": ["temperature", "humidity", "day_of_week", "hour", "is_holiday"],
                "target": "load",
                "time_column": "timestamp",
                "interval": "1h",
                "date_range": "-",
                "available": False,
                "columns": [
                    {"name": "timestamp", "type": "datetime", "description": "时间戳"},
                    {"name": "temperature", "type": "float", "unit": "°C", "description": "温度"},
                    {"name": "humidity", "type": "float", "unit": "%", "description": "湿度"},
                    {"name": "day_of_week", "type": "int", "description": "星期几(0-6)"},
                    {"name": "hour", "type": "int", "description": "小时(0-23)"},
                    {"name": "is_holiday", "type": "bool", "description": "是否节假日"},
                    {"name": "load", "type": "float", "unit": "MW", "description": "电网负荷"}
                ]
            },
            {
                "id": "equipment-fault-industrial",
                "name": "设备故障预测 - 工业园区",
                "scenario": "predictive-maintenance",
                "template": "fault_prediction",
                "description": "工业设备传感器数据，用于故障预测和预防性维护",
                "records": 0,
                "features": ["vibration", "temperature", "pressure", "current", "rpm"],
                "target": "fault_label",
                "time_column": "timestamp",
                "interval": "1min",
                "date_range": "-",
                "available": False,
                "columns": [
                    {"name": "timestamp", "type": "datetime", "description": "时间戳"},
                    {"name": "vibration", "type": "float", "unit": "mm/s", "description": "振动值"},
                    {"name": "temperature", "type": "float", "unit": "°C", "description": "设备温度"},
                    {"name": "pressure", "type": "float", "unit": "bar", "description": "压力"},
                    {"name": "current", "type": "float", "unit": "A", "description": "电流"},
                    {"name": "rpm", "type": "float", "unit": "r/min", "description": "转速"},
                    {"name": "fault_label", "type": "int", "description": "故障标签(0/1)"}
                ]
            }
        ]
    }
# @AI_GENERATED: end
