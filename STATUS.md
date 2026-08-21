# Estado atual

- **Atualizado em:** 2026-08-20 (America/Rio_Branco)
- **Branch de trabalho:** `codex/m2-adb-hardware-validation`
- **Versão:** `0.2.1`
- **Milestone:** M2 validado no hardware; correção final de flicker aguardando reteste
- **Push:** autorizado explicitamente para o fechamento/UX final do M2

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

## Evidência do M2 no hardware

A campanha M2 posterior à estabilização comprovou, em uma única sessão segura
no SM-G975F real:

- self-ADB manual em estado `device`, sem alterar o ADB USB de recuperação;
- modelo e fingerprint esperados validados pelo provider, sem registrar target,
  fingerprint ou chaves no Git;
- Dashboard com ADB `available`/`IDENTITY_VERIFIED`;
- PNG real contínuo na Tela Remota: 720 × 1520, portrait, rotação 0°, WebSocket
  online e aproximadamente 1 FPS;
- `KEYCODE_HOME` e `input swipe` tipados executados diretamente no Termux
  funcionaram, isolando o transporte/input Android dos defeitos da aplicação.

Dois defeitos do S10 Control foram inicialmente observados: controles pela UI
eram recusados como `STALE_FRAME` quando o ACK do frame seguinte avançava o registry
enquanto a ação aguardava o gate ADB; e o PNG portrait aparecia ampliado/
recortado em viewport largo. O commit `52c7510` mantém um lease interno somente
para a ação já validada e usa uma imagem absoluta com `contain` centralizado,
letterbox e mapeamento pela área efetivamente renderizada. Após o deploy, o
proprietário confirmou no aparelho que o frame portrait inteiro 720 × 1520 foi
preservado e que os controles testados passaram a funcionar pelo painel.

O reteste revelou um defeito de UX restante: a troca normal de cada PNG exibia
o estado `decodificando` sobre a superfície, causando flicker perceptível a
aproximadamente 1 FPS. A correção atual pré-decodifica o candidato fora do DOM,
preserva o último frame válido durante decode/ACK e faz o swap somente após
`frame_acknowledged`. Ela passou no host e ainda aguarda reteste no S10.

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
| Tela Remota | PNG ADB real 720 × 1520 contínuo; portrait inteiro/contain confirmado após `52c7510` |
| WebSocket da UI | conexão funcionou após restart e na campanha M2 a aproximadamente 1 FPS |

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
5. **Controle frame-bound:** o frame seguinte confirmado invalidava uma ação
   fresca que já aguardava o gate ADB, produzindo `STALE_FRAME` continuamente em
   1 FPS. A correção de `52c7510` funcionou no reteste real: os controles
   exercitados pelo proprietário passaram a funcionar pelo painel.
6. **Viewport portrait:** o PNG 720 × 1520 participava do dimensionamento
   intrínseco do grid e aparecia recortado em viewport largo. O layout com
   `contain`, centralização e letterbox mostrou o frame inteiro no reteste real.
7. **Flicker entre PNGs:** o candidato substituía o `src` visível antes de
   decode/ACK e um overlay cobria o frame a cada atualização. A máquina de
   apresentação atômica passou nas regressões do host e aguarda reteste real.

## Classificação e estado verificável

| Capacidade | Classe | Evidência atual |
|---|---|---|
| Runtime e lifecycle M2.1 | `probable` | versão `0.2.1`, smoke e restart real `8132` → `15504` validados no SM-G975F |
| Core, auth, health, Dashboard e métricas básicas | `probable` | executados uma vez no SM-G975F; repetição/soak pendentes |
| Listener e acesso LAN `0.0.0.0:8080` | `probable` | acesso real por `192.168.1.13` e telemetria correta após restart; teste sem WAN pendente |
| SSH observacional | `probable` | probe e serviço real online; permanece protegido/read-only |
| Termux:API e bateria | `probable` | APK+CLI compatíveis responderam no aparelho |
| Frontend Tela Remota e WebSocket da UI | `probable` | WS/PNG e viewport portrait inteiro validados uma vez; correção de flicker aguarda reteste |
| ADB no próprio Termux | `experimental` | uma conexão manual real chegou a `device` e passou identidade; repetição/reconnect pendentes |
| Screenshot PNG por ADB | `experimental` | PNG real 720 × 1520, portrait/0°, ~1 FPS observado uma vez |
| Controle Android vinculado ao frame | `experimental` | controles testados pelo proprietário funcionaram após `52c7510`; matriz completa/repetição pendentes |
| Wake/sleep e `adb input text` | `experimental` | não executados no aparelho |
| H.264/scrcpy e PowerShare | `experimental` | não implementados |
| Operações que exigem root/privilégio de sistema | `privileged_required` | permanecem fora do projeto |

## Não validado no hardware

- repetição do self-ADB/reconnect e comportamento após mudança da porta do serviço;
- rotação diferente de 0° e mudança real de orientação durante frame/ação;
- tap, swipe, long press, HOME, BACK, RECENTS, ENTER e volume;
- wake/sleep e texto ASCII;
- correção de flicker, stale real, pós-condições, fullscreen móvel e matriz individual de gestos/teclas;
- LAN com WAN indisponível, soak e consumo térmico/energético.

ADB permaneceu `enabled: false` durante a validação M2.1. Na campanha M2,
pareamento/conexão e configuração foram ações manuais do proprietário; o
provider foi habilitado somente após identidade verificada. O projeto não
executou `disconnect`, `kill-server`, `tcpip`, `root`, `unroot`, reboot,
revogação, alteração de Wi-Fi ou ação sobre SSH.

## Validação no host desta branch

- ambiente de teste: Python 3.12.13 com os pins exatos do runtime;
- backend: 61 testes passaram e 1 regressão POSIX de SIGTERM foi pulada no
  Windows; a suíte inclui import em subprocesso, versões, LAN por socket/rota,
  `Range` recusado, timeout de shutdown, ADB degradado e todos os contratos M2;
- a regressão SIGTERM fica habilitada automaticamente em Linux/Termux e mantém
  um WebSocket autenticado aberto durante o sinal;
- frontend 0.2.1: `npm test` passou typecheck e 12 regressões de apresentação,
  layout e geometria; `npm run build` gerou 22 módulos e assets locais;
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
- no fechamento M2.1 anterior, a matriz foi repetida: 59 testes backend passaram
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
5. Self-ADB, PNG, viewport e controles exercitados foram comprovados uma vez;
   flicker, matriz completa de ações, stale/orientação e repetição permanecem.
6. HTTP LAN não oferece confidencialidade e `:8080` não deve ser publicado por
   WAN ou túnel.
7. Android/One UI ainda pode matar Termux e `sshd`; runit não garante uptime do
   app Android.

## Próximo passo seguro

M2.1 está aceita e o núcleo funcional do M2 passou no hardware. O próximo passo
é implantar somente a correção de apresentação e confirmar ausência de flicker,
controle contínuo e preservação do portrait/letterbox. O próximo milestone
novo numerado no `PLAN.md` é M3 (observabilidade local avançada), ainda não
autorizado. Não iniciar M3, PowerShare, H.264 ou outro milestone.
