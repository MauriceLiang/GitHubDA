# RepoVantage 后端

后端由 FastAPI、SQLite、Alembic 和独立 Worker 组成。它通过 GitHub REST API 读取公开仓库，保留原始响应归档、指标快照和分析任务历史。

## 环境

项目按 Python 3.12 运行。创建虚拟环境并安装依赖：

```bash
uv sync --all-extras
source .venv/bin/activate
cp .env.example .env
```

在 `.env` 中设置仅本机使用的 `INTERNAL_API_KEY`。`GITHUB_TOKEN` 可选；未配置时使用 GitHub 匿名额度。密钥只由 API 和 Worker 进程读取。

默认 SQLite 文件固定解析到仓库根目录的 `data/app.db`，不受启动时当前目录影响。兼容旧版的原始压缩 JSON 写入 `data/raw/`；新版逐页采集归档写入 Git 忽略的 `data/collected/`，数据库检查点是断点续传的权威状态。精选数据包已随项目提供在 `data/datasets/featured-v1/`，对应分发 ZIP 为 `data/datasets/featured-v1.zip`。当前包包含 15 个公开仓库，活动数据窗口为 90 天、正式 Release 窗口为 365 天，不代表 GitHub 全历史。可用 `DATABASE_URL` 与 `RAW_DATA_DIR` 覆盖旧版归档路径。

## 数据库与启动

完整项目推荐使用仓库根目录的一键启动命令：

```bash
uv run --locked --all-extras python -m scripts.start
```

它会先构建 Vue 前端，再自动升级数据库并启动 API 与 Worker。首次运行会创建 `.env` 并生成本机随机 `INTERNAL_API_KEY`；完整访问地址见 [README.md](README.md)。新前端仅允许绑定本机回环地址。

需要单独调试后端时，可手动运行迁移并分别启动 API 与 Worker：

从空库执行迁移：

```bash
alembic upgrade head
```

分别启动 API 与 Worker：

```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8501
python -m backend.app.worker.main
```

健康检查为 `GET /healthz`。其余 `/api/v1/*` 请求须带 `X-Internal-Api-Key`。`/api/browser/*` 是给同源 Vue 前端使用的本机会话入口；密钥不会下发到浏览器。`/docs` 和 `/openapi.json` 用于本机联调，服务默认只绑定回环地址。

## 研究样本

仓库不含演示样本。首次安装会创建空的 `research-2026-v1` 数据集；API 会如实返回 0 个成员。要冻结真实样本，先从 GitHub REST Search 收集公开候选，人工复核项目资格，并按以下结构提供 manifest：

```json
{
  "metadata": {
    "source": "GitHub REST API",
    "sampled_at": "2026-10-13T00:00:00Z",
    "queries": {"Python": "stars:100..100000 language:Python"},
    "candidate_count": 1,
    "incomplete_results": false,
    "random_seed": 20261013,
    "rules_version": "selection-v1",
    "quotas": {"Python": {"0-999": 1}}
  },
  "candidates": [
    {
      "repository": {"id": 123, "full_name": "owner/project", "html_url": "https://github.com/owner/project", "language": "Python", "stargazers_count": 500, "forks_count": 30, "fork": false, "archived": false, "private": false},
      "reviewed_eligible": true,
      "inclusion_reason": "人工复核为公开软件项目",
      "selection_source": "language=Python; tier=0-999"
    }
  ]
}
```

构建选择结果并写入一个尚未冻结的数据集：

```bash
python -m scripts.build_research_sample candidates.json --dataset-id research-2026-v1
```

候选清单由 GitHub Search 采集器生成。默认对每个语言/Star 分层按最近更新、Star 降序和 Star 升序各取 20 条并按仓库 ID 去重（最多 900 条候选）；这会产生最多 45 次 Search 请求，运行前应检查当前 GitHub 配额。Search 的排序结果可能重叠，manifest 会记录每层的实际候选数和不足目标，不能把候选目标当作已保证数量。采集器只生成待人工复核的 manifest，不能直接构建研究样本：

```bash
python -m scripts.collect_research_candidates --per-bucket 20 --output data/manifests/research-candidates.json
```

审核候选的公开状态、项目类型和存在时间后，填写 `reviewed_eligible` 与 `inclusion_reason`，再运行上面的冻结命令。采集器不会自动替用户消耗配额或冻结样本。

脚本按 manifest 中的语言/Star 分层配额和固定随机种子抽取，并在 `sampling_runs` 中保留每条候选的纳入或排除原因；候选不够时报告未填满配额。已冻结版本不会被覆盖，规则变化时请使用新的 `dataset_id`。GitHub Search 不完整或候选范围有限时，结果只能称为分层配额样本，不能代表 GitHub 全体。

## API

契约为 `docs/03_API接口契约_v1.0.md`。实现覆盖 API-01 至 API-20（API-01 为 `/healthz`）：搜索/解析、分析库、仓库快照与分析、任务/重试、数据集、总览/研究统计/质量、比较和 CSV 导出。JSON 成功响应采用 `data`/`meta`，错误采用 `error`/`request_id`；删除成员关系返回空的 204，CSV 为 UTF-8 文本。

