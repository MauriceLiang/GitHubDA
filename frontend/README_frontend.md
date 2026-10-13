# GitHubDA 前端

交付 Streamlit 页面、v1 API 客户端、DTO、错误映射、Mock 场景和本地契约 fixture。Mock 使用预置的标准样例、GitHub 限流、Worker 心跳过期、无效仓库地址、部分完成和任务失败/重试数据；每个响应都来自 `frontend/fixtures/` 文件。

## 环境

- Python 3.12
- 直接依赖版本见 `requirements.txt`
- `API_BASE_URL`：FastAPI 地址，默认 `http://127.0.0.1:8000`
- `INTERNAL_API_KEY`：仅由 Streamlit 服务端环境读取；真实模式调用受保护的 `/api/v1` 时必需
- `MOCK_MODE`：`true` 时显式回放 `frontend/fixtures/` 中的契约样例；默认 `false`

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r frontend/requirements.txt
python -m streamlit run frontend/app.py --server.port 8501
```

演示模式：

```bash
MOCK_MODE=true python -m streamlit run frontend/app.py --server.port 8501
```

Streamlit 自带的菜单保留，可在 Settings 中切换 Light/Dark；项目默认主题为 GitHub Developer Workspace Dark。图表另有配色选项，需要与界面主题保持一致。环境变量变更后重启进程。

## Mock 场景

在侧边栏选择“标准样例”“GitHub 限流”“Worker 心跳过期”“无效仓库地址”“部分完成任务”或“任务失败与重试”。Mock 只读取本地 JSON/CSV fixture；添加与任务状态转变按固定 fixture 顺序回放，不生成临时统计值。

若 API 端点没有匹配的 fixture，Mock 会显示明确缺失提示。Mock 数值是演示样例，不能当成实时 GitHub 数据。
