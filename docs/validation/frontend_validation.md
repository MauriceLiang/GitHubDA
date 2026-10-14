# GitHubDA 前端验收记录

- 日期：2026-10-14
- 基准提交：`main@cdccdd42a755c29bf2f0a74c5192a2947bb2f8f4`
- 工作分支：`frontend`
- 环境：macOS，Python 3.12.14，Streamlit 1.63.0，pytest 8.4.2

## 已完成验证

- `python -m compileall -q frontend tests/frontend`：通过；字节码缓存写到仓库外临时目录。
- `python -m pytest -p no:cacheprovider -v tests/frontend`：21 passed（2.20 秒）。覆盖 API DTO 正反契约、`.env` 优先级、认证与幂等请求头、401/429/503 安全错误文本、204 删除、CSV、Mock 会话隔离，以及 AppTest 七页执行和详情跳转。
- `git diff --check`：通过。
- `MOCK_MODE=true` 下启动本地 Streamlit，并在浏览器中打开概览、仓库发现、分析库、项目对比、仓库详情、数据研究、数据与任务；七页均显示正文。详情从分析库跳转后 URL 包含 `repository_id`，刷新页面后仍恢复同一仓库。

## 待后端融合验证

- 当前 worktree 没有仓库根目录 `.env`，也没有提供可用的 FastAPI、Worker 或 `INTERNAL_API_KEY`；未执行真实模式 API、采集、缓存复用、深度任务及重试联调。FE-T02、FE-T05 至 FE-T11 的真实端到端验收仍待后端集成环境。
- 本次浏览器检查使用本地 Mock 样例；未将七页截图文件归档到仓库。AppTest 和页面可访问性树结果作为当前自动/浏览器验证证据。
- 本次没有真实 API 请求，因此没有请求编号。
