# 分析窗口验收

## 自动化范围

后端 API 测试覆盖 30/90/180 天与默认 90 天、非法窗口、同期与各自窗口、缺失范围、部分覆盖、比较 CSV、来源任务、GET 不新增运行以及独立研究结果。数据库和 GitHub 响应均使用确定性 fixture，不访问真实 GitHub。

```bash
uv run --locked --all-extras pytest tests/backend/test_insights.py tests/backend/test_comparison_export.py tests/backend/test_worker_deep.py tests/backend/test_worker_queue.py tests/backend/test_api_contract.py
cd frontend
npm ci
npm run typecheck
npm run build
```

## 独立浏览器烟测

在一个终端启动独立 Mock 服务：

```bash
cd frontend
VITE_DATA_MODE=mock npm run dev -- --host 127.0.0.1 --port 5179 --strictPort
```

在另一个终端指定独立 Chromium 可执行文件运行：

```bash
cd frontend
BASE_URL=http://127.0.0.1:5179 CHROME_PATH=/absolute/path/to/chrome-headless-shell npm run test:e2e:analysis-window
```

脚本要求 `CHROME_PATH` 存在且可执行。每次启动独立的 headless 实例及隔离浏览器上下文，不连接已有浏览器会话。它校验服务确为 Mock 模式，意外访问后端或 GitHub 时失败。浅色和深色均断言窗口切换、缺失范围清空旧图表、模式按钮、切换不创建任务、点击后任务模式与范围、比较页刷新、保留缺失仓库、模式切换保持范围、实际下载的 30/180 天 CSV 与表格一致，以及桌面与 390px 布局。

默认将 CSV、截图和 `report.json` 保存到临时目录，在终端打印路径；可用 `E2E_ARTIFACT_DIR` 指定目录。截图仅作辅助，成功条件来自断言。CI 工作流为 `.github/workflows/analysis-window.yml`，自行安装 headless Chromium，不依赖个人浏览器路径或 GitHub Token。

API 字段说明见 [采集与回放合同](02_collection_contract.md)。[window-schema.json](window-schema.json) 是当前 OpenAPI 中窗口请求与来源响应模型的摘录，由契约测试校验。

## 真实 GitHub API 手动验收

状态：本次未执行。浏览器 Mock 测试及 fixture API 测试不证明真实 GitHub 分页或限流行为。

1. 使用独立测试数据库及公开测试仓库，通过环境变量配置 Token，启动 API、浏览器网关与 Worker。不要在日志、截图或提交中保存 Token。
2. 在设置中设定较小的快速页数预算，选择 30 天并启动快速采集。核对任务冻结起止时间、实际分页数及预算耗尽时的部分覆盖。
3. 对同一仓库选择 30 天完整窗口采集。核对普通分页不受快速预算限制；活动窗口与任务日期一致，Release 查询仍采用结束时间前 365 天。
4. 在实际遇到 GitHub 限流时核对 `resume_after`、检查点与恢复后的去重结果，记录最终模块覆盖。未遇到限流时将暂停/恢复标记为未验证，不人为耗尽额度。
5. 在分析和比较页面切换 30/90/180 天，检查缺失范围提示、两种比较模式及实际下载 CSV。记录仓库、任务 ID、窗口、运行版本、时间和结果，敏感信息脱敏。

## 本次执行记录

- 后端：`.venv/bin/python -m pytest -p no:cacheprovider tests/backend/test_insights.py tests/backend/test_comparison_export.py tests/backend/test_worker_deep.py tests/backend/test_worker_queue.py tests/backend/test_api_contract.py -q`，65 项通过。
- 前端：`npm ci`、`npm run typecheck`、`npm run build`、`node --check scripts/e2e-analysis-window.mjs` 均通过。`npm ci` 报告 1 项 moderate 依赖漏洞；本次没有升级或自动修复依赖。
- 浏览器：使用独立 Mock Vite 服务 `http://127.0.0.1:5179` 和独立 headless Chromium 运行 `npm run test:e2e:analysis-window`，浅色与深色场景均通过。实际下载并断言了每个主题下的 30 天、180 天 CSV；任务范围、无自动建任务、缺失范围、比较模式、桌面和 390px 布局也通过。浏览器断言报告和 CSV、截图保存在 `/tmp/repovantage-window-final/`。
- 错误配置：将 `CHROME_PATH` 指向不存在文件时，脚本以非零状态退出并明确报告路径不可用。
- `git diff --check` 通过。
- 真实 GitHub API 与限流恢复：未执行。远端 GitHub Actions run `39876166391`（提交 `668252e`）已完成，`backend` 与 `browser` 两个 job 均为 success；本地检查结果不替代后续提交对应的远端 CI。
