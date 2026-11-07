# 阿里云 ECS 部署指南

## 建议资源

个人使用、30～100 只 ETF/LOF、只存日线和行情快照时：

- 2 vCPU；
- 4 GiB 内存起步；
- 40～80 GiB ESSD；
- Alibaba Cloud Linux 3/4 或 Ubuntu LTS；
- 固定公网 IP 或域名；
- 定期快照不是数据库逻辑备份的替代品。

若后续存储全市场分钟线或运行 ML 训练，单独扩容，不要在生产 API 容器里训练。

## 安全组

推荐入站规则：

| 端口 | 来源 | 用途 |
|---|---|---|
| 22/TCP | 你的固定公网 IP/32 | SSH |
| 80/TCP | 0.0.0.0/0（有域名时） | ACME/跳转 HTTPS |
| 443/TCP | 0.0.0.0/0 或仅你的 IP | HTTPS 看板 |

不要开放：

- 5432 PostgreSQL；
- 8080 应用内部端口；
- 2375/2376 Docker API；
- 全端口 `1/65535`。

应用 Compose 已将 8080 绑定 `127.0.0.1`，数据库没有宿主机端口映射。

阿里云官方安全组文档强调最小权限，80/443 可按需公开，而 SSH/管理端口应限制到可信 IP；新的基础安全组除组内通信外默认拒绝其他入站。参考：

- https://www.alibabacloud.com/help/en/ecs/user-guide/start-using-security-groups
- https://www.alibabacloud.com/help/en/ecs/user-guide/best-security-practices

## 1. 安装 Docker

项目提供：

```bash
sudo bash deploy/aliyun/bootstrap_host.sh
```

脚本优先识别 Alibaba Cloud Linux，使用阿里云内网镜像仓库或 Alibaba Cloud Linux 4 的 Moby；不适配时才回退 Docker 官方安装脚本。安装方式应与阿里云当前文档核对：

https://www.alibabacloud.com/help/en/ecs/user-guide/install-and-use-docker

## 2. 上传源码

```bash
sudo mkdir -p /opt/china-fund-decision
sudo chown "$USER":"$USER" /opt/china-fund-decision
cd /opt/china-fund-decision
# git clone 私有仓库，或上传解压本交付包
```

不要把第三方完整 Git 历史放到生产 ECS；`vendor/src` 默认忽略。

## 3. 配置

```bash
cp deploy/.env.production.example .env
python3 scripts/generate_secrets.py
chmod 600 .env
```

填入真实值。建议先保持：

```env
LLM_ENABLED=false
SCHEDULER_ENABLED=false
```

浏览器认证使用数据库账户：显式设置 `AUTH_ENABLED=true`，使用 PostgreSQL `DATABASE_URL`、保持
`AUTO_CREATE_SCHEMA=false` 与 `AUTH_COOKIE_SECURE=true`，完成迁移后在服务器本地运行
`fund-decision auth-bootstrap-admin` 创建首个管理员。浏览器提交用户名和原始密码，
会话只存在 Secure HttpOnly SameSite cookie。不要保存或回显明文密码。
生产环境不得配置 `AUTH_USERNAME`、`AUTH_EMAIL`、`AUTH_PASSWORD_HASH`、`AUTH_SESSION_SECRET` 或旧 Bearer 凭据。

说明：scheduler 进程同时受 Compose 是否启动和 `SCHEDULER_ENABLED` 控制。首次冒烟建议保持 `false`，完成数据核验后改为 `true` 并启动 scheduler service。

## 4. 构建

```bash
set -a; source .env; set +a
POSTGRES_PASSWORD="$POSTGRES_PASSWORD" docker compose config
sudo bash deploy/aliyun/deploy.sh
```

部署脚本会：

1. 检查 `.env`；
2. 调整 reports/backups 的容器写权限；
3. 构建镜像；
4. 启动 PostgreSQL/API；
5. 等待健康检查；
6. 同步标的和执行 Provider smoke；
7. 拉取历史数据并初始化；
8. 启动 scheduler。

若希望先人工审查 Provider，请手动分步执行而不是直接运行完整脚本。

## 5. 临时私有访问

最安全的首次访问方式是 SSH 隧道：

```bash
ssh -L 8080:127.0.0.1:8080 user@ecs-public-ip
```

本机浏览器访问 `http://127.0.0.1:8080`。

## 6. Caddy HTTPS

安装 Caddy 后复制并修改：

```bash
sudo cp deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

需要：

- 域名 A/AAAA 记录；
- 安全组开放 80/443；
- `fund.example.com` 改成真实域名；
- 可增加 Caddy Basic Auth；浏览器仍使用应用账户密码会话。`PRIVATE_ACCESS_TOKEN` 仅是非生产迁移/测试兼容项；生产数据库账户认证会拒绝该配置，不能保留或作为部署凭据。

使用 Nginx 时必须关闭 `/api/events` 的代理缓冲并把 read timeout 调长，示例已包含。反代必须覆盖客户端传来的 `X-Forwarded-For`，而 Compose/Dockerfile 已禁用 Uvicorn proxy-header trust，登录限流不会接受任意转发链。

## 7. 云盘和备份

每日：

```bash
./scripts/backup_postgres.sh
```

建议：

- 本地保留 30 天；
- 另传 OSS 私有 Bucket；
- OSS 使用 RAM 最小权限和服务端加密；
- 定期在临时 PostgreSQL 恢复；
- 不把 `.env` 包进备份。

## 8. 日志和监控

Compose 将每个容器日志限制为 20 MiB × 5。至少监控：

- API health；
- 容器重启次数；
- 磁盘空间；
- PostgreSQL 连接和备份失败；
- Provider 连续失败；
- 盘中实时行情数量；
- scheduler 最近成功任务时间。

可先使用阿里云云监控和简单 HTTP 探针，不必第一天就引入完整 Prometheus/Grafana。

## 9. 更新和回滚

更新：

```bash
sudo bash deploy/aliyun/update.sh
```

脚本先备份，再 `git pull --ff-only`、构建并重启。正式更新前还应记录旧 commit 和数据库迁移版本。

回滚代码：

```bash
git checkout <previous-good-commit>
docker compose build
docker compose up -d --remove-orphans
```

数据库迁移回滚需逐版本审查，不应盲目 `alembic downgrade -1`。
