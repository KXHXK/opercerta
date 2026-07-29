#!/usr/bin/env bash
set -Eeuo pipefail

readonly TUNA_UBUNTU_MIRROR="https://mirrors.tuna.tsinghua.edu.cn/ubuntu/"
readonly UBUNTU_SOURCES="/etc/apt/sources.list.d/ubuntu.sources"
readonly UV_VERSION="0.11.28"
readonly PYTHON_VERSION="3.12.13"
readonly NODE_VERSION="24.18.0"
readonly NODE_SHA256="55aa7153f9d88f28d765fcdad5ae6945b5c0f98a36881703817e4c450fa76742"
readonly TUNA_PYPI_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"
readonly NPM_REGISTRY="https://registry.npmmirror.com"
readonly NODE_MIRROR_BASE="https://cdn.npmmirror.com/binaries/node/"

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "${script_dir}/.." && pwd)"
temporary_directory=""

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

fail() {
  printf '\nERROR: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  if [[ -n "${temporary_directory}" && -d "${temporary_directory}" ]]; then
    rm -rf -- "${temporary_directory}"
  fi
}

trap cleanup EXIT

[[ "$(uname -s)" == "Linux" ]] || fail "This script must run inside Ubuntu WSL2."
grep -q '^ID=ubuntu$' /etc/os-release || fail "This script supports Ubuntu only."
grep -q '^VERSION_ID="26.04"$' /etc/os-release || fail "Ubuntu 26.04 is required."
grep -qi microsoft /proc/sys/kernel/osrelease || fail "A WSL2 kernel was not detected."

log "Requesting sudo once for system package installation"
sudo -v

if [[ -f "${UBUNTU_SOURCES}" ]]; then
  if ! grep -q "mirrors.tuna.tsinghua.edu.cn/ubuntu" "${UBUNTU_SOURCES}"; then
    backup="${UBUNTU_SOURCES}.opercerta-backup-$(date '+%Y%m%d%H%M%S')"
    log "Backing up Ubuntu APT sources to ${backup}"
    sudo cp --preserve=mode,ownership,timestamps "${UBUNTU_SOURCES}" "${backup}"
    sudo sed -E -i \
      "s#https?://(archive|security)\.ubuntu\.com/ubuntu/?#${TUNA_UBUNTU_MIRROR}#g" \
      "${UBUNTU_SOURCES}"
    grep -q "mirrors.tuna.tsinghua.edu.cn/ubuntu" "${UBUNTU_SOURCES}" || \
      fail "The Ubuntu source format was not recognized; the backup was preserved at ${backup}."
  fi
else
  fail "Expected ${UBUNTU_SOURCES}; refusing to guess a package-source layout."
fi

log "Refreshing signed Ubuntu package metadata from TUNA"
sudo apt-get update

log "Installing the repository-approved Linux development runtime"
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y \
  build-essential \
  ca-certificates \
  curl \
  docker-buildx \
  docker-compose-v2 \
  docker.io \
  git \
  xz-utils

export PATH="${HOME}/.local/bin:${PATH}"

if ! command -v uv >/dev/null || [[ "$(uv --version)" != "uv ${UV_VERSION} "* ]]; then
  log "Installing pinned uv ${UV_VERSION} from the official versioned installer"
  temporary_directory="$(mktemp -d)"
  curl --fail --location --retry 5 --connect-timeout 15 \
    "https://astral.sh/uv/${UV_VERSION}/install.sh" \
    --output "${temporary_directory}/uv-installer.sh"
  sh "${temporary_directory}/uv-installer.sh"
  export PATH="${HOME}/.local/bin:${PATH}"
fi

[[ "$(uv --version)" == "uv ${UV_VERSION} "* ]] || \
  fail "Expected uv ${UV_VERSION}, got: $(uv --version)"

log "Installing the project-managed Python ${PYTHON_VERSION} without replacing Ubuntu Python"
uv python install "${PYTHON_VERSION}"
managed_python="$(uv python find "${PYTHON_VERSION}")"
[[ "$("${managed_python}" --version)" == "Python ${PYTHON_VERSION}" ]] || \
  fail "uv did not resolve Python ${PYTHON_VERSION}."

