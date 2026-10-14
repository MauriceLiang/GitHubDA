# GitHubDA 后端

后端由 FastAPI、SQLite、Alembic 和独立 Worker 组成。它通过 GitHub REST API 读取公开仓库，保留原始响应归档、指标快照和分析任务历史。

## 环境

项目按 Python 3.12 运行。创建虚拟环境并安装依赖：

```bash
uv venv --python 3.12
uv pip install --python .venv/bin/python -e '.[dev]'
cp .env.example .env
```

在 `.env` 中设置仅本机使用的 `INTERNAL_API_KEY`。`GITHUB_TOKEN` 可选；未配置时使用 GitHub 匿名额度。密钥只由 API 和 Worker 进程读取。

默认 SQLite 文件固定解析到仓库根目录的 `data/app.db`，不受启动时当前目录影响。原始压缩 JSON 写入 `data/raw/`。可用 `DATABASE_URL` 与 `RAW_DATA_DIR` 覆盖路径。

## 数据库与启动

从空库执行迁移：

```bash
alembic upgrade head
```

分别启动 API 与 Worker：

```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
python -m backend.app.worker.main
```

健康检查为 `GET /healthz`。其余 `/api/v1/*` 请求须带 `X-Internal-Api-Key`。`/docs` 和 `/openapi.json` 用于本机联调，服务默认只绑定回环地址。

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

脚本按 manifest 中的语言/Star 分层配额和固定随机种子抽取，并在 `sampling_runs` 中保留每条候选的纳入或排除原因；候选不够时报告未填满配额。已冻结版本不会被覆盖，规则变化时请使用新的 `dataset_id`。GitHub Search 不完整或候选范围有限时，结果只能称为分层配额样本，不能代表 GitHub 全体。

## API

契约为 `docs/03_API接口契约_v1.0.md`。实现覆盖 API-01 至 API-20（API-01 为 `/healthz`）：搜索/解析、分析库、仓库快照与分析、任务/重试、数据集、总览/研究统计/质量、比较和 CSV 导出。JSON 成功响应采用 `data`/`meta`，错误采用 `error`/`request_id`；删除成员关系返回空的 204，CSV 为 UTF-8 文本。

Worker 对基础仓库档案采集真实快照。深度采集限定在近期窗口并遵守分页上限；未完整分页或上游端点失败时，返回 `partial` 与 null 指标。星标时间序列只包含真实采集日期，不插值。

## 验证与诊断

```bash
python -m compileall -q backend frontend migrations scripts tests
python -m pytest -p no:cacheprovider tests/backend -q
python -m scripts.check_data_integrity
```

做本地集成验收前，将 `DATABASE_URL`、`RAW_DATA_DIR` 和随机 `INTERNAL_API_KEY` 配置到本地环境；API 与 Worker 必须使用相同配置。临时数据库先运行 `alembic upgrade head`，再分别启动 API 和 Worker。确认 `/healthz` 返回 200 后，带 `X-Internal-Api-Key` 请求 `/api/v1/datasets` 与 `/api/v1/system/status`。真实 GitHub 冒烟可通过 `/api/v1/github/resolve` 查询一个公开仓库，再添加到分析库并轮询任务；记录 `X-Request-ID`、任务终态和 coverage，勿将 Token、内部 Key、测试数据库或原始归档提交到仓库。

`GET /api/v1/system/status` 读取数据库、Worker 心跳、队列和 GitHub 最近一次限额缓存；它不会为了状态查询消耗 GitHub 配额。`GET /repositories/{id}` 只读取本地数据库，因此 GitHub 暂时不可用时仍能展示最近一次成功结果。
