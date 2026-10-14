"""Human-readable status labels shared by repository and task views."""

from __future__ import annotations

import streamlit as st


STATUS_LABELS = {
    "not_started": "尚未采集",
    "missing": "尚未采集",
    "not_collected": "尚未采集",
    "queued": "已排队",
    "processing": "正在采集",
    "running": "正在采集",
    "completed": "已采集",
    "succeeded": "任务已结束",
    "partial": "部分完成",
    "failed": "失败",
    "cancelled": "已取消",
    "stale": "数据已过期",
    "fresh": "数据新鲜",
    "unknown": "状态未知",
    "ok": "正常",
}
DATA_STATUS_LABELS = {
    "missing": "暂无可用快照",
    "fresh": "快照新鲜",
    "stale": "展示上次成功快照",
}


def status_label(status: str | None) -> str:
    if status is None:
        return "状态未知"
    return STATUS_LABELS.get(status, status)


def render_status(status: str | None, data_status: str | None = None) -> None:
    parts = [status_label(status)]
    if data_status:
        parts.append(DATA_STATUS_LABELS.get(data_status, data_status))
    st.caption(" · ".join(parts))
