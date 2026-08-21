# ADR 0005 — Lease efêmero para controle já validado

- **Estado:** aceita
- **Data:** 2026-08-20
- **Escopo:** correção M2 após validação no SM-G975F

## Contexto

No aparelho real, o stream PNG operou a aproximadamente 1 FPS, mas toda ação da
UI terminou em `STALE_FRAME`. O frame estava confirmado quando a request foi
aceita. Enquanto ela aguardava o gate ADB, porém, o navegador decodificava e
confirmava o frame seguinte. O registry substituía corretamente o frame mais
recente e a revalidação imediatamente anterior ao input rejeitava a request em
voo. Aumentar `frame_max_age_seconds` não corrige essa corrida e enfraqueceria a
política de stale.

## Decisão

Após validar que a referência é o frame confirmado mais recente da mesma
sessão/stream, o backend cria um lease interno, opaco e limitado à duração dessa
ação. Um ACK normal pode avançar o frame mais recente sem cancelar esse lease.
Antes do input, continuam obrigatórias as revalidações de sessão/papel, idade,
display, rotação, target e geração ADB.

O lease é revogado ao fechar/inutilizar o stream, limpar o owner, ocorrer erro
do provider ou limpar o registry, e é sempre removido no `finally` da ação. Ele
não é enviado ao cliente e não permite iniciar uma nova ação sobre um frame que
já deixou de ser o mais recente.

## Consequências

- uma ação iniciada imediatamente após decode/ACK pode atravessar a espera do
  gate sem ser invalidada apenas pelo próximo ACK de 1 FPS;
- requests novas continuam exigindo o frame confirmado mais recente;
- frame expirado, sessão/stream revogados, rotação e identidade divergentes
  continuam fail-closed;
- a quantidade de leases é limitada pelas ações em voo e cada lease é limpo no
  término ou invalidação.

Esta decisão complementa a ADR 0003 somente para a janela de uma ação já
validada; não autoriza frames históricos nem altera a allowlist ADB.
