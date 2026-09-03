#!/usr/bin/env bash
# Detecta o ambiente atual: gerenciador de pacote, init system, privilégio
# e runtimes disponíveis. Kernel/versão é reportado só como informação —
# não é usado pra decidir nada, porque instalar uma skill nunca toca syscall.
set -euo pipefail

_detect_pkg_manager() {
  for pm in apt apt-get dnf yum apk pacman zypper brew; do
    if command -v "$pm" >/dev/null 2>&1; then
      echo "$pm"
      return
    fi
  done
  echo "desconhecido"
}

_detect_init() {
  if [ -d /run/systemd/system ] && command -v systemctl >/dev/null 2>&1; then
    echo "systemd"
  elif command -v openrc >/dev/null 2>&1; then
    echo "openrc"
  else
    echo "nenhum"
  fi
}

_detect_privilege() {
  if [ "$(id -u)" -eq 0 ]; then
    echo "root"
  elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    echo "sudo-sem-senha"
  else
    echo "usuario-comum"
  fi
}

_has() {
  command -v "$1" >/dev/null 2>&1 && echo "sim" || echo "nao"
}

VPSBOOT_OS="$(uname -s)"
VPSBOOT_KERNEL="$(uname -r)"
VPSBOOT_ARCH="$(uname -m)"
VPSBOOT_PKG_MANAGER="$(_detect_pkg_manager)"
VPSBOOT_INIT="$(_detect_init)"
VPSBOOT_PRIVILEGE="$(_detect_privilege)"
VPSBOOT_HAS_GIT="$(_has git)"
VPSBOOT_HAS_CURL="$(_has curl)"
VPSBOOT_HAS_PYTHON3="$(_has python3)"
VPSBOOT_HAS_NODE="$(_has node)"
VPSBOOT_HAS_GUARD="$(_has guard)"

print_env_report() {
  cat <<EOF
Sistema........: $VPSBOOT_OS $VPSBOOT_KERNEL ($VPSBOOT_ARCH)
Gerenciador....: $VPSBOOT_PKG_MANAGER
Init system....: $VPSBOOT_INIT
Privilegio.....: $VPSBOOT_PRIVILEGE
git............: $VPSBOOT_HAS_GIT
curl...........: $VPSBOOT_HAS_CURL
python3........: $VPSBOOT_HAS_PYTHON3
node...........: $VPSBOOT_HAS_NODE
guard..........: $VPSBOOT_HAS_GUARD (allied-code)
EOF
}

# Só imprime o relatório quando executado direto; quando sourced por
# install.sh, este arquivo apenas exporta as variáveis acima.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  print_env_report
fi
