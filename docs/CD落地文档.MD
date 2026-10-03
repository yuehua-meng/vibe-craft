


## 简历可写


1. 容器化与线上部署（Docker + Docker Compose + Caddy） 使用 Dockerfile（python:3.13-slim + 锁文件分层构建，改代码不重装依赖）与 Docker Compose 双服务编排完成上线：应用容器不映射宿主机端口，仅由 Caddy 对外承担 TLS 终结、Basic Auth 与反向代理，缩小攻击面；SQLite 与断点文件通过 bind mount 落盘宿主机，配合 healthcheck 与`restart: unless-stopped` 实现进程异常与机器重启后自愈。已在腾讯云 Ubuntu 24.04 实机部署，并从公网验证鉴权、健康检查与数据持久化全部生效。
2. 一键部署脚本（幂等 + 零手工步骤） 编写幂等`deploy.sh` 将发布收敛为单条命令：自动完成 Docker/Compose 环境自检、`.env` 与访问凭证缺失检测、bcrypt 口令哈希生成（哈希文件 gitignore，不入仓库）、`git pull --ff-only` 、镜像重建、容器滚动更新，并轮询`/api/health` 通过后才判定成功（失败即打印日志并退出）；同时支持「无域名先用 IP + Basic Auth 临时上线」与「拿到域名后一条命令切自动签发 HTTPS」两种路径。


压缩版：


- 容器化与线上部署（Docker + Docker Compose + Caddy） Dockerfile 分层构建 + Compose 双服务编排，Caddy 承担 TLS 与鉴权反代，数据落盘持久化，容器异常自愈。
- 一键部署脚本（幂等 + 零手工步骤） 幂等`deploy.sh` 串联环境自检、凭证生成、拉码、镜像重建、滚动更新与健康检查，发布收敛为单条命令，支持 IP 与 HTTPS 两种路径。



## 一、自动化靠什么实现（仓库里新增的 5 个东西）

1. **`Dockerfile`** —— 把应用打包成镜像。基于 `python:3.13-slim`；先拷 `requirements.lock.txt` 再 `pip install`（利用 Docker 层缓存，改代码不必重装依赖）；只拷 `app/`、`web/`、`run.py`；启动命令 `python run.py`。
2. **`run.py` 支持 `APP_HOST`** —— 本地默认仍是 `127.0.0.1`，容器里由 compose 注入 `0.0.0.0`。同一份代码适配两种环境，本地行为零变化。
3. **`docker-compose.yml`（两个服务）**
   - `app`：**不映射宿主机端口**，只在内网；`./data` 挂到 `/app/data`（SQLite 与断点持久化）；自带 healthcheck；`restart: unless-stopped`（进程崩溃或重启机器后自动拉起）。
   - `caddy`：对外只开 80/443，负责 HTTPS 终结 + Basic Auth，反向代理到 `app:8010`；证书放在 `caddy_data` 命名卷，避免重建容器时重复向 Let's Encrypt 申请。
4. **`deploy/Caddyfile.template` + `deploy/deploy.sh`** —— 模板里不含任何密码；脚本运行时交互式生成真正的 `deploy/Caddyfile`（写入 bcrypt 哈希，该文件已 gitignore）。
5. **`.dockerignore` / `.gitignore`** —— 构建上下文排除 `.venv`、`data/`；含密码哈希的 `Caddyfile` 永不进仓库。

> 需要说清楚一点：**触发方式是"你在服务器上执行一条命令"，不是 push 自动上线**——这是你当初选的方案（另一条路是 GitHub Actions 接 SSH 自动部署，需要配 GitHub Secrets）。所以"自动化"体现在**一条命令完成全部更新动作**，而不是"提交即上线"。

## 二、`./deploy/deploy.sh` 一条命令内部做了 8 步（幂等，可反复执行）

1. 定位脚本所在的仓库根目录
2. 检查 `docker` 与 compose 插件；缺失时 `--install-docker` 会走 Docker 官方 apt 源安装
3. 检查 `.env`：不存在就从 `.env.example` 复制并**退出**，提示你填 `ARK_API_KEY`
4. 检查 `deploy/Caddyfile`：不存在就依次问域名、访问用户名、密码（`read -s` 不回显），调 `caddy hash-password` 生成 bcrypt 填进模板，并 `chmod 600`
5. `git pull --ff-only` 拉最新代码
6. `docker compose build --pull app` 重建镜像
7. `docker compose up -d --remove-orphans` 启动/滚动替换容器
8. 循环探测容器内 `/api/health` 直到通过；超时则打印最近日志并**以失败退出**；最后打印访问地址与运维命令

## 三、我在你这台服务器上实际执行的 8 步

1. 探测环境：Ubuntu 24.04、x86_64、4 核 3.7G，**Docker 29.6.1 已装**、sudo 可用、公网 22 端口通
2. `usermod -aG docker ubuntu` —— 让 ubuntu 用户免 sudo 用 docker
3. `git clone` 到 `/home/ubuntu/vibe-craft`（仓库公开，无需凭据）
4. 写入 `.env`（从你本机配置带过去，含 ARK key，权限 600）
5. 生成 **IP 模式**的 `deploy/Caddyfile`（因为当时还没域名）：`:80` 监听 + `basic_auth` + 反代 8010，无 TLS
6. `docker compose build app` 构建镜像
7. `docker compose up -d` 启动 `app` + `caddy`
8. 验证：公网 401（无凭证）/ 200（有凭证）/ `/api/health` 返回正常 / `data/app.db` 确实落在宿主机

## 补充两点

- **切到域名 + HTTPS** 时只需一条命令：`rm deploy/Caddyfile && ./deploy/deploy.sh`，它会重新问域名并自动签证书（记得先在安全组放行 **443**）。
- 当前状态是"IP 模式的临时配置"，`deploy.sh` 的域名流程没有被走过；脚本末尾打印的地址在那时仍会写成 `https://xxx`，这是它按域名模式写死的输出
