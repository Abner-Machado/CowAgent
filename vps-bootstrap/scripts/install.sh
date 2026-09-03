#!/usr/bin/env bash
# Instala uma skill de Claude Code em qualquer VPS: detecta o ambiente,
# mostra o plano, pede confirmação e só então copia. Se o binário `guard`
# (allied-code) estiver disponível, os scripts da skill passam por ele
# antes da instalação.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=detect-env.sh
source "$SCRIPT_DIR/detect-env.sh"

usage() {
  cat <<EOF
Uso: $(basename "$0") <fonte-da-skill> [opcoes]

  <fonte-da-skill>   URL git (https://github.com/...) ou caminho local
                      de um diretorio contendo um SKILL.md na raiz

Opcoes:
  --target-dir DIR   Onde instalar (padrao: \$CLAUDE_SKILLS_DIR ou ~/.claude/skills)
  --yes               Nao pergunta, instala direto (assume o risco)
  -h, --help          Esta mensagem

Exemplo:
  $(basename "$0") https://github.com/Abner-Machado/comitbigorna
EOF
}

SOURCE=""
TARGET_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
ASSUME_YES="no"

while [ $# -gt 0 ]; do
  case "$1" in
    --target-dir)
      TARGET_DIR="$2"
      shift 2
      ;;
    --yes)
      ASSUME_YES="yes"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [ -z "$SOURCE" ]; then
        SOURCE="$1"
        shift
      else
        echo "Argumento inesperado: $1" >&2
        usage
        exit 1
      fi
      ;;
  esac
done

if [ -z "$SOURCE" ]; then
  echo "Erro: faltou a fonte da skill." >&2
  usage
  exit 1
fi

STAGING="$(mktemp -d)"
cleanup() { rm -rf "$STAGING"; }
trap cleanup EXIT

echo "==> Buscando skill de: $SOURCE"
if [[ "$SOURCE" =~ ^https?:// ]] || [[ "$SOURCE" =~ ^git@ ]]; then
  if [ "$VPSBOOT_HAS_GIT" != "sim" ]; then
    echo "Erro: fonte e uma URL git, mas 'git' nao esta disponivel neste ambiente." >&2
    exit 1
  fi
  git clone --depth 1 --quiet "$SOURCE" "$STAGING/skill" \
    || { echo "Erro: falha ao clonar $SOURCE" >&2; exit 1; }
  rm -rf "$STAGING/skill/.git"
else
  if [ ! -d "$SOURCE" ]; then
    echo "Erro: caminho local nao existe: $SOURCE" >&2
    exit 1
  fi
  cp -r "$SOURCE" "$STAGING/skill"
fi

SKILL_PATH="$STAGING/skill"

if [ ! -f "$SKILL_PATH/SKILL.md" ]; then
  echo "Erro: $SOURCE nao tem SKILL.md na raiz — nao parece ser uma skill valida." >&2
  exit 1
fi

SKILL_NAME="$(grep -m1 '^name:' "$SKILL_PATH/SKILL.md" | sed 's/^name: *//' | tr -d '\r')"
if [ -z "$SKILL_NAME" ]; then
  SKILL_NAME="$(basename "$SOURCE" .git)"
fi

DEST="$TARGET_DIR/$SKILL_NAME"

echo
echo "===================== Plano ====================="
print_env_report
echo "---------------------------------------------------"
echo "Skill..........: $SKILL_NAME"
echo "Origem.........: $SOURCE"
echo "Destino........: $DEST"
if [ -e "$DEST" ]; then
  echo "Atencao........: ja existe algo em $DEST, sera sobrescrito"
fi
echo "==================================================="
echo

if [ "$VPSBOOT_HAS_GUARD" = "sim" ]; then
  echo "==> guard encontrado — avaliando os scripts da skill antes de instalar..."
  BLOCKED=0
  while IFS= read -r -d '' script; do
    if ! guard check "bash $script" --json; then
      echo "guard recusou rodar: $script" >&2
      BLOCKED=1
    fi
  done < <(find "$SKILL_PATH" -type f -name '*.sh' -print0)
  if [ "$BLOCKED" -eq 1 ]; then
    echo "Erro: guard recusou um ou mais scripts dessa skill. Instalacao abortada." >&2
    exit 1
  fi
else
  echo "Aviso: guard (allied-code) nao encontrado no PATH — instalando SEM verificacao de guardrail." >&2
  echo "       https://github.com/Abner-Machado/allied-code" >&2
fi

if [ "$ASSUME_YES" != "yes" ]; then
  read -r -p "Confirma a instalacao acima? [y/N] " REPLY
  case "$REPLY" in
    [yY][eE][sS]|[yY]) ;;
    *)
      echo "Cancelado."
      exit 1
      ;;
  esac
fi

mkdir -p "$TARGET_DIR"
rm -rf "$DEST"
cp -r "$SKILL_PATH" "$DEST"

echo "==> Instalado em $DEST"