node_home="${HOME}/.local/opt/node-v${NODE_VERSION}-linux-x64"
node_archive="node-v${NODE_VERSION}-linux-x64.tar.xz"
node_url="${NODE_MIRROR_BASE}v${NODE_VERSION}/${node_archive}"

if [[ ! -x "${node_home}/bin/node" ]]; then
  [[ ! -e "${node_home}" ]] || \
    fail "Incomplete Node directory exists at ${node_home}; inspect it before retrying."
  [[ -n "${temporary_directory}" ]] || temporary_directory="$(mktemp -d)"
  log "Downloading Node ${NODE_VERSION} from npmmirror and verifying the official SHA256"
  curl --fail --location --retry 5 --connect-timeout 15 --continue-at - \
    "${node_url}" \
    --output "${temporary_directory}/${node_archive}"
  printf '%s  %s\n' "${NODE_SHA256}" "${temporary_directory}/${node_archive}" \
    | sha256sum -c -
  install -d -m 0755 "${HOME}/.local/opt"
  tar -xJf "${temporary_directory}/${node_archive}" -C "${HOME}/.local/opt"
fi

node_path_line='export PATH="$HOME/.local/opt/node-v24.18.0-linux-x64/bin:$HOME/.local/bin:$PATH"'
grep -Fqx "${node_path_line}" "${HOME}/.bashrc" || \
  printf '\n%s\n' "${node_path_line}" >>"${HOME}/.bashrc"
export PATH="${node_home}/bin:${HOME}/.local/bin:${PATH}"

[[ "$(node --version)" == "v${NODE_VERSION}" ]] || \
  fail "Expected Node v${NODE_VERSION}, got: $(node --version)"
npm config set registry "${NPM_REGISTRY}"

log "Verified the pinned Python and frontend development tools"
uv --version
"${managed_python}" --version
node --version
npm --version
npm config get registry

log "Configuring the Docker registry mirrors recorded in the OperCerta runtime design"
sudo install -d -m 0755 /etc/docker
sudo tee /etc/docker/daemon.json >/dev/null <<'JSON'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.1ms.run",
    "https://docker.xuanyuan.me"
  ]
}
JSON

if ! getent group docker >/dev/null; then
  sudo groupadd docker
fi
sudo usermod -aG docker "${USER}"
sudo systemctl enable --now docker
sudo systemctl restart docker

log "Verifying Docker client, server, Compose, Buildx, and configured mirrors"
docker --version
sudo docker info --format 'Server={{.ServerVersion}} Driver={{.Driver}} Cgroup={{.CgroupVersion}}'
docker compose version
docker buildx version
sudo docker info | sed -n '/Registry Mirrors:/,/Live Restore Enabled:/p'

log "Running the minimal registry and container execution probe"
sudo docker pull hello-world
sudo docker run --rm hello-world

if [[ "${project_root}" == /mnt/* ]]; then
  cat <<EOF

DrvFS development boundary:

  This repository is on a Windows-mounted drive (${project_root}).
  Do not alternate Windows npm and WSL npm against the same web/node_modules tree.
  Stop any Windows Vite/Node process before the first WSL `npm ci`, then keep npm
  install, test, and build commands inside WSL. A generated node_modules tree is
  disposable and remains excluded from Git.

For a slow PyPI connection, preserve uv.lock and prefill the project environment
from the TUNA mirror with the repository's documented hash-checked export flow:

  UV_DEFAULT_INDEX=${TUNA_PYPI_MIRROR}
  UV_HTTP_TIMEOUT=300
  UV_HTTP_RETRIES=10
EOF
fi

cat <<'EOF'

WSL environment bootstrap completed.

The current shell does not automatically receive the new docker-group membership.
Run `exit`, open Ubuntu again, and then run:

  docker info

Pinned development tools were also installed for the current user. Reopen Ubuntu
before relying on the saved Node PATH, then verify `uv --version`, `uv run python
--version`, `node --version`, and `npm --version` from the OperCerta repository.

Do not use `sudo docker` for normal project work after reopening Ubuntu.
EOF
