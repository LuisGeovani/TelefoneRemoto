# S10 Control Server

Servidor de controle **local-first** para um Samsung Galaxy S10+ SM-G975F,
executado no Termux, sem root e com o display físico inoperante.

O projeto está no **Milestone 1 (painel local em implementação)**. O backend é
Python/FastAPI com SQLite e a interface é React/TypeScript/Vite, compilada para
assets locais e entregue pelo próprio backend. A base de trabalho é:

- [SPEC.md](SPEC.md): escopo consolidado e matriz de viabilidade;
- [ARCHITECTURE.md](ARCHITECTURE.md): arquitetura, módulos e contratos;
- [PLAN.md](PLAN.md): milestones e validação no S10 real;
- [STATUS.md](STATUS.md): estado verificável do repositório;
- [AGENTS.md](AGENTS.md): regras permanentes de segurança e colaboração.

## Princípio operacional

A LAN é o caminho principal. Internet e túnel remoto são opcionais. A ausência
de ADB, Internet, túnel, Termux:API ou qualquer provider opcional deve reduzir
somente as capacidades correspondentes, sem derrubar o núcleo local.

## Execução planejada no Termux

Após a validação no aparelho real, o painel escutará em `0.0.0.0:8080` e será
acessado pela LAN. Internet não é necessária depois da instalação; ADB é apenas
reportado como indisponível nesta etapa e nunca é chamado pelo servidor.
