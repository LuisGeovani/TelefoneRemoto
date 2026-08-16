# Estado atual

- **Atualizado em:** 2026-08-15 (America/Rio_Branco)
- **Branch de trabalho:** `codex/m2-adb-screen-control`
- **Versão:** `0.2.0`
- **Milestone:** M2 implementado e testado no host; validação no SM-G975F pendente
- **Push:** autorizado pelo proprietário para a conclusão desta tarefa

## Entregue

O M1 continua funcional: backend FastAPI/SQLite, autenticação, health, métricas,
Dashboard, LAN, SSH observacional, PWA, scripts Termux e serviço runit não
dependem de ADB nem de Internet.

O M2 acrescenta:

- `AdbController` abstrato e adapter por subprocesso com estados `available`,
  `unavailable`, `unauthorized`, `connecting` e `error`;
- feature flag ADB desativada por padrão e habilitação somente pela configuração
  privada revisada no runbook;
- discovery opt-in por `adb devices -l`/mDNS, preferência de target sem assumir
  `127.0.0.1:5555` e rediscovery de porta já conectada somente quando o candidato
  é inequívoco; chamar o cliente pode iniciar o servidor ADB/mDNS local;
- target explícito em toda operação, modelo fixo `SM-G975F` e fingerprint local
  obrigatória antes de captura ou input;
- deadlines, scheduler ADB limitado com prioridade de controle/burst justo,
  saída limitada, backoff e serialização de subprocessos; somente o
  processo-cliente criado pelo projeto é encerrado em timeout;
- `MockAdbController`, `ScreenProvider` e captura PNG por
  `adb -s TARGET exec-out screencap -p`;
- rotação medida antes/depois do PNG no mesmo gate e geração monotônica da
  identidade ADB, inclusive `transport_id`, incorporada ao frame;
- WebSocket autenticado/same-origin em baixa frequência, uma fila latest-only
  por cliente, registry por sessão/stream, ACK exato com confirmação do servidor
  e revalidação periódica de sessão revogada/expirada mesmo sem novos frames;
- tela remota mobile-first com reconnect, fullscreen, resolução, orientação,
  aspect ratio, FPS e estados ADB/stream;
- tap, swipe, long press, HOME, BACK, RECENTS, ENTER, volume, wake, sleep e texto
  ASCII restrito, sempre tipados e vinculados à sessão, frame, display, rotação,
  target e geração atuais, com revalidação imediatamente antes do input;
- CSRF, Origin/Host, papel admin/operator, rate limit, confirmação adicional de
  sleep e recusa de campos/comandos desconhecidos;
- service worker v2 com navegação network-first para não reter um `index.html`
  antigo depois de update;
- TypeScript 6.0.2 portátil em JavaScript; FastAPI 0.124.4/Starlette 0.50.0,
  Pydantic 1.10.26 puro, Uvicorn 0.51.0 e wsproto 1.3.2;
- instalação nova cria o serviço runit desabilitado para revisão e não inicia o
  listener automaticamente;
- ADR 0003 e runbook manual seguro para validação no aparelho real.

Não existe endpoint de shell, keycode numérico, package ou intent arbitrário. O
M2 não contém H.264, scrcpy, `screenrecord`, PowerShare, terminal web, túnel,
package manager ou file manager.

## Classificação e estado verificável

| Capacidade | Classe | Evidência atual |
|---|---|---|
| Core, auth, health e Dashboard sem Internet/ADB | `probable` | testes de host; S10 pendente |
| Listener e acesso LAN `0.0.0.0:8080` | `probable` | implementação M1; LAN real pendente |
| ADB no próprio Termux | `experimental` | fake/contrato no host; transporte real pendente |
| Screenshot PNG por ADB | `experimental` | parser/provider/WebSocket testados com mock |
| Controle Android vinculado ao frame | `experimental` | coordenadas/rotação/allowlist testadas com mock |
| Wake/sleep e `adb input text` | `experimental` | execução reportada como `unverified` |
| H.264/scrcpy e PowerShare | `experimental` | não implementados neste milestone |
| Operações que exigem root/privilégio de sistema | `privileged_required` | permanecem fora do projeto |

Nenhuma capacidade está classificada como `guaranteed`: não houve evidência
repetível no Samsung Galaxy S10+ SM-G975F real.

## Validação executada no host

- Python 3.12.13: `compileall` passou;
- backend: 54 testes passaram, incluindo configuração segura, parsers/estados
  ADB, fingerprint, mudança de porta, timeout/limite de saída, mock, PNG,
  rotação durante captura, coordenadas, frame stale durante espera, isolamento
  por sessão/stream, geração/target/transport, backpressure, ACK tardio,
  revogação WebSocket e durante input, prioridade do gate, CSRF e degradação sem
  ADB/Internet;
- os testes de ADB usam runner/provider falso ou subprocesso Python controlado;
  nenhum comando chamou um ADB real;
- frontend com Node 22.20.0/npm 10.9.3 e TypeScript 6.0.2: `npm test`
  (typecheck) e `npm run build` passaram; build Vite gerou 21 módulos e assets
  locais;
