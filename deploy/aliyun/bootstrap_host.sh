#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then echo "Run as root: sudo $0" >&2; exit 1; fi
export TZ=Asia/Shanghai

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  source /etc/os-release
else
  ID=unknown
  VERSION_ID=unknown
fi

if command -v dnf >/dev/null 2>&1; then
  dnf install -y git curl wget ca-certificates jq tar gzip tzdata || true
elif command -v yum >/dev/null 2>&1; then
  yum install -y git curl wget ca-certificates jq tar gzip tzdata || true
elif command -v apt-get >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y git curl wget ca-certificates jq tar gzip tzdata
else
  echo "Unsupported package manager; install Docker Engine and Compose v2 manually." >&2
fi

if ! command -v docker >/dev/null 2>&1; then
  if [[ "${ID:-}" == "alinux" && "${VERSION_ID%%.*}" == "4" ]]; then
    echo "Installing Alibaba Cloud Linux 4 native Moby runtime..."
    yum install -y moby docker-compose-plugin || true
  elif [[ "${ID:-}" == "alinux" ]]; then
    echo "Installing Docker CE from Alibaba Cloud internal mirror..."
    wget -O /etc/yum.repos.d/docker-ce.repo http://mirrors.cloud.aliyuncs.com/docker-ce/linux/centos/docker-ce.repo
    sed -i 's|https://mirrors.aliyun.com|http://mirrors.cloud.aliyuncs.com|g' /etc/yum.repos.d/docker-ce.repo
    if command -v dnf >/dev/null 2>&1; then
      dnf -y install dnf-plugin-releasever-adapter --repo alinux3-plus || true
      dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    else
      yum -y install yum-plugin-releasever-adapter --disablerepo='*' --enablerepo=plus || true
      yum -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    fi
  fi
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Native installation was unavailable; falling back to Docker's official installer."
  curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
  sh /tmp/get-docker.sh
  rm -f /tmp/get-docker.sh
fi

systemctl enable --now docker
docker version
docker compose version
mkdir -p /opt/china-fund-decision
chmod 750 /opt/china-fund-decision

echo "Host bootstrap complete. Configure ECS security groups separately before exposing the domain."
