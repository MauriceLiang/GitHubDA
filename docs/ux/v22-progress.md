# GitHubDA 产品体验与页面重构 V2.2 实施记录

## 实施范围

- 基于基线提交 `31530a44edcf5c5775ce9fca21bae1860cfec40a`，在 `feature/githubda-ux-v22` 上实施；未提交或推送。
- 将可见导航收敛为“总览、仓库、研究、任务”，旧仓库详情、发现、对比路由保留为隐藏页面；根首页与旧 `/dashboard` 地址均指向总览。
- 将“我的仓库”和“发现仓库”合并到“仓库”页内按需切换；发现视图不加载个人分析库列表。
- 在仓库列表内选择 2–5 个有可用快照的项目进行对比；选择跨页保留，达到上限后禁用其他项目，移除仓库时清除其选择和缓存对比结果。
- 精简仓库行操作为“查看分析”和“更多”；总览展示对齐的输入区、KPI、最近仓库与任务，并在有效分析样本 `n < 3` 时隐藏分布图。
- 研究筛选和任务列表按紧凑布局呈现；排队和运行中的任务沿用现有轮询机制自动更新，任务列表优先显示仓库名。
- 更新 `frontend/README_frontend.md`。未更改后端 API、任务幂等性、研究数据隔离或数据语义。

## 验证

- 前端：`env -u ALL_PROXY -u HTTPS_PROXY -u HTTP_PROXY -u all_proxy -u https_proxy -u http_proxy .venv/bin/python -m pytest -p no:cacheprovider tests/frontend -q`，39 项通过。
- 后端：同样清除代理变量后运行 `tests/backend`，48 项通过；包含现有 Starlette/httpx 和 Alembic 弃用警告。
- `python -m compileall -q frontend tests` 和 `git diff --check` 通过。
- Codex 内置浏览器曾加载 `/dashboard` 的总览内容和四项可见导航，未见 `Page not found`。之后重启本地服务时，浏览器 URL 策略拒绝访问 `127.0.0.1:8501`；因此 1440×900、1280×800、390×844 三种尺寸的完整视觉验收未完成，也没有可复查的截图文件。
- 页面验证仅使用 `MOCK_MODE=true`。真实 GitHub API、Worker 和数据库联调未执行，不能以 Mock 结果代表真实集成结果。

## 后续验收

- 在 Codex 内置浏览器允许访问本地预览后，完成 1440×900、1280×800、390×844 的截图与布局检查，并将截图保存到可复查路径。
- 在准备好真实 API 与 Worker 环境后，按手册的授权和环境要求执行真实集成验收。
