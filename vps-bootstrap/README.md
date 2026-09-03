# vps-bootstrap

> **Provisorio dentro do CowAgent.** Isto e um produto proprio, desacoplado
> do CowAgent por decisao explicita — so esta hospedado aqui porque a
> sessao que o criou nao tinha permissao pra abrir repositorio novo no
> momento. Vira `Abner-Machado/vps-bootstrap` (ou nome equivalente) assim
> que possivel; nao trate como parte do roadmap do CowAgent.

Instalador plug-and-play de skills de [Claude Code](https://claude.com/claude-code)
em qualquer VPS. Detecta o ambiente, mostra um plano, pede confirmacao — e
so entao instala.

Nao e um framework universal pra "qualquer IA": e uma skill pequena e
desacoplada, com um alvo claro (Claude Code) e um fluxo honesto (nunca
silencioso, nunca assume root).

## Por que existe

Plug-and-play automatico em maquina de terceiro e, por padrao, o vetor de
ataque que ferramentas como o [allied-code](https://github.com/Abner-Machado/allied-code)
existem pra bloquear. Este instalador resolve essa tensao assim:

- **Nunca** baixa e executa as cegas. Sempre monta um plano legivel primeiro.
- **Nunca** assume que voce tem root, ou que sua distro usa `apt`.
- **Se** o `guard` (allied-code) estiver instalado, cada script `.sh` da
  skill que voce esta instalando passa por ele antes da copia.
- Sem `guard` no PATH, ele avisa alto e claro que esta instalando sem
  verificacao — a decisao de seguir sem essa camada e sua, nunca silenciosa.

## Uso

```bash
git clone https://github.com/Abner-Machado/vps-bootstrap
cd vps-bootstrap
bash scripts/install.sh https://github.com/Abner-Machado/comitbigorna
```

Ele mostra algo assim antes de pedir confirmacao:

```
===================== Plano =====================
Sistema........: Linux 6.18.44-fc-v24 (x86_64)
Gerenciador....: apt
Init system....: systemd
Privilegio.....: usuario-comum
git............: sim
curl...........: sim
python3........: sim
node...........: nao
guard..........: nao (allied-code)
---------------------------------------------------
Skill..........: comitbigorna
Origem.........: https://github.com/Abner-Machado/comitbigorna
Destino........: /home/voce/.claude/skills/comitbigorna
===================================================

Confirma a instalacao acima? [y/N]
```

Pra automatizar (CI, provisionamento, etc.), pule a confirmacao:

```bash
bash scripts/install.sh https://github.com/Abner-Machado/comitbigorna --yes
```

Instalar num diretorio de skills diferente do padrao:

```bash
bash scripts/install.sh <fonte> --target-dir /caminho/custom/skills
```

## Rodar so a deteccao de ambiente

```bash
bash scripts/detect-env.sh
```

## Escopo da v1

- Alvo: Claude Code. Nao promete suportar qualquer runtime de agente.
- Ignora versao de kernel Linux como variavel — o que muda de verdade entre
  VPS e gerenciador de pacote, init system e privilegio.
- Payload de demonstracao: [comitbigorna](https://github.com/Abner-Machado/comitbigorna),
  ja pronto e sem dependencia pesada.

## Licenca

MIT — ver [LICENSE](LICENSE).
