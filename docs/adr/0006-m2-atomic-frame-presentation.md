# ADR 0006 — Apresentação atômica de frames PNG

- **Estado:** aceita
- **Data:** 2026-08-20
- **Escopo:** fechamento de UX do M2 após validação no SM-G975F

## Contexto

O reteste real de `52c7510` comprovou o frame portrait inteiro e controles pelo
painel, mas revelou flicker a aproximadamente 1 FPS. O frontend atribuía o Blob
URL candidato ao `<img>` visível antes do decode/ACK e cobria a superfície com
um overlay de progresso. Assim, o último frame válido desaparecia brevemente em
cada atualização.

## Decisão

O frontend mantém estados separados para frame exibido/confirmado e candidato.
O Blob candidato é pré-decodificado fora do DOM com uma `Image` nativa. Durante
decode e espera de ACK, o frame confirmado anterior continua visível e pode ser
usado enquanto ainda cumprir idade, sessão, stream, rotação, target e geração.
Somente `frame_acknowledged` promove o candidato e atualiza a referência visual
e de controle.

Não existe overlay de decode sobre a tela. No primeiro frame, o placeholder
permanece até a promoção. Em erro ou reconnect, o último frame pode permanecer
visível como referência stale/offline, mas fica sem autorização de input. A URL
anterior só é revogada após o evento `load` do novo frame exibido; no máximo uma
URL aposentada é mantida entre trocas, além do frame e candidato atuais.

## Consequências

- o protocolo WebSocket/ACK e o lease da ADR 0005 não são enfraquecidos;
- a superfície e sua geometria não desaparecem durante atualização normal;
- erro transitório não apaga a última evidência visual, mas status e bloqueio
  impedem que ela pareça uma tela ao vivo controlável;
- a solução usa somente APIs nativas do navegador e não adiciona dependências,
  canvas, H.264 ou double buffering complexo.

Esta decisão complementa as ADRs 0003 e 0005 e aguarda reteste no S10 real.

## Addendum de validação no hardware — 2026-08-20

O deploy posterior no SM-G975F confirmou que a imagem não pisca, o último frame
permanece visível entre atualizações, o portrait 720 × 1520 permanece inteiro e
os controles continuam funcionais. Um flicker separado no texto auxiliar do
painel foi observado; ele não altera este protocolo e é tratado como correção de
apresentação de status, ainda pendente de reteste.
