---
name: vps-bootstrap
description: Instala uma skill de Claude Code em qualquer VPS. Detecta o ambiente (gerenciador de pacote, init system, root ou nao, runtimes disponiveis), mostra um plano e pede confirmacao antes de tocar em qualquer coisa. Se o guard (allied-code) estiver instalado, os scripts da skill passam por ele antes da copia. Use quando pedirem para instalar/plugar uma skill numa maquina nova, num VPS, ou "sobe essa skill em qualquer servidor".
---

> **Status: provisorio dentro do CowAgent.** Este diretorio mora aqui só
> porque a sessao que criou o `vps-bootstrap` nao tinha permissao pra abrir
> um repositorio novo no momento. É um produto desacoplado do CowAgent —
> a decisao explicita foi que ele **nao** deveria viver dentro do fork.
> Assim que possivel isso vira o repo proprio `Abner-Machado/vps-bootstrap`
> (ou nome equivalente) e este diretorio sai do CowAgent.

# Skill: vps-bootstrap

Instalador de skills de Claude Code pensado pra "chegar numa VPS nova e plugar
sem drama" — sem assumir root, sem assumir distro, sem rodar nada sem mostrar
o plano primeiro.

## O que faz

1. Roda `scripts/detect-env.sh`: identifica sistema, gerenciador de pacote
   (apt/apk/yum/dnf/pacman/zypper/brew), init system, privilegio (root, sudo
   sem senha, usuario comum) e presenca de git/curl/python3/node/guard.
2. Busca a skill de origem (URL git ou caminho local) pra um diretorio
   temporario.
3. Se `guard` (do [allied-code](https://github.com/Abner-Machado/allied-code))
   estiver no PATH, roda `guard check "bash <script>" --json` em cada script
   `.sh` da skill antes de prosseguir. Sem `guard`, instala mesmo assim, mas
   avisa que nao ha verificacao.
4. Mostra o plano completo (ambiente + origem + destino) e pede confirmacao —
   a menos que `--yes` seja passado.
5. Copia a skill pra `$CLAUDE_SKILLS_DIR` (ou `~/.claude/skills` por padrao).

## Como usar

```bash
bash scripts/install.sh https://github.com/Abner-Machado/comitbigorna
```

Ou sem interacao, pra automacao:

```bash
bash scripts/install.sh https://github.com/Abner-Machado/comitbigorna --yes
```

## Escopo desta v1

- Alvo: Claude Code (skills em `SKILL.md` + scripts). Nao tenta ser
  "universal pra qualquer agente de IA".
- Nao decide nada por versao de kernel Linux — instalar uma skill e copiar
  arquivo e rodar shell, nao mexe em syscall. O que varia de fato entre VPS
  e gerenciador de pacote, init system e privilegio, e e isso que o
  `detect-env.sh` mede.
- Nunca instala silenciosamente: sempre mostra o plano e pede confirmacao,
  exceto com `--yes` explicito.
