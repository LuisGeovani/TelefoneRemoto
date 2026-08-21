# Estado atual

- **Atualizado em:** 2026-08-20 (America/Rio_Branco)
- **Branch de trabalho:** `codex/m2.1-hardware-stabilization`
- **Versão:** `0.2.1`
- **Milestone:** M2.1 concluída e validada no hardware; M2 ADB real permanece pendente
- **Push:** autorizado explicitamente para o fechamento e a campanha M2 em hardware

## Resultado da estabilização M2.1

Esta tarefa não adiciona feature. Ela reconcilia o repositório com a evidência
obtida no Samsung Galaxy S10+ SM-G975F real:

- pins alterados para FastAPI 0.118.3, Pydantic 1.10.26 e Starlette 0.48.0;
- smoke de versões/import do projeto inserido em instalação e atualização;
- Uvicorn configurado com shutdown gracioso limitado a cinco segundos;
- regressão POSIX inicia o servidor real, espera ready, abre WebSocket
  autenticado, envia SIGTERM e exige saída dentro do limite;
- telemetria LAN combina endereço observado no socket, hostname e seleção de
  endereço-fonte por UDP conectado sem transmitir dados, sem `iproute2`, nome
  de interface ou mutação da rede;
- requests com `Range` são recusadas antes de `FileResponse`, fechando a
  superfície alcançável do advisory de ranges da Starlette 0.48.0;
- ADR 0004 documenta a compatibilidade, as mitigações e os riscos restantes.
- no SM-G975F real, `sv restart s10-control` encerrou o PID `8132`, iniciou o
  PID `15504`, restaurou readiness/LAN/WebSocket e preservou duas sessões SSH.

Não foram adicionados PowerShare, H.264/scrcpy, terminal, arquivos, package
manager, Cloudflare, Tailscale ou qualquer outro milestone.

## Evidência real no SM-G975F

O projeto foi instalado em `~/s10-control` no Termux do SM-G975F, usuário
`u0_a343`, com SSH existente na porta 8022. Nenhum segredo, token, fingerprint
ou captura foi registrado no Git.

Validados no aparelho em um deploy real:

| Item | Evidência observada |
|---|---|
| Instalação Termux ARM64 | venv, dependências e pacote editável concluíram após ajuste dos pins |
| Python | `3.14.6`; smoke M2.1 executado novamente com sucesso |
| Stack backend | FastAPI `0.118.3`, Pydantic `1.10.26`, Starlette `0.48.0`; `update-termux.sh`, import e versão `0.2.1` passaram |
| Frontend | `npm ci`, typecheck e build Vite concluíram; SPA/PWA carregou no navegador |
| Serviço | runit reiniciou `s10-control` do PID `8132` para `15504` sem ficar preso em `got TERM`; `sshd` permaneceu online |
| Listener | bind `0.0.0.0:8080` voltou após o restart e ready respondeu `ready` |
| LAN | painel acessado de outro equipamento por `http://192.168.1.13:8080`; Dashboard reportou a LAN corretamente |
| Autenticação | `auth reset --yes`, novo bootstrap token e novo login funcionaram após a atualização |
| Dashboard | sistema, CPU, RAM, armazenamento e estados carregaram e voltaram após o restart |
| Rede | probe de Internet online e probe SSH online |
| Termux:API | CLI e APK compatíveis instalados; `termux-battery-status` respondeu |
| Bateria | dados reais apareceram no Dashboard |
| Tela Remota | página mobile-first e controles carregaram |
| WebSocket da UI | conexão funcionou novamente após o restart de `s10-control` |

Essa é uma validação real, mas única. As capacidades acima permanecem na classe
`probable`, não `guaranteed`, até haver execução repetível sob pré-condições
registradas. LAN sem Internet e soak ainda não foram executados no aparelho.

## Falhas reais encontradas

