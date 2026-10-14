# 深度采集性能基线（改造前）

测量日期：2026-10-14。基线源码：`main@b2838605f60f1a4a8a45391417cda7e3dfe0d015`，通过 `git show` 加载原有 `GitHubClient.list_paginated`。执行环境：Python 3.12.14、macOS 15.7.9 arm64；`GITHUB_TOKEN` 为空，`GITHUB_MAX_PAGES=10`，`GITHUB_TIMEOUT_SECONDS=15`，并发数 1。

## 可复现的分页基线

使用 `httpx.MockTransport` 执行四个深度端点（commits、issues、pulls、releases），每个端点返回 3 页、每页 25 条，响应间加入 5 ms 固定延迟。覆盖目标为 12 页、300 条伪造记录；重复 10 次。总耗时和每个模块耗时用 `time.perf_counter()` 计时，p95 使用 nearest-rank（10 个样本时取最大值）。每个版本在独立 Python 子进程中运行，RSS 为进程 high-water mark。

| 模块 | HTTP calls | pages | observed items | median time (ms) | p95 (ms) | coverage | error |
|---|---:|---:|---:|---:|---:|---|---|
| profile | — | — | — | — | — | 未纳入分页 fixture | — |
| commits | 3 | 3 | 75 | 20.119 | 27.464 | complete | — |
| issues | 3 | 3 | 75 | 19.964 | 23.107 | complete | — |
| pulls | 3 | 3 | 75 | 19.918 | 27.822 | complete | — |
| releases | 3 | 3 | 75 | 22.589 | 33.733 | complete | — |
| **合计** | **12** | **12** | **300** | **87.067** | **100.342** | **fixture 完整** | — |

- 429：0；timeout：0。MockTransport 不访问 GitHub，不消耗配额；真实配额余额不适用。
- 分页 harness 峰值 RSS：42,205,184 bytes。该值含解释器、依赖和 fixture，不是 Worker 真实任务 RSS。
- 没有 Worker 数据库写入，因此 SQLite 锁等待与任务详情 API p95 未测。
- 真实仓库的改造前耗时、请求数、内存和 partial 比例未在实现前记录；本文件是同口径分页 harness 基线，不能代替真实端到端基线。
