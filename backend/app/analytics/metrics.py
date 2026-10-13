from datetime import datetime

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def basic_metrics(stars: int | None, forks: int | None, collected_at: datetime, created_at: datetime | None, pushed_at: datetime | None) -> dict:
    age = (collected_at - created_at).total_seconds() / 86400 if created_at else None
    since_push = (collected_at - pushed_at).total_seconds() / 86400 if pushed_at else None
    if age is not None and age < 0:
        age = None
    if since_push is not None and since_push < 0:
        since_push = None
    return {
        "stars": stars,
        "forks": forks,
        "age_days": round(age, 1) if age is not None else None,
        "days_since_push": round(since_push, 1) if since_push is not None else None,
        "release_count_365d": None,
        "commits_90d": None,
        "issues_closed_90d": None,
        "pr_merged_90d": None,
    }


def numeric_summary(values: list[float]) -> dict:
    series = pd.to_numeric(pd.Series(values, dtype="float64"), errors="coerce").dropna()
    if series.empty:
        return {"count": 0, "mean": None, "median": None, "std": None}
    return {
        "count": int(series.count()),
        "mean": round(float(series.mean()), 3),
        "median": round(float(series.median()), 3),
        "std": round(float(series.std(ddof=1)), 3) if len(series) > 1 else None,
    }


def spearman_summary(x_values: list[float], y_values: list[float]) -> dict:
    pairs = pd.DataFrame({"x": x_values, "y": y_values}).apply(pd.to_numeric, errors="coerce").dropna()
    n = int(len(pairs))
    result = {"method": "spearman", "n": n, "coefficient": None, "p_value": None, "note": None}
    if n < 10:
        result["note"] = "有效配对样本少于 10，未计算研究性相关"
        return result
    if pairs["x"].nunique() < 2 or pairs["y"].nunique() < 2:
        result["note"] = "输入为常量，Spearman 系数与 p 值未定义"
        return result
    coefficient, p_value = spearmanr(pairs["x"], pairs["y"])
    if np.isfinite(coefficient) and np.isfinite(p_value):
        result["coefficient"] = round(float(coefficient), 6)
        result["p_value"] = round(float(p_value), 8)
    else:
        result["note"] = "输入数据无法形成有效相关估计"
    return result
