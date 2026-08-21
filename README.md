# S10 Control Server

Servidor de controle **local-first** para um Samsung Galaxy S10+ SM-G975F,
executado no Termux, sem root e com o display físico inoperante.

O projeto está no **Milestone 2**. A estabilização M2.1 `0.2.1` foi validada no
SM-G975F real (runtime Termux, restart gracioso, recuperação do painel/WebSocket,
preservação do SSH e telemetria LAN). A campanha M2 comprovou uma vez self-ADB,
identidade, PNG real 720 × 1520, viewport portrait inteiro e controles pelo
painel. A correção final do flicker entre PNGs passou no host e aguarda reteste
no aparelho. O backend é Python/FastAPI com SQLite e a interface é
React/TypeScript/Vite, compilada para assets locais e entregue pelo próprio
backend. A base de trabalho é:

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
