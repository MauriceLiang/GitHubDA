# 后端修复验证记录

## 基线与提交

- 仓库：`MauriceLiang/GitHubDA`
- 基线：`main@cdccdd42a755c29bf2f0a74c5192a2947bb2f8f4`
- 实现分支：`fix/githubda-backend`
- 后端实现提交：`e27445c529b5d3cd35ecd33ac9d70b77e7d82b2b`
- Python：`3.12.14`
- 迁移：本次未修改数据库 schema，无新增迁移。

## 自动化验证

| 检查 | 结果 |
|---|---|
| 基线 `pytest tests/backend -q` | 20 passed |
| 当前 `/private/tmp/GitHubDA-backend-venv/bin/python -m pytest -p no:cacheprovider tests/backend -q` | 37 passed；有 Starlette 提示 `httpx` TestClient 用法将弃用的警告 |
| `PYTHONPYCACHEPREFIX=/private/tmp/GitHubDA-compile-cache ... -m compileall -q backend frontend migrations scripts tests` | 通过 |
| `git diff --check` | 通过 |
| 临时 SQLite `alembic upgrade head`，重复升级、`downgrade -1` 后再升级 | 通过 |
| `alembic check` | `No new upgrade operations detected.` |
| `scripts.check_data_integrity`（空迁移库与真实冒烟数据库） | `foreign_key_errors=[]`、`orphan_memberships=[]` |
| 工作流 YAML 解析 | 通过；GitHub Actions 托管运行结果尚未核验 |

首次直接执行 `compileall` 时，工作区策略禁止写入仓库中的 `__pycache__`，命令失败；将 `PYTHONPYCACHEPREFIX` 指到 `/private/tmp` 后编译通过，未在仓库生成缓存文件。

## 真实公开 GitHub 冒烟

在独立临时 SQLite、临时原始归档目录中启动 API 和 Worker，目标仓库为 `octocat/Hello-World`。使用本地冒烟 Key；本次命令没有注入或输出 GitHub Token。API 与 Worker 使用同一临时 `DATABASE_URL` 和 `RAW_DATA_DIR`。

- `/healthz`：200；Worker 状态：`ok`。
- `/api/v1/github/resolve`：200；添加仓库：201。
- basic 任务：`succeeded`，`attempt=1`。
- deep 刷新：202；deep 任务：`partial`，`attempt=1`。
- basic 分析：`completed`；deep 分析：`partial`。两份分析与快照 `source_collected_at` 对齐，为 `2026-10-14T00:26:19Z`。
- deep 模块：commits、releases 为 `complete`；issues、pulls 为 `partial`。此次冒烟将 `GITHUB_MAX_PAGES=1` 限制为单页以控制外部请求量；服务正确保留了部分覆盖状态，没有把未取完的分页标成完整。
- API/Worker 日志扫描未发现冒烟 Key、`Authorization:` 或 `Bearer ` 字符串。
- 关键请求号（已截短）：resolve `req_5f77fb…44bf149`，添加 `req_378b65…b7989a4`，basic 任务查询 `req_de021e…f3d5b5`，deep 刷新 `req_d68a59…226ebd6`，deep 任务查询 `req_00a4ac…3a8995f`。

## 前端 DTO 联调结果

使用真实 FastAPI `TestClient` 响应直接调用 `frontend/api/models.py` 中的 Pydantic DTO。以下不兼容仍需前端归属代码修复；本后端分支未修改 `frontend/**`：

| 响应 | DTO 校验结果 | 不兼容字段 |
|---|---|---|
| datasets | 失败 | DTO 的 `Dataset.type` 不接受 `featured` |
| 空 library overview | 失败 | DTO 的 `SourceMetadata.collected_at` 不接受 `null` |
| 空 research overview | 失败 | DTO 的 `SourceMetadata.collected_at` 不接受 `null` |
| 空 research data-quality | 失败 | 5 个 `missing_fields[].rate` 均为合法 `null`，DTO 要求非空浮点数 |
| 新建 queued task 列表 | 失败 | DTO 要求 `attempt >= 1`，契约和后端新任务值为 0 |
| 缓存命中的 refresh | 失败 | DTO 仅接受 `queued/running`，后端按契约返回 `succeeded` |

仓库当前没有 `tests/frontend/` 目录。CI 工作流会运行后端测试；当该前端测试目录加入后会自动运行它。**当前结果不能视为前后端 DTO 联调通过。**

## 未完成的集成项

- 远端当时没有 `integration/githubda-validation` 分支，因此该修复以审计基线 `origin/main` 起分支；本次只推送 `fix/githubda-backend`，不直接改动 `main`。
- 文档要求的集成分支、前端 DTO 修复、前端测试、Streamlit 三进程闭环以及以集成分支为目标的 PR 尚未完成；需集成人员建立集成分支并由前端归属者同步 DTO 后继续验收。
- 真实 GitHub deep 冒烟有意限制为单页，因此结果为 `partial`；真实 basic 流程已成功，完整 deep 分页未在本次冒烟验证。
