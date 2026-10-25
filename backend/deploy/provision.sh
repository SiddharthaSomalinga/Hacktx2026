#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 Vultr instance (D36). Run as root on the server:
#   bash provision.sh https://github.com/<owner>/<repo>.git
set -euo pipefail

repo_url=${1:?usage: provision.sh <git clone url>}
app_dir=/opt/ghostseats
env_file=/etc/ghostseats.env

apt-get update -q
apt-get install -y -q docker.io docker-compose-v2 docker-buildx git
systemctl enable --now docker

if [ ! -d "$app_dir/.git" ]; then
  git clone --quiet "$repo_url" "$app_dir"
fi

# Secrets live only here: root-owned, mode 600, outside the checkout.
if [ ! -f "$env_file" ]; then
  install -m 600 -o root -g root /dev/null "$env_file"
  echo "created empty $env_file: fill it in (see backend/.env.example) before deploying"
fi

docker --version
docker compose version