- o lock atualizado instalou sem requisitos quebrados; Pydantic 1.10.26 e
  wsproto 1.3.2 são wheels puros, e os protocolos Uvicorn foram fixados em
  `asyncio`/`h11`/`wsproto`;
- instalação editável em venv limpa passou, `s10-control version` retornou
  `0.2.0` e os assets compilados foram resolvidos a partir do repositório;
- smoke Uvicorn real em `0.0.0.0:8080` passou para ready, SPA e handshake
  WebSocket autenticado; com ADB desativado o stream reportou `unavailable` sem
  afetar ready;
- smoke visual em viewport móvel carregou a SPA, CSS, PWA e tela de login sem
  overflow ou erros no console; o painel autenticado continua coberto por API/
  WebSocket e aguarda navegador móvel real;
- nenhum reboot, reset, alteração de Wi-Fi/SSH/ADB, captura real ou ação Android
  foi executado.

## VEX temporária: Starlette 0.50.0

O scanner sinaliza `GHSA-86qp-5c8j-p5mr`, `GHSA-wqp7-x3pw-xc5r`,
`GHSA-x746-7m8f-x49c`, `GHSA-jp82-jpqv-5vv3` e
`GHSA-82w8-qh3p-5jfq`, publicadas em 2026, mas os caminhos afetados não são
alcançáveis nesta configuração: o projeto não usa
`request.url`, `request.form()`, `StaticFiles` nem `HTTPEndpoint`; o middleware
decide cache pelo `scope["path"]`; e o runtime-alvo é Android/Termux, não Windows
UNC. Um teste envia `Host` malformado e comprova que ready continua roteado e
com `Cache-Control: no-store`.

Esta é uma declaração de não alcançabilidade, não uma afirmação de que a versão
está corrigida. Qualquer uso futuro dessas APIs ou deploy no Windows invalida a
VEX. A correção upstream completa exige Starlette 1.3.1; a linha atual do
FastAPI que a suporta exige Pydantic 2/pydantic-core nativo, proibido até haver
prova no S10 Termux. Reavaliar a pilha imediatamente após essa prova de
compatibilidade.

## Ainda não validado no S10 real

- instalação/lock Python e build Vite no Termux aarch64/Bionic;
- bind e uso pela LAN com Internet indisponível;
- `android-tools`, self-ADB/Wireless Debugging e mudança de porta após boot;
- modelo/fingerprint reais, autorização já existente e comportamento do
  firmware Android 12/One UI;
- PNG real, parsing de `dumpsys input`, orientação, fullscreen móvel e gesto;
- consumo de CPU/RAM/bateria/temperatura entre 0,2 e 2 FPS e soak de 30 minutos;
- HOME/BACK/RECENTS/ENTER/volume/wake/sleep, texto ASCII e pós-condições;
- tela lógica com painel físico apagado, DeX/multi-display, keyguard, DRM e
  janelas `FLAG_SECURE`.

## Limitações e riscos

1. Self-ADB é experimental: autorização inicial pode exigir DeX/HDMI e a porta
   Wireless Debugging pode mudar; conectar/parear continua sendo ação manual.
   Mesmo probes `devices`/mDNS podem iniciar o servidor ADB local e tentar
   reconectar peers já pareados, por isso o provider é opt-in.
2. Fingerprint muda após update de firmware e deve ser conferida e recadastrada
   manualmente; divergência falha fechada.
3. PNG por subprocesso é uma sequência de screenshots, não vídeo: pode ter
   latência, tráfego, custo térmico e energético relevantes.
4. Se a rotação não puder ser lida, a imagem continua visível, mas todo controle
   fica bloqueado.
5. `FLAG_SECURE`, DRM, keyguard ou tela lógica apagada podem produzir imagem
   preta; o projeto não tenta bypass.
6. Somente display 0 foi modelado. DeX/multi-display não foi validado.
7. Texto está limitado a `[A-Za-z0-9 .,@_+-]`; Unicode/IME Samsung permanece
   experimental.
8. Exit code zero do input não comprova mudança da UI; respostas são
   `unverified` até existir pós-condição observável.
9. HTTP na LAN não oferece confidencialidade; não publicar `:8080` por WAN ou
   túnel nesta etapa.
10. O frontend passou typecheck/build, mas não teste DOM/visual automatizado nem
    navegador móvel real; a portabilidade do build TypeScript 6 no S10 ainda
    precisa ser comprovada.
11. O stack Python anuncia Python 3.14 e evita wheels nativos, mas a instalação
    real depende de `python-pip`/`python-ensurepip-wheels` do Termux e permanece
    não validada no aparelho.
12. Starlette 0.50.0 permanece em versão afetada por advisories recentes; a VEX
    acima depende do conjunto atual de APIs, do runtime Termux e dos testes de
    Host/path. Scanner deve continuar reportando até uma atualização compatível.

## Próximo passo seguro

Não implementar outro milestone. Com o proprietário presente, SSH confirmado
de outro equipamento e rota visual DeX/HDMI disponível, executar somente o
[`runbook ADB/PNG/controle`](docs/operations/adb-screen-control-safe.md). Registrar
firmware, versões, estados e medições sanitizadas aqui. Qualquer correção deve
ficar restrita à compatibilidade do M2; H.264/scrcpy e novos recursos continuam
fora do escopo até nova autorização.
