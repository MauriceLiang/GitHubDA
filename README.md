# GitHubDA

GitHub 开源项目分析台，包含 FastAPI、SQLite、采集 Worker 和 Streamlit 前端。

## 一键启动

需要 Python 3.12 和 [uv](https://docs.astral.sh/uv/)。在仓库根目录运行：

```bash
uv run --locked --all-extras python -m scripts.start
```

命令会按 `uv.lock` 准备依赖、自动创建本地 `.env` 和随机 `INTERNAL_API_KEY`、升级数据库，然后启动 API、Worker 和前端。服务地址：

- 前端：<http://127.0.0.1:8501>
- API 文档：<http://127.0.0.1:8000/docs>
- API 健康检查：<http://127.0.0.1:8000/healthz>

按 `Ctrl+C` 会一并停止三个服务。`.env` 中的 `GITHUB_TOKEN` 可选；不配置时使用 GitHub 匿名额度。

要允许同一局域网内的人员访问前端：

```bash
uv run --locked --all-extras python -m scripts.start --frontend-host 0.0.0.0
```

API 默认仍只监听本机。需要调整端口时可传入 `--api-port` 或 `--frontend-port`。
局域网内通过运行机器的 IP 和前端端口访问；当前 Streamlit 页面没有用户登录，仅应绑定到可信网络。

## 分别调试

后端和前端的独立启动、配置与验证说明分别见 [README_backend.md](README_backend.md) 和 [frontend/README_frontend.md](frontend/README_frontend.md)。
