# GitHubDA 前端

前端由 Streamlit 页面、v1 API 客户端、Pydantic DTO、错误映射、Mock 场景和契约 fixture 组成。真实数据与任务状态均从现有 API 读取；Mock 数字只用于明确选择的本地演示场景。

## 环境与启动

完整项目推荐从仓库根目录一键启动：

    uv run --locked --all-extras python -m scripts.start

该命令会一并启动 FastAPI、Worker 和 Streamlit；完整配置与访问地址见 README.md。

- Python 3.12
- Streamlit 1.63.0
- Plotly 7.1.0
- API_BASE_URL：FastAPI 地址，默认 http://127.0.0.1:8000
- INTERNAL_API_KEY：仅由 Streamlit 服务端环境读取；真实模式调用受保护的 /api/v1 时必需
- MOCK_MODE：true 时显式回放 frontend/fixtures 中的本地契约样例；默认 false

单独调试前端时，先在仓库根目录运行 uv sync --locked --all-extras，再激活 .venv。

仅启动 Streamlit 不会执行真实采集任务。前端 Mock 演示无需后端或 Worker：

    MOCK_MODE=true python -m streamlit run frontend/app.py --server.port 8501

## 页面导航

- 工作台：默认查看个人分析库摘要、近期仓库和活跃任务。空库提供发现仓库入口。
- 发现仓库：搜索关键词、owner/repo 或 GitHub URL；添加后显示任务已提交状态。
- 我的分析库：搜索、筛选和排序；移除操作要求确认，且只移除成员关系。
- 仓库对比：使用服务端搜索和分页，跨页保留已选仓库；只允许选择已有基础快照的项目。
- 研究分析：只读取明确版本的研究数据集；不把个人分析库数据作为研究样本。
- 任务中心：优先显示排队和运行中任务；历史任务和系统状态在次级区域查看。
- 仓库详情继续使用 /repository?repository_id=<id> 深链，并在当前页展示基础指标、深度任务和结果状态。

CSV 从业务页导出：个人分析库在“我的分析库”，固定研究数据集在“研究分析”。

## 任务进度与兼容

GET /api/v1/tasks 和 GET /api/v1/tasks/{task_id} 的新增字段均可缺省。旧 Task 会将 progress_kind 视为 unknown、modules 视为空数组；没有新字段时显示阶段状态，不会由前端根据分页数量推算完成百分比。

只有 progress_kind=stages 且 progress_percent 有值时才显示阶段进度条，并明确提示它不代表数据覆盖率。模块状态、coverage、已获取页数、页数限制和观察条数分别呈现。eta_seconds 为 null 时显示“完成时间暂不可估计”。任务成功只表示任务流程结束，不表示已覆盖 GitHub 的全部历史。

Mock 侧边栏场景包含标准样例、空分析库、限流、Worker 状态、v2 模块进度、部分完成和失败任务。Mock fixture 仅用于本地演示，不作为真实 API 联调结果。

## 外观与验证

Streamlit Settings 管理界面主题。侧边栏中的“图表配色”只控制 Plotly 图表；由于应用无法可靠读取运行时主题，它不会声称自动跟随界面主题。默认界面和图表均为深色。

在仓库根目录运行前端验证：

    uv run --locked --all-extras python -m compileall -q frontend tests/frontend
    uv run --locked --all-extras python -m pytest tests/frontend -q

手工 UI 验收需检查 1440×900、1280×800 和 390×844，覆盖空库、搜索与添加、任务状态、深度分析、对比、研究空样本和 CSV 导出。
