# RepoVantage 前端

RepoVantage 主前端使用 Vue 3、TypeScript 与 Vite。生产构建由 FastAPI 提供；默认通过本机浏览器网关读取和修改真实后端数据。仓库级 Mock 数据仅用于明确启用的原型演示。

## 本地开发

```bash
npm ci
npm run dev
```

开发服务器使用 `http://127.0.0.1:5173`，并把 `/api/browser` 代理到本机 FastAPI `http://127.0.0.1:8501`。请先启动后端。

```bash
VITE_DATA_MODE=http npm run dev   # 真实后端，默认模式
VITE_DATA_MODE=mock npm run dev   # 明确启用原型演示数据
npm run build                    # 类型检查 + 生产构建
```

从项目根目录运行 `python -m scripts.start` 会构建本目录并启动 FastAPI 与 Worker；FastAPI 在 `http://127.0.0.1:8501` 同时提供 API 和 Vue 页面。

## 页面

- `/` 总览：添加仓库、最近分析、活动变化与进行中的任务
- `/repositories` 仓库管理：搜索、添加、移除与多选比较
- `/repositories/:id/overview|activity|issues|prs|releases` 单仓库分析
- `/compare` 项目比较（2–5 个仓库）
- `/research` 研究数据集分析
- `/tasks` 任务状态与失败任务重试

## 数据边界

前端通过 `RepositoryDataSource` 接口访问数据。默认实现使用带 CSRF 校验的本机浏览器 API 会话，不在浏览器中暴露内部 API Key。仅后端实际提供的数据会进入图表；缺少的日级序列、逐条 Issue/PR/Commit 等明细显示为未提供，不用 Mock、估算或演示数补齐。