Worker 对基础仓库档案采集真实快照。深度任务支持 `quick`、`window`、后台 `incremental` 和人工排队的 `backfill`：快速范围遵守用户页数预算；完整窗口和增量同步跟随所有分页；增量同步仅对最近分析运行的四个活动模块都完整的仓库排队，按 7 天重叠区间查询并从本地去重事件表重新计算滚动窗口。Commit/Issue 使用时间查询，PR 按更新时间倒序并在重叠边界停止，Release 端点逐次复核并按数字 ID 去重。每日增量同步在 04:00 UTC 排队，日常基础资料刷新在 03:00 UTC 排队。

历史回填只针对五个试点仓库提供 CLI 入口，默认仅预览本地数据库中已存在的仓库；加 `--queue` 才会写入任务队列。每次回填按用户页数预算让出 Worker，保留检查点并继续排队，普通任务优先。CLI 本身不访问 GitHub；实际请求只会在 Worker 执行时发生。预算耗尽、部分覆盖和配额延期不会被标为完整；相关进度和采集范围可在任务详情中查看。星标时间序列只包含真实采集日期，不插值。

为现有数据集成员排队采集任务（真正的 GitHub 请求由已运行的 Worker 执行）：

```bash
python -m scripts.collect_dataset featured-default --scope window
```

预览五个历史回填试点（不会写入任务）：

```bash
python -m scripts.queue_history_pilot
```

审核预览后，使用 `--queue` 将可用仓库排入后台队列；GitHub 请求由 Worker 之后执行：

```bash
python -m scripts.queue_history_pilot --queue
```

需要更新精选包时，可生成、校验和导出数据；CLI 导入会写入当前 `DATABASE_URL` 指向的数据库：

```bash
python -m scripts.build_featured_bundle --version featured-v1.0.0
python -m scripts.verify_dataset_bundle data/datasets/featured-v1
python -m scripts.export_dataset_bundle data/datasets/featured-v1 --output data/datasets/featured-v1.zip --force
python -m scripts.import_dataset_bundle data/datasets/featured-v1.zip
```

打包器要求 `featured-default` 恰有 15 个已审核成员，且本地具备快照和分析数据；不会生成虚构的演示记录。仓库页的“导入精选仓库”按钮只读取校验通过的本地目录，不触发 GitHub 请求。`POST /api/v1/datasets/featured/import` 会返回 `202` 和持久化任务 ID；本地 Worker 校验并分批暂存数据，再在一个事务中合并正式数据和完成状态。可通过 `/api/v1/tasks`、`/api/v1/tasks/{task_id}` 查询导入与仓库采集任务；失败的精选数据导入可从任务中心重试。`GET /api/v1/datasets/featured/status` 返回轻量包状态、已导入版本和当前任务，不会在每次轮询时解压并全量解析 JSONL。导入任务不会创建 GitHub 客户端或消耗 API 配额。“下载数据包”按钮通过 `GET /api/v1/datasets/featured/export` 下载与该目录校验一致的 ZIP。

## 验证与诊断

```bash
python -m compileall -q backend migrations scripts tests
python -m pytest -p no:cacheprovider tests/backend -q
python -m scripts.check_data_integrity
```

做本地集成验收前，将 `DATABASE_URL`、`RAW_DATA_DIR` 和随机 `INTERNAL_API_KEY` 配置到本地环境；API 与 Worker 必须使用相同配置。临时数据库先运行 `alembic upgrade head`，再分别启动 API 和 Worker。确认 `/healthz` 返回 200 后，带 `X-Internal-Api-Key` 请求 `/api/v1/datasets` 与 `/api/v1/system/status`。真实 GitHub 冒烟可通过 `/api/v1/github/resolve` 查询一个公开仓库，再添加到分析库并轮询任务；记录 `X-Request-ID`、任务终态和 coverage，勿将 Token、内部 Key、测试数据库或原始归档提交到仓库。

`GET /api/v1/system/status` 读取数据库、Worker 心跳、队列和 GitHub 最近一次限额缓存；它不会为了状态查询消耗 GitHub 配额。`GET /repositories/{id}` 只读取本地数据库，因此 GitHub 暂时不可用时仍能展示最近一次成功结果。

## 事件分析 API（insights-v1）

新增接口均沿用内部认证和 `{data,meta}` 响应；浏览器沿用同源会话/CSRF，不传内部 Key：

- `GET /api/v1/repositories/{id}/insights`：最新版本化运行、按指标独立质量、来源、限制。
- `GET /api/v1/repositories/{id}/insights/series?metric=commits_weekly|issues_closed_weekly|prs_merged_weekly`。
- `GET /api/v1/repositories/{id}/insights/quality`：模块分页、错误、观察与查询范围。
- `GET /api/v1/repositories/{id}/insights/export.csv`：精确统计与分桶，包含单位、版本、窗口、任务，防 CSV 公式注入。
- `POST /api/v1/comparisons/insights`：`{"repository_ids":[1,2],"depth":"deep"}`；提交仅使用共同完整周，耗时窗口不一致则不给可比值。
- `GET /api/v1/research/insights?dataset_id=...`：研究成员活动分组、分布与相关，排除非 ready 输入。

无事件返回 missing，不返回伪造零值；单模块 partial 不影响其他 ready 模块。旧 `/analysis`、`/series`、比较和导出合同不变。完整合同见运行中的 `/docs`，离线快照见 [OpenAPI](docs/insights/openapi-insights.json)。指标字典与来源限制见 [指标文档](docs/insights/01_metric_dictionary.md)。