1. **Compatibilidade Python:** FastAPI 0.124.4/Pydantic 1.10.26/Starlette
   0.50.0 falhou no Python 3.14.6 com `ImportError: cannot import name
   'TypeAdapter' from 'pydantic'`. A combinação agora fixada importou e executou
   no S10.
2. **Shutdown:** `sv restart s10-control` fechou o listener após SIGTERM, mas o
   processo Python permaneceu vivo e o runit mostrou `got TERM`. Após M2.1, o
   teste real encerrou o PID `8132`, iniciou o PID `15504` e recuperou ready,
   Dashboard e WebSocket sem perder SSH; a correção está validada no aparelho.
3. **Detecção LAN:** o Dashboard mostrou `NO_PRIVATE_ADDRESS_VISIBLE` apesar do
   acesso real por `192.168.1.20:8080`. Após M2.1, a descoberta mostrou o
   endereço privado real e o painel foi usado por `192.168.1.13:8080`; a
   correção está validada no aparelho sem alterar rede ou listener.
4. **Bateria:** instalar somente o pacote CLI `termux-api` não bastou e o comando
   aguardou o APK. Depois de instalar o app Termux:API de origem compatível, a
   coleta funcionou. Ausência do APK continua sendo degradação esperada.

## Classificação e estado verificável

| Capacidade | Classe | Evidência atual |
|---|---|---|
| Runtime e lifecycle M2.1 | `probable` | versão `0.2.1`, smoke e restart real `8132` → `15504` validados no SM-G975F |
| Core, auth, health, Dashboard e métricas básicas | `probable` | executados uma vez no SM-G975F; repetição/soak pendentes |
| Listener e acesso LAN `0.0.0.0:8080` | `probable` | acesso real por `192.168.1.13` e telemetria correta após restart; teste sem WAN pendente |
| SSH observacional | `probable` | probe e serviço real online; permanece protegido/read-only |
| Termux:API e bateria | `probable` | APK+CLI compatíveis responderam no aparelho |
| Frontend Tela Remota e WebSocket da UI | `probable` | página e conexão funcionando após restart validadas; sem frame ADB |
| ADB no próprio Termux | `experimental` | desabilitado no deploy; transporte real não testado |
| Screenshot PNG por ADB | `experimental` | somente mock/fixtures no host |
| Controle Android vinculado ao frame | `experimental` | somente mock/contrato no host |
| Wake/sleep e `adb input text` | `experimental` | não executados no aparelho |
| H.264/scrcpy e PowerShare | `experimental` | não implementados |
| Operações que exigem root/privilégio de sistema | `privileged_required` | permanecem fora do projeto |

## Não validado no hardware

- self-ADB/Wireless Debugging dentro do Termux;
- seleção de target, modelo/fingerprint e mudança de porta reais;
- screenshot PNG real e comportamento com display físico inoperante;
- rotação real por `dumpsys input`;
- tap, swipe, long press, HOME, BACK, RECENTS, ENTER e volume;
- wake/sleep e texto ASCII;
- frame-bound control, pós-condições, fullscreen móvel e gestos reais;
- LAN com WAN indisponível, soak e consumo térmico/energético.

ADB permaneceu `enabled: false` durante a validação M2.1; não foram executados
`adb pair`, `connect`, `disconnect`, `kill-server`, `tcpip`, `root`, `unroot`,
reboot ou revogação. Wi-Fi e SSH não foram alterados.

## Validação no host desta branch

- ambiente de teste: Python 3.12.13 com os pins exatos do runtime;
- backend: 59 testes passaram e 1 regressão POSIX de SIGTERM foi pulada no
  Windows; a suíte inclui import em subprocesso, versões, LAN por socket/rota,
  `Range` recusado, timeout de shutdown, ADB degradado e todos os contratos M2;
- a regressão SIGTERM fica habilitada automaticamente em Linux/Termux e mantém
  um WebSocket autenticado aberto durante o sinal;
- frontend 0.2.1: `npm test` (typecheck) e `npm run build` passaram; Vite gerou
  21 módulos e assets locais;
