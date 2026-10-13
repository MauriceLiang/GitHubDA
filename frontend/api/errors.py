"""Safe, user-facing mapping for HTTP and contract errors."""

from __future__ import annotations

from typing import Any


ERROR_MESSAGES = {
    "INVALID_REPOSITORY_URL": "仓库地址格式不正确，请使用 github.com 仓库链接或 owner/repo。",
    "UNAUTHORIZED_CLIENT": "前端与 API 的内部认证配置不匹配，请检查服务端配置。",
    "REPOSITORY_NOT_FOUND": "仓库不存在、已删除或当前不可访问。",
    "RESOURCE_NOT_FOUND": "请求的数据不存在或已被移除。",
    "CONFLICTING_OPERATION": "当前任务状态不支持此操作，请刷新状态后重试。",
    "VALIDATION_ERROR": "输入参数不符合接口要求，请检查筛选条件。",
    "GITHUB_RATE_LIMITED": "GitHub 请求暂时受限。",
    "GITHUB_UPSTREAM_ERROR": "GitHub 暂时无法完成此请求。",
    "BACKEND_UNAVAILABLE": "后端服务暂不可用，已有数据可以继续查看。",
    "WORKER_UNAVAILABLE": "后台 Worker 暂不可用，采集任务可能延迟。",
    "GITHUB_TIMEOUT": "GitHub 查询超时，请稍后重试。",
    "API_TIMEOUT": "后端响应超时，请稍后重试。",
    "MOCK_FIXTURE_MISSING": "此接口还没有本地契约 fixture，Mock 模式无法回放。",
    "INVALID_API_RESPONSE": "后端响应不符合当前 API 契约。",
    "CLIENT_CONFIGURATION_ERROR": "Streamlit 服务端缺少 INTERNAL_API_KEY 配置。",
}


class APIError(RuntimeError):
    """An API failure with a safe message suitable for display in Streamlit."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str = "",
        details: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.request_id = request_id
        super().__init__(self.user_message)

    @property
    def user_message(self) -> str:
        message = ERROR_MESSAGES.get(self.code)
        if message is None:
            if self.status_code == 404:
                message = "请求的数据不存在或已被移除。"
            elif self.status_code == 429:
                message = "请求过于频繁，请稍后重试。"
            elif self.status_code >= 500:
                message = "服务暂时无法完成请求，请稍后重试。"
            else:
                message = "请求未能完成，请检查输入后重试。"

        retry_after = self.details.get("retry_after_seconds")
        if self.code == "GITHUB_RATE_LIMITED" and isinstance(retry_after, int) and retry_after >= 0:
            message += f" 建议 {retry_after} 秒后重试。"

        if self.request_id:
            message += f" 请求编号：{self.request_id}。"
        return message
