#!/usr/bin/env python3
"""Limpeza incremental de lint, um alvo por execucao.

Roda ruff nos diagnosticos F401 (imports nao usados) e F841 (variaveis nao
usadas), aplicando apenas as correcoes que o ruff classifica como seguras.
Processa um unico diretorio por vez para manter os commits pequenos e
revisaveis. Se nada compilar depois da correcao, desfaz tudo e sai sem
alteracoes.

Sai com codigo 0 tanto quando corrige algo quanto quando nao ha o que fazer.
Quem decide se ha commit e a ausencia/presenca de diff no working tree.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Diagnosticos que consideramos seguros para correcao automatica.
RULES = "F401,F841"

# __init__.py costuma reexportar simbolos de proposito: remover o import
# "nao usado" quebraria a API publica do pacote.
EXCLUDES = ["__init__.py"]


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, **kw)


def python_dirs():
    """Diretorios de primeiro nivel com codigo Python, em ordem estavel."""
    dirs = []
    for entry in sorted(REPO.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if entry.name in {"node_modules", "dist", "build", "__pycache__"}:
            continue
        if any(entry.rglob("*.py")):
            dirs.append(entry.name)
    return dirs


def count_issues(target):
    """Quantos diagnosticos corrigiveis existem no alvo."""
    proc = run([
        "ruff", "check", "--select", RULES,
        "--exclude", ",".join(EXCLUDES),
        "--output-format", "json", target,
    ])
    if not proc.stdout.strip():
        return 0
    try:
        items = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return 0
    return sum(1 for i in items if i.get("fix"))


def changed_python_files():
    proc = run(["git", "diff", "--name-only"])
    return [f for f in proc.stdout.split() if f.endswith(".py")]


def revert(paths):
    if paths:
        run(["git", "checkout", "--"] + paths)


def emit(message):
    """Publica a mensagem de commit para o passo seguinte do workflow."""
    print(message)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"summary<<EOF\n{message}\nEOF\n")


def main():
    target = next((d for d in python_dirs() if count_issues(d)), None)

    if target is None:
        print("Nenhum diagnostico corrigivel encontrado. Nada a fazer.")
        return 0

    before = count_issues(target)
    run([
        "ruff", "check", "--select", RULES,
        "--exclude", ",".join(EXCLUDES),
        "--fix", target,
    ])

    touched = changed_python_files()
    if not touched:
        print(f"ruff nao aplicou nenhuma correcao em {target}/. Nada a fazer.")
        return 0

    # Rede de seguranca: o push vai direto para a branch default, entao
    # qualquer arquivo que nao compile invalida a execucao inteira.
    compile_check = run([sys.executable, "-m", "py_compile"] + touched)
    if compile_check.returncode != 0:
        print("Correcao revertida: arquivo(s) nao compilam apos o ruff.")
        print(compile_check.stderr)
        revert(touched)
        return 0

    fixed = before - count_issues(target)
    emit(
        f"chore({target}): remove imports e variaveis nao utilizados\n\n"
        f"{fixed} diagnostico(s) F401/F841 corrigido(s) pelo ruff em "
        f"{len(touched)} arquivo(s). Apenas correcoes seguras; __init__.py "
        f"fica de fora para preservar reexports."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
