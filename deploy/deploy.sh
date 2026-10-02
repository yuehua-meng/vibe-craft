#!/usr/bin/env bash
# 一键部署：拉取代码 → 重建镜像 → 重启服务 → 健康检查。
# 可重复执行；密码只在服务器本地输入，不写入仓库。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

CADDY_IMAGE="caddy:2-alpine"
INSTALL_DOCKER=0

case "${1:-}" in
    --install-docker) INSTALL_DOCKER=1 ;;
    -h|--help)
        cat <<'USAGE'
用法：./deploy/deploy.sh [--install-docker]

  --install-docker   未安装 Docker 时，先用官方 apt 源安装 Docker 与 compose 插件

首次运行会依次要求输入：已解析到本机的域名、访问用户名、访问密码。
USAGE
        exit 0
        ;;
    "") ;;
    *) echo "未知参数：$1（可用 --help 查看用法）" >&2; exit 1 ;;
esac

log() { printf '\033[32m[deploy]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[deploy]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[deploy]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------- 1. 环境检查 ----------

if ! command -v docker >/dev/null 2>&1; then
    if [ "$INSTALL_DOCKER" != 1 ]; then
        die '未检测到 docker。可执行：./deploy/deploy.sh --install-docker'
    fi
    log '通过 Docker 官方 apt 源安装 Docker'
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl gnupg
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg |
        sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" |
        sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
    sudo usermod -aG docker "$USER" || true
    warn "Docker 已安装，但当前 shell 还没拿到 docker 组权限。"
    warn "请退出登录后重新连接（或新开一个终端），再运行 ./deploy/deploy.sh"
    exit 0
fi

docker compose version >/dev/null 2>&1 ||
    die 'docker 已安装但缺少 compose 插件（docker compose version 执行失败）'
docker info >/dev/null 2>&1 ||
    die '当前用户无权访问 Docker：请用 sudo 运行，或把用户加入 docker 组后重新登录'

# ---------- 2. 应用配置 ----------

if [ ! -f .env ]; then
    cp .env.example .env
    warn '已从 .env.example 生成 .env'
    die '请编辑 .env 填写 ARK_API_KEY（例如 vi .env），然后重新运行本脚本'
fi
grep -qE '^ARK_API_KEY=.+' .env ||
    warn '.env 里 ARK_API_KEY 为空：界面可以使用演示模式，但无法调用真实模型'

# ---------- 3. 反向代理与访问口令 ----------

if [ ! -f deploy/Caddyfile ]; then
    log '首次部署：生成 Caddy 配置与访问口令'
    read -rp '域名（已解析到本机，如 craft.example.com）: ' DOMAIN
    [ -n "$DOMAIN" ] || die '域名不能为空'
    read -rp '访问用户名: ' AUTH_USER
    [ -n "$AUTH_USER" ] || die '用户名不能为空'
    read -rsp '访问密码: ' AUTH_PASS
    echo
    [ -n "$AUTH_PASS" ] || die '密码不能为空'

    log "生成 bcrypt 哈希（首次会拉取 $CADDY_IMAGE）"
    AUTH_HASH="$(docker run --rm "$CADDY_IMAGE" caddy hash-password --plaintext "$AUTH_PASS")"
    [ -n "$AUTH_HASH" ] || die '生成密码哈希失败'

    # bcrypt 串含 $ 与 /，sed 用 | 作分隔符避免转义问题。
    sed -e "s|__DOMAIN__|$DOMAIN|" \
        -e "s|__BASIC_AUTH_USER__|$AUTH_USER|" \
        -e "s|__BASIC_AUTH_HASH__|$AUTH_HASH|" \
        deploy/Caddyfile.template >deploy/Caddyfile
    chmod 600 deploy/Caddyfile
    unset AUTH_PASS AUTH_HASH
    log '配置已写入 deploy/Caddyfile（含密码哈希，不要提交到 Git）'
else
    log '已存在 deploy/Caddyfile，沿用当前域名与访问口令'
fi

# ---------- 4. 更新代码 ----------

if git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    log '拉取最新代码'
    git -C "$REPO_ROOT" pull --ff-only
else
    warn '当前目录不是 git 仓库，跳过代码更新'
fi

# ---------- 5. 构建并启动 ----------

log '构建应用镜像'
docker compose build --pull app

log '启动服务'
docker compose up -d --remove-orphans

log '等待应用就绪'
HEALTHY=0
for _ in $(seq 1 30); do
    if docker compose exec -T app python -c \
        "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8010/api/health', timeout=3).status == 200 else 1)" \
        >/dev/null 2>&1; then
        HEALTHY=1
        break
    fi
    sleep 2
done
if [ "$HEALTHY" != 1 ]; then
    docker compose logs --tail 50 app
    die '应用未在 60 秒内通过健康检查，已输出最近日志'
fi

# ---------- 6. 结果与运维提示 ----------

DOMAIN_SHOWN="$(awk '!/^#/ && NF {print $1; exit}' deploy/Caddyfile)"

cat <<EOF

部署完成。
  访问地址：https://${DOMAIN_SHOWN}
  浏览器首次访问会要求输入刚才设置的用户名与密码。

常用命令（在 $REPO_ROOT 下执行）：
  查看应用日志   docker compose logs -f app
  查看证书日志   docker compose logs -f caddy
  重启应用       docker compose restart app
  停止服务       docker compose down
  备份数据       tar czf ~/vibe-craft-data-\$(date +%F).tar.gz data
  重置访问口令   rm deploy/Caddyfile && ./deploy/deploy.sh

注意：
  - 腾讯云安全组需要放行 80 与 443，否则证书签发会失败。
  - data/ 保存 app.db 与 checkpoints.db，是唯一的持久化位置，升级时不要删除。
  - 应用内部端口固定 8010，请不要给 app 服务添加 ports 映射。
EOF
