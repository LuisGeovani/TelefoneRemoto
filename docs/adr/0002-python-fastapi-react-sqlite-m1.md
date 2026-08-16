# ADR 0002 — Runtime do M1 em Python, FastAPI, React e SQLite

- **Estado:** aceita
- **Data:** 2026-08-15

## Contexto

O ADR 0001 previa Go, Preact e estado JSON. O proprietário autorizou
explicitamente o primeiro milestone funcional com Python + FastAPI, React +
TypeScript + Vite e SQLite, além de métricas locais. Essa autorização substitui
a escolha de runtime do M0, mas não as regras de segurança nem o desenho de
monólito local-first.

## Decisão

O M1 usa um único processo Python/FastAPI no Termux, SQLite da biblioteca padrão
e uma SPA React estática compilada por Vite e servida pelo backend. O listener
LAN é `0.0.0.0:8080`, conforme autorizado. A aplicação cria sessão com cookie
HttpOnly/SameSite=Strict; por usar HTTP na LAN neste milestone, o cookie não
pode ter a flag `Secure`. Portanto, o listener não deve ser exposto por túnel
ou WAN. TLS para LAN continua uma evolução de hardening posterior.

Métricas são exclusivamente read-only: procfs/POSIX, uma consulta TCP curta e
opcional a `termux-battery-status`. ADB não é invocado: a ausência do binário
é somente um estado `unavailable`.

## Consequências

- Termux precisa fornecer Python 3.11+ e Node.js apenas para instalação/build;
  o runtime não necessita de Internet depois de instalado.
- SQLite evita uma dependência nativa adicional, pois faz parte do Python;
  seus dados permanecem fora do Git e sob diretório privado do projeto.
- O M1 amplia métricas locais em relação ao plano original; tela, controle,
  PowerShare, terminal, arquivos, túnel e gerenciamento de serviços continuam
  fora de escopo.
- A decisão não altera as proibições: nenhum endpoint ou script controla Wi-Fi,
  SSH, ADB, boot ou componentes Android.
