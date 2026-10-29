# 部署与模型配置

## 本地与容器

使用 Python 3.12+。先运行 `pip install -r requirements.lock`、`pip install -e .`，
再分别启动 API 和 UI。API 的导入路径为 `paperpilot.api:create_app --factory`。
Web 是 `streamlit run paperpilot/ui.py --server.headless true`。

Windows PowerShell 创建和启动虚拟环境：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock
.\.venv\Scripts\python -m pip install -e '.[dev]'
Copy-Item .env.example .env
.\.venv\Scripts\python -m uvicorn paperpilot.api:create_app --factory --host 127.0.0.1 --port 8000
# 另开终端：
.\.venv\Scripts\python -m streamlit run paperpilot/ui.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

Docker Compose 默认监听 `127.0.0.1:8000`（API）和 `127.0.0.1:8501`（Web），
镜像普通用户 UID 10001 运行。SQLite、片段、事件和 checkpoint 保存在命名卷。
`.dockerignore` 排除密钥、运行数据、工具与 Git；不要把 `.env` COPY 进镜像。

```bash
docker compose up -d --build --wait
docker compose ps
docker compose logs --tail=80
curl -f http://127.0.0.1:8000/health
curl -f http://127.0.0.1:8501/_stcore/health
```

Docker Hub 不可达时，可以从官方 Docker 镜像的 Amazon ECR 分发源构建：

```bash
docker build --build-arg BASE_IMAGE=public.ecr.aws/docker/library/python:3.12-slim \
  --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
  -t paperpilot-agent:local .
docker compose up -d --no-build --wait
```

包镜像可能短暂缺少新版本，Dockerfile 保留官方 PyPI 回源地址。项目使用锁定
依赖版本；不要为绕过网络问题任意升级或混用 MCP v1/v2。

`docker compose down` 停止容器，保留数据卷；不要在需要保留分析记录时使用 `-v`。
修改 `.env` 的模型配置后运行 `docker compose up -d --force-recreate api`，
重建 API 容器让配置生效。该操作会中断运行中的任务。

## 无 Docker 的服务器

在服务器创建独立项目目录与虚拟环境：

```bash
python3 -m venv /path/to/paperpilot-venv
/path/to/paperpilot-venv/bin/python -m pip install -r requirements.lock
/path/to/paperpilot-venv/bin/python -m pip install -e .
bash deploy/install-user-service.sh /path/to/PaperPilot-Agent /path/to/paperpilot-venv
```

Debian/Ubuntu 未安装 `python3-venv` 时，可由管理员安装；或使用官方 uv 创建和
管理用户环境。部署脚本创建 `paperpilot-api.service` 与 `paperpilot-web.service`，
端口分别为 18080 和 18501，仅本机可访问。

```bash
systemctl --user status paperpilot-api paperpilot-web
systemctl --user restart paperpilot-api
journalctl --user -u paperpilot-api -n 100 --no-pager
systemctl --user stop paperpilot-api paperpilot-web
```

用户级服务若需要在无登录会话及重启后持续运行，需要管理员启用相应用户的
linger；Docker Compose 的 `unless-stopped` 则由已启用的 Docker 服务管理。
启用后可通过 `systemctl --user is-enabled` 检查配置，并在计划维护时验证重启行为。

## SSH 访问

个人工作区推荐本机 SSH 端口转发，避免公开暴露无认证实例：

```bash
# 用户级服务端口
ssh -N -L 18501:127.0.0.1:18501 -L 18080:127.0.0.1:18080 user@server
# 或容器部署端口
ssh -N -L 8501:127.0.0.1:8501 -L 8000:127.0.0.1:8000 user@server
```

然后访问本机对应 Web 端口。不需要给容器传入 GPU 设备，也不需要修改防火墙
开放应用端口。当前历史任务和文档对该实例的使用者共享，不提供多租户隔离。

## OpenAI 兼容模型与百炼

运行 `python scripts/configure_model.py` 可隐藏输入 key，并在 Linux 用 0600 权限
保存项目根目录 `.env`。该脚本不调用模型，也不检查账户余额。重启 API 后才能
生效。每个 Live 任务在向模型发送内容前都需要独立确认。

百炼北京地域可使用以下兼容配置，也可采用控制台提供的业务空间专属域名：

```dotenv
PAPERPILOT_MODE=live
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=your-enabled-model-code
OPENAI_API_KEY=your-private-key
PAPERPILOT_MODEL_EXTRA_BODY={"enable_thinking":false}
```

Base URL、模型权限和 key 必须匹配地域。API key 不代表免费资格；实时调用
是否抵扣免费额度以该账户、模型 Code、额度有效期为准。希望只使用免费额度时，
先在控制台确认余量并启用该模型的“免费额度用完即停”，等待生效。

上面的额外 JSON 参数用于百炼支持关闭思考的混合模型，其他服务默认保持 `{}`。设置来自供应商官方接口，
不是对模型名称硬编码特殊逻辑。实际模型响应的 token 用量与结束原因记录在任务事件中。

正常任务调用模型两次：规划、报告。引用不合法时最多增加一次模型纠正，
再次失败即停止，因而一个任务最多三次模型调用。单次输出上限 5000 token，网络请求不自动重试；
无任意开放的工具循环。模型必须输出符合 schema 的 JSON，错误如实报告。
某些推理模型要求供应商特定参数，若不能遵守当前标准聊天调用协议，应选择
兼容的非推理模型或在验证后添加对应配置，不能称所有模型已经兼容。

官方依据（查询于 2026-10-29）：
[百炼接入域名](https://help.aliyun.com/zh/model-studio/beijing-access-information)、
[OpenAI 兼容](https://docs.bailian.console.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)、
[免费额度规则](https://help.aliyun.com/zh/model-studio/new-free-quota)、
[DeepSeek 思考参数](https://help.aliyun.com/zh/model-studio/deepseek-api)。

## 运行与保留

- 每个 API 实例使用单 worker，进程内最多 2 个并发任务、队列共 8 个。
- 等待确认的图 checkpoint 持久化；服务重启时执行中的任务标为失败，需重新创建。
- 源 PDF 二进制不持久化，提取文本、文件名及哈希会保存在 SQLite。
- 仓库最多读取 24 个文件；查看报告中的采样清单，不能当作全仓库覆盖。
- 分享源码前使用 `git ls-files` 核对文件；不分享 data 卷、`.env` 或未获授权的 PDF。

## 已有 Agent 与主机 Runner

CLI/MCP 的证据模式不需要 Web 或额外模型 key。读取项目中的
`agent-skills/paperpilot-reproduce/SKILL.md`，然后使用虚拟环境的 `paperpilot` 命令。
外部 Agent 生成分析和配方，PaperPilot 提供固定版本证据及指标比较。

Runner 单独安装在有 Docker 的主机，Web 不挂载 Docker socket，也不启动实验
代码。Windows 使用 Docker Desktop 的 Linux 容器模式；真实 CPU 实验已在 Linux
Docker Engine 验证，Windows Docker Desktop 的实验执行尚未实机验证。
镜像与适配器准备、具体运行批准和结果导入见 [复现流程](reproduction.md)。

从 0.1 更新时保留命名卷，重建 API/Web 镜像即可。Store 会创建 results 表，旧来源
和研究任务保留；旧任务没有 structured_report 时页面仍可显示 Markdown。更新会
中断执行中的研究任务，应在无运行任务时操作。Runner 记录独立保存在主机 data/runs。
