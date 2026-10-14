# GitHubDA 前端

交付 Streamlit 页面、v1 API 客户端、DTO、错误映射、Mock 场景和本地契约 fixture。Mock 使用预置的标准样例、GitHub 限流、Worker 心跳过期、无效仓库地址、部分完成和任务失败/重试数据；每个响应都来自 `frontend/fixtures/` 文件。

## 环境与启动

完整项目推荐从仓库根目录一键启动：

```bash
uv run --locked --all-extras python -m scripts.start
```

该命令会一并启动 FastAPI、Worker 和 Streamlit；完整配置与访问地址见 [README.md](../README.md)。

- Python 3.12
- 前端直接依赖版本在 `pyproject.toml` 的 `frontend` extra 中统一维护
- `API_BASE_URL`：FastAPI 地址，默认 `http://127.0.0.1:8000`
- `INTERNAL_API_KEY`：仅由 Streamlit 服务端环境读取；真实模式调用受保护的 `/api/v1` 时必需
- `MOCK_MODE`：`true` 时显式回放 `frontend/fixtures/` 中的契约样例；默认 `false`

前端从仓库根目录 `.env` 读取以上设置，进程环境变量优先；不需要 `source .env`。`.env` 不应提交。设置变更后重启相关进程。

单独调试前端时，先在仓库根目录运行 `uv sync --locked --all-extras`，再激活 `.venv`。

GitHubDA 有三个独立进程。真实采集需要 API、Worker 和 Streamlit 都运行：

```bash
# 终端 1：FastAPI
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

# 终端 2：采集 Worker
python -m backend.app.worker.main

# 终端 3：Streamlit 真实模式（仓库根目录 .env 中需有 INTERNAL_API_KEY）
MOCK_MODE=false python -m streamlit run frontend/app.py --server.port 8501
```

仅启动 Streamlit 不会执行真实采集任务。UI 演示模式无需后端/Worker：

```bash
MOCK_MODE=true python -m streamlit run frontend/app.py --server.port 8501
```

Streamlit 自带的菜单保留，可在 Settings 中切换 Light/Dark；项目默认主题为 GitHub Developer Workspace Dark。图表另有配色选项，需要与界面主题保持一致。

## 前端验证

在仓库根目录并激活上述虚拟环境后运行：

```bash
python -m compileall -q frontend tests/frontend
python -m pytest tests/frontend -q
```

## Mock 场景

在侧边栏选择“标准样例”“GitHub 限流”“Worker 心跳过期”“无效仓库地址”“部分完成任务”或“任务失败与重试”。Mock 只读取本地 JSON/CSV fixture；添加与任务状态转变按固定 fixture 顺序回放，不生成临时统计值。

若 API 端点没有匹配的 fixture，Mock 会显示明确缺失提示。Mock 数值是演示样例，不能当成实时 GitHub 数据。