- `compileall` de source, testes e smoke passou;
- `pip check` reportou `No broken requirements found`;
- `smoke-python-runtime.py` importou o projeto em subprocesso e confirmou os
  três pins;
- processo Uvicorn real iniciou em `0.0.0.0:8080`; ready e SPA responderam 200.
  O harness Windows não entregou Ctrl+C ao filho e fez cleanup pelo PID exato,
  portanto isso não conta como teste de shutdown;
- `bash -n` passou para install, update e serviço runit. A revisão confirmou
  que instalação/atualização executam o smoke antes do bootstrap/build, não
  iniciam automaticamente serviço novo e não reiniciam aparelho, rede, ADB ou
  SSH;
- no fechamento documental, a matriz foi repetida: 59 testes backend passaram
  com 1 skip POSIX esperado no Windows, smoke isolado, `compileall`, `pip check`,
  typecheck/build frontend, `bash -n` e `git diff --check` passaram;
- nenhuma chamada tocou ADB, Wi-Fi, SSH ou o aparelho real.

## VEX estreita: Starlette 0.48.0

Starlette 0.48.0 permanece afetada por advisories e não é chamada de corrigida:

| Advisory | Superfície nesta aplicação |
|---|---|
| `GHSA-7f5h-v6xp-fcq8` | `FileResponse` existe, mas todo `Range` é recusado no middleware antes do roteamento; teste negativo obrigatório |
| `GHSA-86qp-5c8j-p5mr` | não há decisão baseada em `request.url`; path de cache/log vem de `scope["path"]` |
| `GHSA-wqp7-x3pw-xc5r` | afeta `StaticFiles` no Windows; runtime é Termux/POSIX e não há `StaticFiles` |
| `GHSA-x746-7m8f-x49c` | não há `HTTPEndpoint` |
| `GHSA-jp82-jpqv-5vv3` | não há uso de `request.url`/hostname |
| `GHSA-82w8-qh3p-5jfq` | não há `request.form()` nem parser multipart |

A análise completa e links oficiais estão no ADR 0004. Qualquer introdução de
Range, `request.url`, forms, `StaticFiles`, `HTTPEndpoint` ou deploy Windows
invalida a VEX. Scanners devem continuar sinalizando a dependência até uma pilha
upstream corrigida ser comprovada no Termux ARM64.

## Riscos remanescentes

1. Pydantic 1 não tem suporte upstream para Python 3.14, embora 1.10.26 tenha
   funcionado neste aparelho; uma atualização futura do Python Termux pode
   quebrar o runtime.
2. Starlette 0.48.0 está em ranges vulneráveis; as mitigações dependem da
   superfície permanecer estreita e devem ser reavaliadas em qualquer mudança.
3. O prazo do Uvicorn resolveu o restart preso no teste real, mas pode cancelar
   requests/WS em andamento após cinco segundos; o WebSocket funcionou depois
   do restart no teste.
4. A descoberta LAN funcionou no teste real depois de uma request por
   `192.168.1.13`; antes da primeira request, os fallbacks ainda dependem das
   rotas que o kernel expõe ao Termux.
5. Self-ADB, PNG e input continuam totalmente não validados no hardware.
6. HTTP LAN não oferece confidencialidade e `:8080` não deve ser publicado por
   WAN ou túnel.
7. Android/One UI ainda pode matar Termux e `sshd`; runit não garante uptime do
   app Android.

## Próximo passo seguro

M2.1 está aceita e encerrada. O próximo trabalho operacional, em tarefa
separada, é validar o M2 já implementado: self-ADB manual, PNG e controles reais
conforme o runbook, preservando a rota scrcpy USB e o SSH. O próximo milestone
novo numerado no `PLAN.md` é M3 (observabilidade local avançada), ainda não
autorizado. Não iniciar M2 real, M3, PowerShare, H.264 ou outro milestone sem
autorização específica.
