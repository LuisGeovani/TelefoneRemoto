# ADR 0001 — Núcleo local-first como monólito modular

- **Estado:** aceita
- **Data:** 2026-08-15

## Contexto

O servidor roda sem root em um Galaxy S10+ com Android/Termux, painel físico
inoperante e risco de processos-filho serem mortos. A LAN precisa funcionar sem
Internet e integrações como ADB/túnel podem desaparecer.

## Decisão

Usar um processo Go principal, UI estática embutida e arquitetura hexagonal com
providers opcionais. Persistência inicial é JSON atômico/NDJSON. Sidecars ficam
limitados a ferramentas Termux necessárias e não fazem parte do health do core.

## Consequências

- menor número de processos, instalação e recovery mais simples;
- módulos podem ser testados com fakes e degradar isoladamente;
- backend não escala por microserviços, o que é intencional para um único S10;
- recursos vendor/ADB precisam de adapters e capability reports explícitos;
- mudança para banco ou outro runtime exige nova ADR e prova no aparelho.
