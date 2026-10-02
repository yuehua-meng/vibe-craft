# 上传图文 → 图文生成

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一个可直接运行的本地营销工作台。员工上传商品图片和文字，勾选平台，经过选题确认和文章审核，再生成摘要、配图及图文成品。

技术栈：**FastAPI + LangGraph + 原生 JavaScript/CSS + 火山方舟 API**。无需 Node 构建、独立数据库服务、Redis 或 Docker。

## 效果预览

下图是火山方舟真实模式下的成品页：选题、文章、摘要、配图与图文编排全部完成后，可复制文章、打开完整 HTML 预览，或下载素材包。

![工作台成品页](docs/验收截图.jpg)

## 启动

Windows 双击 **`start.cmd`**，或在项目目录运行：

```powershell
.\start.ps1
```

打开 <http://127.0.0.1:8010>。接口文档：<http://127.0.0.1:8010/docs>。

当前目录已准备 `.venv` 和依赖。复制到其他机器时删除原虚拟环境，并重新创建：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe run.py
```

要求 Python 3.11+；当前验证环境为 Python 3.13。默认单进程监听 `127.0.0.1`，容器化部署见下文[服务器部署](#服务器部署腾讯云-ubuntu--docker)。

## 使用流程

1. 上传 1–4 张 JPG/PNG/WebP 商品图，每张不超过 8 MB；填写商品名称、描述、创作要求。
2. 勾选小红书、微信公众号、X / Twitter，可以同时选择多个平台。
3. 选择生成方式，点击“开始生成选题”。
4. 每个平台生成 3 个候选选题。员工选择一个确认，或填写反馈重新生成。
5. 文章生成后暂停，员工可直接编辑通过，也可提交修改意见或退回选题。
6. 审核通过后，依次执行摘要生成、原图与摘要联合生图、图文编排。
7. 复制文章、打开完整 HTML 预览，或下载包含文章、配图、HTML 与元数据的 ZIP 素材包。

点击“试用示例素材”会填入虚构商品，同时切换到**本地演示模式**。演示模式的文字是模板数据，图片是本地模板合成，界面与成品中均明确标注；它不调用付费模型。切换为“火山方舟”后才调用真实模型。真实接口错误不会自动降级到演示模式。

## 火山方舟配置

密钥只读取项目根目录的 `.env`，后端使用，前端不能读取。`.env` 已加入 `.gitignore`，示例配置不含密钥。

```dotenv
ARK_API_KEY=填写自己的密钥
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_TEXT_MODEL=doubao-seed-2-0-lite-260428
ARK_IMAGE_MODEL=doubao-seedream-4-0-20260415
APP_PORT=8010
```

配置变更后重启服务。也可以通过系统环境变量覆盖。模型可填写账户可用的 Model ID 或 `ep-...` 推理接入点；文本模型需要支持视觉输入、JSON 输出和当前调用参数，图片模型需要支持图生图和 `b64_json`。

该版本已验证上述两个模型的真实文本调用与原图参考生图。账户模型权限、配额或生命周期发生变化时，以控制台实际可用模型为准。

```powershell
# 最小真实文本调用（会消耗少量模型额度）
.\.venv\Scripts\python.exe smoke_ark.py
# 文本调用 + 生成一张参考图（会产生生图费用）
.\.venv\Scripts\python.exe smoke_ark.py --image
# 只读查询官方模型目录；目录存在不等于账户已开通
.\.venv\Scripts\python.exe inspect_models.py
```

## Mock 数据说明

- `MockRepository` 使用内存字典保存业务任务、版本和审核记录。
- LangGraph 使用 `InMemorySaver` 保存暂停点和执行状态。
- **重启后任务与暂停点清空，不能恢复上次进程的审核任务。** 这与生产数据库持久化不同。
- 原图、生成图片及导出文件保存在 `data/`。重启不删除已有文件，但旧任务不会自动重新出现在列表。
- 服务只启动一个进程；不要增加 `workers`，否则不同进程的内存状态不共享。

## 项目结构

```text
上传图文-图文生成/
├── app/
│   ├── main.py           # 上传、任务、审核、重试 API 与静态页面
│   ├── workflow.py       # 真正的 LangGraph StateGraph、interrupt、Command
│   ├── providers.py      # 火山方舟模型适配与独立 MockProvider
│   ├── repository.py     # MockRepository，无数据库连接
│   ├── schemas.py        # 请求与模型输出结构校验
│   ├── media.py          # 图片校验、本地示例、HTML 与 ZIP 导出
│   └── config.py         # 环境配置与平台风格
├── web/                  # 工作台界面，不需要 npm install
├── tests/                # 工作流与接口测试
├── deploy/               # 服务器部署：deploy.sh 与 Caddy 模板
├── docs/architecture.md  # Mermaid 架构和工作流
├── data/                 # 运行时素材，已忽略 Git
├── Dockerfile
├── docker-compose.yml    # app + Caddy 编排，见「服务器部署」
├── requirements.lock.txt # 已安装并验证的依赖快照
├── .env.example          # 无密钥的配置示例
├── run.py
├── start.ps1
└── start.cmd
```

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
node --check web/app.js
```

