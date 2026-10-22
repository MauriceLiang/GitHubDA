# RepoVantage

RepoVantage 是一款 GitHub 开源项目分析台，包含 Vue 3 前端、FastAPI、SQLite 和采集 Worker。

项目仓库：[MauriceLiang/RepoVantage](https://github.com/MauriceLiang/RepoVantage)

## 一键启动

需要 Python 3.12 和 [uv](https://docs.astral.sh/uv/)。在仓库根目录运行：

```bash
uv run --locked --all-extras python -m scripts.start
```

命令会按 `uv.lock` 准备依赖、构建前端、自动创建本地 `.env` 和随机 `INTERNAL_API_KEY`、升级数据库，然后启动 API 与 Worker。服务地址：

- 前端：<http://127.0.0.1:8501>
- API 文档：<http://127.0.0.1:8501/docs>
- API 健康检查：<http://127.0.0.1:8501/healthz>

按 `Ctrl+C` 会一并停止 API 与 Worker。`.env` 中的 `GITHUB_TOKEN` 可选；不配置时使用 GitHub 匿名额度。

新前端只监听本机回环地址。浏览器通过同源会话和 CSRF 校验访问 API；`INTERNAL_API_KEY` 仅由服务端读取，不进入前端构建产物。

## 前端开发

主界面源码位于 `frontend/`。Mock 模式不需要启动后端：

```bash
cd frontend
npm ci
VITE_DATA_MODE=mock npm run dev
```

若要从 Vite 开发服务器联调真实 API，先用一键启动命令启动本地服务，再在 `frontend` 目录执行 `VITE_DATA_MODE=http npm run dev`。开发服务器会把安全浏览器 API 请求转发到本机 FastAPI。

后端配置与 API 说明见 [README_backend.md](README_backend.md)。

## 活动与协作分析（insights-v1）

在仓库详情点击“采集活动数据”。Worker 保存真实 Commit / Issue / PR / Release 事件，计算并固化分析结果；详情默认展示开发活跃度，另可查看 Issue 效率、PR 协作、发布节奏和数据来源。

- Commit：UTC 自然周趋势、最近四个完整周与前四周变化。
- Issue / PR：关闭或合并耗时分布、中位数、样本门槛控制的 p75/p90。
- Release：正式发布时间轴、相邻间隔分布，预发布单独计数。
- 比较：共同完整周、窗口/语言/覆盖限制；研究：只使用研究成员的完整活动指标。

默认 90 天活动窗口，Release 365 天，均为左闭右开。分页达到上限时只展示已观测证据，不把部分数据或未采集当零。关注度与活动指标不代表代码质量。

数据库通过 Alembic `0003_activity_insights` 增量升级；升级已有数据库前建议使用 SQLite backup 留存一致备份。旧快照、任务、研究成员和 API 保留。历史归档先预览，再显式导入：

```bash
uv run --locked --all-extras python -m scripts.recompute_insights --repository-id 123
uv run --locked --all-extras python -m scripts.recompute_insights --repository-id 123 --apply
```

命令只读取本地最近活动归档，不联网；旧归档查询合同未知时保守标记 partial。新版原始归档有窗口和分页元数据；重复回放复用同一输入指纹，算法升级另建运行。

指标、API、迁移与真实验收：[docs/insights/04_delivery.md](docs/insights/04_delivery.md)。真实模式发生错误不会回退 Mock；仅显式 `VITE_DATA_MODE=mock` 启用演示，正式构建默认 http。

### 分析图表

当前 Vue 前端按分析问题提供 Commit 趋势、Issue/PR 周聚合和耗时分布、Release 时间线与间隔排序、研究分组与散点，以及共同完整周比较图。页面只使用后端实际返回的数据；缺失、样本不足和覆盖不完整会明确标注。图表组件和数据边界见 [多图表说明](docs/insights/05_chart_styles.md)。
