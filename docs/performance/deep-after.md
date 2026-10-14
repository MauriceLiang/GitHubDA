# 深度采集进度改造后性能记录

测量日期：2026-10-14。改造代码提交：`b84007356b09ad414f13aad5c9cd12c6fa2d11ea`；对照基线：`main@b2838605f60f1a4a8a45391417cda7e3dfe0d015`。执行环境：Python 3.12.14、macOS 15.7.9 arm64；`GITHUB_TOKEN` 为空，`GITHUB_MAX_PAGES=10`，`GITHUB_TIMEOUT_SECONDS=15`，并发数 1。

## MockTransport 同口径分页对照

沿用 [`deep-baseline.md`](deep-baseline.md) 中的 fixture：4 个深度端点，每模块 3 页、每页 25 条，5 ms 固定响应延迟，10 次重复；基线调用改造前源码的 `list_paginated`，改造后调用 `list_paginated_detailed` 并同步触发页回调。p95 使用 nearest-rank（10 个样本时取最大值）。此测试不启动 Worker，也不执行 SQLite 进度写入。

| 版本 | HTTP calls | pages | observed items | median time (ms) | p95 (ms) | 进程峰值 RSS |
|---|---:|---:|---:|---:|---:|---:|
| 改造前 | 12 | 12 | 300 | 87.067 | 100.342 | 42,205,184 bytes |
| 改造后 | 12 | 12 | 300 | 85.471 | 96.356 | 41,025,536 bytes |

两组请求数与样本覆盖完全相同。中位数相差 1.596 ms（约 1.8%），p95 相差 3.986 ms（约 4.0%）；模块中位数也有小幅上下波动。样本只有 10 次且人工响应延迟会受本机调度影响，这些差异不足以证明真实提速。RSS 是隔离 harness 子进程 high-water mark，不代表 Worker 或数据库集成后的内存。

| 模块 | HTTP calls | pages | observed items | median time (ms) | p95 (ms) | coverage | error |
|---|---:|---:|---:|---:|---:|---|---|
| profile | — | — | — | — | — | 未纳入分页 fixture | — |
| commits | 3 | 3 | 75 | 20.951 | 26.862 | complete | — |
| issues | 3 | 3 | 75 | 20.661 | 22.795 | complete | — |
| pulls | 3 | 3 | 75 | 20.726 | 22.404 | complete | — |
| releases | 3 | 3 | 75 | 21.672 | 25.956 | complete | — |

## 真实 GitHub 与未测项

本轮以匿名模式尝试了 `octocat/Hello-World` 的仓库资料请求；上游返回 429，任务尚未创建，因此没有深度页数、模块耗时、真实 Worker RSS、SQLite 锁等待或任务详情 API 响应时延可报告。该次尝试只观测到限流，未记录可用的剩余配额/重置时间或 `Retry-After` 数值；没有用 Token 重试，也没有在限流状态下继续发请求。真实 429 计数为 1，真实成功页数为 0；timeout 未观测到。

因此本轮没有真实仓库的改造前后比较，也不声称端到端提速。`_request_lock` 与单任务串行执行保持原样；未启用模块并发或提高请求频率。需要在限流解除后，使用相同仓库规模、时间窗和配置补做真实匿名/授权基线与改造后记录，再决定是否实施可选的并发优化。

## 结果语义与回退

- fixture 的 12 页在两个版本中都完整结束，300 条记录完全一致；没有用 `GITHUB_MAX_PAGES` 推算覆盖率。
- 模块状态、实际页数、错误码和流程进度分别持久化；partial 模块的指标保持 `null`，原始归档包含已成功页面及错误/分页上限标记。
- 当前没有新增并发开关；回退采集吞吐行为无需改配置，直接回滚功能提交 `b84007356b09ad414f13aad5c9cd12c6fa2d11ea` 即可。SQLite 迁移回退不建议用于含真实进度数据的数据库。
