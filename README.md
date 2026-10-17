# GitHubDA

GitHub 开源项目分析台，包含 Vue 3 前端、FastAPI、SQLite 和采集 Worker。

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

Mock 模式不需要启动后端：

```bash
cd web
npm ci
npm run dev
```

若要从 Vite 开发服务器联调真实 API，先用一键启动命令启动本地服务，再以 `VITE_DATA_MODE=http npm run dev` 启动开发前端。

后端配置与 API 说明见 [README_backend.md](README_backend.md)。
