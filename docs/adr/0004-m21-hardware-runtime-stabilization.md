# ADR 0004 — Estabilização do runtime após validação no S10

- **Estado:** aceita
- **Data:** 2026-08-20
- **Escopo:** estabilização M2.1, sem novo milestone funcional
- **Substitui parcialmente:** pins e pressupostos operacionais do ADR 0002

## Contexto

O deploy real no Samsung Galaxy S10+ SM-G975F encontrou três divergências que
os testes de host do M2 não revelaram:

1. Python 3.14.6 com FastAPI 0.124.4, Pydantic 1.10.26 e Starlette 0.50.0 falhou
   no import por tentar importar `TypeAdapter` do Pydantic 1;
2. após SIGTERM, o Uvicorn fechou o listener, mas permaneceu vivo sem prazo de
   shutdown, prendendo `sv restart s10-control`;
3. `getaddrinfo(gethostname())` não mostrou o endereço `192.168.1.20`, embora o
   painel estivesse acessível por ele a partir de outro equipamento.

No mesmo aparelho foi comprovado que Python 3.14.6 com FastAPI 0.118.3,
Pydantic 1.10.26 e Starlette 0.48.0 importa e executa o projeto. O
[metadata oficial do FastAPI 0.118.3](https://github.com/fastapi/fastapi/blob/0.118.3/pyproject.toml)
declara Python 3.14 e restringe Starlette a `>=0.40.0,<0.49.0`.

## Decisão

- Fixar FastAPI 0.118.3, Pydantic 1.10.26 e Starlette 0.48.0 nos três manifests.
- Executar um smoke de import e versões imediatamente após instalar o backend,
  antes de bootstrap ou build, tanto em instalação quanto em atualização.
- Configurar o Uvicorn com prazo de shutdown gracioso de cinco segundos. A
  regressão POSIX inicia o servidor real, abre WebSocket autenticado, envia
  SIGTERM e exige saída do processo dentro do limite.
- Descobrir endereços por três fontes read-only: endereço local observado no
  socket HTTP, resolução do hostname e seleção de endereço-fonte por `connect`
  UDP sem envio de datagrama. Não chamar `ip`, não depender de `wlan0` e não
  alterar interface, rota, Wi-Fi ou DNS.
- Rejeitar todo header `Range` no middleware antes do roteamento. O M2 não
  precisa de respostas parciais e Starlette 0.48.0 tem um advisory de custo
  quadrático ao mesclar ranges em `FileResponse`.

## Estado de segurança de Starlette 0.48.0

Starlette 0.48.0 não é declarada corrigida. Ela permanece dentro dos ranges
afetados abaixo:

- [GHSA-7f5h-v6xp-fcq8](https://github.com/advisories/GHSA-7f5h-v6xp-fcq8):
  DoS quadrático em ranges de `FileResponse`; mitigado nesta aplicação pela
  rejeição global e testada de qualquer `Range` antes de `FileResponse`;
- [GHSA-86qp-5c8j-p5mr](https://github.com/advisories/GHSA-86qp-5c8j-p5mr):
  `Host` malformado pode envenenar `request.url.path`; decisões de rota/cache
  usam `scope["path"]`, e o projeto não usa `request.url`;
- [GHSA-wqp7-x3pw-xc5r](https://github.com/advisories/GHSA-wqp7-x3pw-xc5r):
  `StaticFiles` em Windows pode acessar UNC; o runtime é Termux/POSIX e o
  projeto não usa `StaticFiles`;
- [GHSA-x746-7m8f-x49c](https://github.com/advisories/GHSA-x746-7m8f-x49c):
  dispatch inseguro em `HTTPEndpoint`; o projeto não usa `HTTPEndpoint`;
- [GHSA-jp82-jpqv-5vv3](https://github.com/advisories/GHSA-jp82-jpqv-5vv3):
  path pode envenenar `request.url.hostname`; o projeto não usa `request.url`;
- [GHSA-82w8-qh3p-5jfq](https://github.com/advisories/GHSA-82w8-qh3p-5jfq):
  limites ignorados em `request.form()` urlencoded; o projeto não chama
  `request.form()` nem instala parser multipart.

Esta VEX é estrita à superfície atual e ao Termux. Adicionar byte ranges,
`request.url`, forms, `StaticFiles`, `HTTPEndpoint` ou suporte Windows invalida
a análise e exige upgrade/revisão antes do merge. Scanners devem continuar
reportando a versão; não há supressão global.

## Consequências

- O runtime passa a refletir a combinação realmente executada no hardware, mas
  Pydantic 1 em Python 3.14 continua fora do suporte upstream e é risco técnico.
- A saída por SIGTERM torna-se limitada mesmo com conexão persistente, evitando
  espera infinita do runit. À data desta decisão, a pós-condição `sv restart`
  com PID novo ainda precisava ser repetida no S10; o resultado posterior está
  registrado no addendum abaixo.
- A telemetria aprende o IP usado por uma conexão LAN real e conserva fallbacks
  portáveis quando ainda não houve conexão remota.
- Migrar para Pydantic 2/Starlette corrigida requer uma prova separada no
  Termux ARM64 e não pertence a esta estabilização.

## Addendum de validação no hardware — 2026-08-20

A pendência operacional descrita acima foi encerrada no Samsung Galaxy S10+
SM-G975F real. Com a versão `0.2.1`, `update-termux.sh` e o smoke do runtime
passaram; `sv restart s10-control` encerrou o PID `8132` e o runit iniciou o PID
`15504`. Readiness, Dashboard em `192.168.1.13:8080` e WebSocket funcionaram
após o restart, enquanto `sshd` e uma segunda sessão SSH permaneceram
operacionais.
A telemetria LAN passou a apresentar o endereço privado real. ADB permaneceu
desabilitado.

Este addendum registra evidência e não altera a decisão arquitetural nem promove
self-ADB, screenshot PNG ou controle Android, que continuam sem validação no
firmware real.
