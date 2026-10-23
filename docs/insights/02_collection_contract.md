# 采集与回放合同

- GitHub `/commits?since&until`、`/issues?state=all&since`、`/pulls?state=closed&sort=updated&direction=desc`、`/releases`；每页100，上限沿用配置10，has_next或错误独立标partial，不宣称覆盖全历史。
- Issues since 按 updated_at；必须再按 closed_at/created_at 筛窗并排除 pull_request。[GitHub 官方端点定义](https://docs.github.com/en/rest/issues/issues#list-repository-issues)。
- PR closed 集合不支持所有已创建PR的转化率；不伪造分母。
- 每模块保存 requested_interval、observed_interval（对象更新时间或提交时间）、collected_at、page_count、has_next、错误和限流状态；观察区间不是完整覆盖证明。
- 原始 gzip 保留旧格式，新 `_meta.schema_version=1` 记录查询合同；唯一事件键 repository/type/external ID。UTC时间、外部ID与异常校验，拒绝额外个人邮件/原始用户对象入分析表。
- 事件 upsert、持久化 run 及旧快照在同一事务落地。普通采集 run 保存本次输入的统计；增量与回填可按对应窗口从去重事件表聚合。输入指纹含版本、来源、窗口、规范化事件和覆盖；重复复用，新版本另建 run。
- `python -m scripts.recompute_insights --repository-id ID` 仅预览已有最近归档，无网络；`--apply` 才写入。路径必须在raw目录，压缩≤16MB，展开≤64MB，每模块≤100页，JSON结构受限。旧归档查询合同未知：保守partial，需新采集得到ready。
- 0003仅新增两表；分桶放在不可变result_json（手册允许的小规模方案），不删除旧ActivityWindow/AnalysisResult。升级前SQLite backup；回滚在副本演练，生产不执行降级。

## 分析窗口与派生结果来源

`GET /repositories/{id}/insights?window_days=30|90|180` 默认 90 天。选择最近一个可证明所需长度的运行，以它的 `window_end` 为结束时间，从当前本地去重事件表按左闭右开窗口重新计算；不同仓库不保证结束时间一致。Release 仍以同一结束时间向前 365 天计算。

| 字段 | 含义 |
| --- | --- |
| `run_id` / `analyzed_at` | 所选覆盖证明运行及该运行的分析时间，未新建持久化快照 |
| `source_task_ids` / `source_archive_paths` | 覆盖证明运行关联的任务与归档，并非当前事件全部输入的归档清单 |
| `calculation_basis` | `current_local_event_store`，本次派生计算读取当前本地事件表 |
| `calculated_at` | 本次计算时间，范围未覆盖时为空 |
| `event_source_task_ids` | 本次读取事件记录实际对应的来源任务，去重并排序 |
| `observed_counts` | 所选窗口重新计算的观测计数；Release 计数独立使用近 365 天 |

`window_available` 表示存在所需长度的覆盖证明，不等于所有模块完整。模块质量继续使用覆盖证明运行的覆盖状态，事件存在不能将部分采集升级为完整。完整采集但无事件时保留 0 个事件，未覆盖范围时 `insights` 与 `observed_counts` 为空、任务来源为空。当前事件表保存最新已知对象记录，不是事务一致的历史快照。每次 GET 不写入新运行。

`POST /comparisons/insights` 和活动比较 CSV `/exports/comparison.csv?mode=...` 均接受 `window_days`，默认 90 天。`same_period` 取共同完整 UTC 自然周；耗时与 Release 间隔仍要求观察窗口一致且质量可用。`individual_periods` 使用各自结束时间的所选长度。响应保留未覆盖仓库与缺失原因，未知指标为 null（CSV 空单元格）。不传 `mode` 的基础概况 CSV 仍使用原合同。`/research/insights` 使用各成员最新保存的 run 结果，不受页面全局窗口和当前事件表后续更新影响；冻结的仍是研究成员规则，不是永久锁定运行。
