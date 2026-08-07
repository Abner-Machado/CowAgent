# CowAgent

Framework de chatbot em Python (fork de chatgpt-on-wechat), com cliente
desktop em Electron sob `desktop/`.

## Convenções de commit

Mensagens descritivas, apenas técnicas: o que mudou e por quê. **Não**
incluir trailers de co-autoria, links de sessão, nem menção a Claude, IA,
assistente ou automação em nenhuma parte da mensagem.

## Rotina diária de manutenção

`.github/workflows/daily-maintenance.yml` roda às `0 9 * * *` (09:00 UTC =
06:00 em São Paulo) e também aceita `workflow_dispatch` para disparo manual.
Commita direto no `master`.

O trabalho fica em `scripts/daily_maintenance.py`: limpa `F401` (imports não
usados) e `F841` (variáveis não usadas) com ruff, **um diretório por
execução**, para manter os commits pequenos e espalhar a limpeza ao longo dos
dias. Se não achar lint, o workflow tenta typos em markdown via codespell —
um assunto por commit.

Salvaguardas, porque o push vai direto na branch default sem revisão:

- só correções que o ruff classifica como seguras;
- `__init__.py` excluído do `F401`, senão remove re-exports intencionais;
- `py_compile` em todo arquivo tocado — se algum não compilar, reverte tudo
  e sai sem commit;
- sem nada a corrigir, não há commit. Dia vazio é resultado esperado.

O `.codespellrc` guarda os falsos positivos que **não** devem ser
"corrigidos": `datas` (chave da API do PyInstaller em `desktop/build/*.spec`),
`scaned` (valor de status vindo de API externa em `channel/weixin/`), e os
identificadores `upToDate`, `provId`, `oldEs`, `nd` do código do desktop.

Prazo: a rotina foi criada para rodar até **30/08/2026**. O `cron` não tem
data de término — desativar em Actions → "Daily maintenance" → Disable
workflow, ou adicionar guarda de data no job.

## Armadilhas conhecidas

Em `except Exception as e:`, o nome `e` é apagado ao sair do bloco. Funções
aninhadas definidas dentro do `except` (como os `error_generator()` dos
bots em `models/`) não podem referenciar `e` — precisam capturar
`str(e)` numa variável local antes. Isso já causou `NameError` no caminho de
tratamento de erro em sete bots; corrigido em `a29d421`.
