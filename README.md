# S10 Control Server

Servidor de controle **local-first** para um Samsung Galaxy S10+ SM-G975F,
executado no Termux, sem root e com o display físico inoperante.

O projeto está no **Milestone 0 (fundação documental)**. Ainda não há servidor,
interface web nem automação do aparelho implementados. A base de trabalho é:

- [SPEC.md](SPEC.md): escopo consolidado e matriz de viabilidade;
- [ARCHITECTURE.md](ARCHITECTURE.md): arquitetura, módulos e contratos;
- [PLAN.md](PLAN.md): milestones e validação no S10 real;
- [STATUS.md](STATUS.md): estado verificável do repositório;
- [AGENTS.md](AGENTS.md): regras permanentes de segurança e colaboração.

## Princípio operacional

A LAN é o caminho principal. Internet e túnel remoto são opcionais. A ausência
de ADB, Internet, túnel, Termux:API ou qualquer provider opcional deve reduzir
somente as capacidades correspondentes, sem derrubar o núcleo local.

## Estado do código

Esta fundação contém apenas documentação e limites de módulos. O
próximo passo autorizado é exclusivamente o Milestone 1 descrito em
[PLAN.md](PLAN.md#milestone-1--fundação-local-próximo-agente).
