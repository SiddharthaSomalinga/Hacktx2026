#!/usr/bin/env bash
# Rolling deploy of one pushed commit to every instance, one at a time (D36). From your laptop:
#   HOSTS="root@<ip-1> root@<ip-2>" backend/deploy/deploy.sh [git-ref, default origin/v1final]
# Each host must be healthy before the next is touched, so a failed build or a crash-looping
# container stops the rollout while the remaining hosts keep serving the previous version.
set -euo pipefail

hosts=${HOSTS:?set HOSTS to the ssh targets, e.g. HOSTS="root@1.2.3.4 root@5.6.7.8"}
ref=${1:-origin/v1final}
frontend_dir=${FRONTEND_DIR:-frontend}
remote_dir=${REMOTE_DIR:-/opt/ghostseats}
health_timeout_s=${HEALTH_TIMEOUT_S:-180}

git fetch --quiet origin
sha=$(git rev-parse --verify "$ref^{commit}")
if ! git branch -r --contains "$sha" | grep -q .; then
  echo "commit $sha is not on origin; push it first (the servers pull from GitHub)" >&2
  exit 1
fi
echo "deploying $sha ($ref) with FRONTEND_DIR=$frontend_dir"

for host in $hosts; do
  echo "== $host"
  ssh "$host" bash -s -- "$sha" "$frontend_dir" "$remote_dir" "$health_timeout_s" <<'REMOTE'
set -euo pipefail
sha=$1 frontend_dir=$2 remote_dir=$3 timeout_s=$4
cd "$remote_dir"
git fetch --quiet origin
git checkout --quiet --detach "$sha"
export COMPOSE_PROJECT_NAME=ghostseats GIT_SHA=$sha FRONTEND_DIR=$frontend_dir
docker compose -f backend/deploy/compose.yaml up -d --build --quiet-pull
container=$(docker compose -f backend/deploy/compose.yaml ps -q api)
deadline=$((SECONDS + timeout_s))
until [ "$(docker inspect -f '{{.State.Health.Status}}' "$container")" = healthy ]; do
  if [ "$SECONDS" -ge "$deadline" ]; then
    docker compose -f backend/deploy/compose.yaml logs --tail 50 api >&2
    echo "not healthy after ${timeout_s}s; stopping the rollout" >&2
    exit 1
  fi
  sleep 2
done
docker image prune -f --filter "until=168h" >/dev/null
echo "healthy at $sha"
REMOTE
done
echo "all hosts at $sha"
