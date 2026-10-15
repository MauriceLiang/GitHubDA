# GitHubDA UI/UX V2 实施记录

## PR-01：首页直接分析

按 V2 方案仅实施 PR-01，并停在该阶段等待后续审查。

### 修改内容

- `frontend/pages/dashboard.py`：首页始终显示仓库输入；空分析库时仍可直接开始分析；最近仓库请求和展示限制为 5 条；移除无活跃任务时占位的空提示。
- `frontend/components/repository_input.py`：新增首页 owner/repo 或 GitHub URL 表单，支持表单提交。
- `frontend/repository_flow.py`：统一已入库检查、基础分析添加、稳定幂等键重试、当前仓库/任务状态写入和详情页导航。
- `frontend/pages/explore.py`：未入库候选的“分析”按钮复用同一流程并直接进入详情；已入库候选直接打开详情。
- `frontend/state/keys.py`：新增首页输入和提交幂等键状态，移除旧的添加后通知状态。
- `frontend/fixtures/resolve_existing.json`：新增已入库解析场景 fixture。
- `tests/frontend/test_pages_smoke.py`：覆盖空库入口、首页提交、已入库不重复添加、解析错误保留输入、添加失败重试复用幂等键，以及发现页直接跳转。
- `frontend/README_frontend.md`：补充首页分析流程和复用行为说明。

### 接口变化

无后端或公共 API 契约变化。复用现有 `POST /api/v1/github/resolve` 和 `POST /api/v1/library/repositories`。

### 验证结果

- `uv run --locked --all-extras python -m pytest -p no:cacheprovider tests/frontend`：32 passed。
- `python -m compileall -q frontend tests/frontend`：通过。
- `git diff --check`：通过。
- 浏览器使用显式 `MOCK_MODE=true` 检查空分析库、首页提交直达 `/repository?repository_id=1362490`，并在 1440×900、1280×800、390×844 视口查看首页。390px 检查时收起侧栏，页面文档宽度为 390px，未检测到水平溢出。

### 未完成与限制

- 三种视口的截图已在浏览器验收过程中以内联预览检查，但当前浏览器工具只返回图像预览，没有可写入工作树的截图文件路径。因此本次未提交截图文件；按方案要求的可复查截图路径仍待补齐。
- 浏览器流程使用本地 Mock fixture。真实 API、Worker、数据库联调未验证。
- PR-02 及后续阶段未实施，按方案要求留待 PR-01 审查后继续。
