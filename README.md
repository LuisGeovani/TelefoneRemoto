# S10 Control Server

Servidor de controle **local-first** para um Samsung Galaxy S10+ SM-G975F,
executado no Termux, sem root e com o display físico inoperante.

O projeto está na **M2.2 `0.2.2`**, validada no host e ainda pendente no
SM-G975F real. O M2 foi fechado no hardware no commit `38e0963`: self-ADB,
identidade, stream PNG 720 × 1520, portrait correto, apresentação sem flicker,
texto auxiliar estável e os controles HOME/BACK/RECENTS/tap/swipe/long press
funcionaram. A M2.2 acrescenta uma única conta administrativa com login por
username/password e sessão persistente de 30 dias; bootstrap passa a servir
somente para setup e recuperação. O backend é Python/FastAPI com SQLite e a
interface é React/TypeScript/Vite, compilada para assets locais e entregue pelo
próprio backend. A base de trabalho é:

- [SPEC.md](SPEC.md): escopo consolidado e matriz de viabilidade;
- [ARCHITECTURE.md](ARCHITECTURE.md): arquitetura, módulos e contratos;
- [PLAN.md](PLAN.md): milestones e validação no S10 real;
- [STATUS.md](STATUS.md): estado verificável do repositório;
- [AGENTS.md](AGENTS.md): regras permanentes de segurança e colaboração.

## Princípio operacional

A LAN é o caminho principal. Internet e túnel remoto são opcionais. A ausência
de ADB, Internet, túnel, Termux:API ou qualquer provider opcional deve reduzir
somente as capacidades correspondentes, sem derrubar o núcleo local.

## Estado funcional

O painel escuta em `0.0.0.0:8080`, mantém Dashboard/health/LAN sem Internet ou
ADB e oferece uma página de tela remota por screenshots PNG de baixo FPS. O ADB
é opcional: captura e controle só ficam disponíveis depois de modelo
`SM-G975F` e fingerprint local serem validados. Controles são tipados,
allowlisted e vinculados à mesma sessão/stream, frame, rotação, target e geração
ADB confirmados; não existe shell remoto.

H.264/scrcpy, PowerShare, terminal web, acesso remoto, package manager e file
manager não pertencem a esta etapa. Antes de usar ADB no aparelho, siga o
[runbook seguro](docs/operations/adb-screen-control-safe.md). O teste real no
S10 deve preservar SSH, Wi-Fi e as autorizações ADB existentes.

## Autenticação

No uso normal, abra o painel e entre com o username e a senha da única conta
administrativa. O cookie opaco é `HttpOnly`, `SameSite=Strict`, dura 30 dias e
é validado contra o estado persistente fora do repositório. Não há token em
`localStorage` nem cadastro público.

Em uma instalação atualizada que ainda não possui conta, obtenha o bootstrap
somente no terminal local com `s10-control bootstrap-token` e use `/setup`. Para
recuperação, gere novo token pelo mesmo comando e use `/recovery`; `s10-control
auth reset --yes` também invalida todas as sessões antes de emitir a credencial
de recuperação. Veja o [runbook de autenticação](docs/operations/persistent-auth-safe.md).