测试覆盖三平台完整流程、人工编辑后的摘要输入、选题重做、文章修订、退回选题、过期与重复审核拦截、失败节点重试、上传校验、HTML 转义、跨站请求拦截、Mock 重启语义，以及原图和摘要确实传入方舟接口。

## 本地原型的边界

- 当前每个平台生成一张配图，提供平台化文案、对应图片比例以及 HTML/文本/ZIP 导出，不自动发布到外部平台。
- 生成图片检查包括格式、可解码性与像素上限；未接入独立视觉模型进行商品一致性自动打分，实际使用前需核对生成图片。
- 本版无登录、企业权限和持久队列；数据已用 SQLite 持久化，适合单进程部署的内网小团队。若要开放给公司员工共同使用或扩展到多实例，需要增加身份权限体系，并把仓库升级为 PostgreSQL、Checkpointer 换成 PostgresSaver、引入外部队列。
- 不自动反复重试付费生图。失败时保留之前的审核结果，由员工发起当前节点重试，最多 3 次；超时后重试可能重复计费，应先检查供应商调用记录。
- 前端采用轻量轮询更新进度；审核期间不会占用运行任务，后台 asyncio 调度允许三个平台并发运行。

## 服务器部署（腾讯云 Ubuntu + Docker）

仓库自带容器化部署：应用只在 Docker 内网监听 8010，Caddy 负责 HTTPS 与入口鉴权，对外只暴露 80/443。应用本身没有登录体系，因此**不建议跳过 Basic Auth 直接暴露到公网**。

前提：Ubuntu 22.04 / 24.04；腾讯云安全组放行 `80`、`443`；域名 A 记录已指向服务器。

首次部署：

```bash
git clone https://github.com/yuehua-meng/vibe-craft.git ~/vibe-craft
cd ~/vibe-craft
cp .env.example .env && vi .env        # 填入 ARK_API_KEY
chmod +x deploy/deploy.sh
./deploy/deploy.sh                     # 未装 Docker 时，先执行 ./deploy/deploy.sh --install-docker
```

首次运行会依次询问域名、访问用户名与密码（密码不回显），生成 `deploy/Caddyfile` 后由 Caddy 自动签发 Let's Encrypt 证书。密码只落在服务器的 `.env` 与 `deploy/Caddyfile` 里，两者都已被 Git 忽略。

日常更新只需再执行一次 `./deploy/deploy.sh`，它依次完成 `git pull` → 重建镜像 → 重启 → 健康检查；任一步失败会中断并输出日志。

运维：

```bash
docker compose logs -f app      # 应用日志
docker compose logs -f caddy    # 证书签发与访问日志
docker compose restart app      # 重启应用
tar czf ~/vibe-craft-data-$(date +%F).tar.gz data   # 备份业务数据与工作流断点
rm deploy/Caddyfile && ./deploy/deploy.sh          # 重置访问用户名与密码
```

`data/` 保存 `app.db` 与 `checkpoints.db`，是唯一的持久化位置（bind mount 到宿主机），升级和重建容器都不要删除。

注意：`deploy/Caddyfile` 由脚本首次生成。如果先手工执行了 `docker compose up`，Docker 会把不存在的挂载点建成目录，此时需要 `rm -rf deploy/Caddyfile` 后再运行脚本。

## 开源协议

本项目采用 [MIT License](LICENSE) 开源，可自由使用、修改和分发，只需保留版权与许可声明。
