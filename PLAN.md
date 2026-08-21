# Plano de entrega e validação

O trabalho avança por milestones estritos. Um milestone só começa após aceite do
anterior e autorização do proprietário. Todos os testes reais preservam ADB,
Wi-Fi e SSH e obedecem `AGENTS.md`.

## Regras de passagem

Para concluir qualquer milestone:

- testes de host aplicáveis passam;
- build e roteiro daquele milestone passam no SM-G975F real;
- `STATUS.md` registra firmware, dependências, evidência e limitações;
- falhas esperadas produzem estado degradado, não crash;
- `git diff --check` está limpo e nenhum segredo/artefato runtime entrou no Git;
- não há push sem autorização explícita do proprietário.

Tags sugeridas são criadas somente depois do aceite, nunca antecipadamente.

## Milestone 0 — fundação documental (esta tarefa)

**Estado:** fundação documental concluída e publicada; inventário real ainda é
gate para validar capacidades no aparelho.

### Entregáveis

- especificação consolidada e matriz de viabilidade;
- arquitetura, ports, adapters e degradação;
- plano incremental e roteiro de teste real;
- estado inicial e regras permanentes dos agentes;
- estrutura de diretórios sem código de feature;
- stack/dependências escolhidas;
- repositório remoto/origem e branch `main` organizados localmente.

### Validação

- conferir que o GitHub e o workspace não tinham conteúdo anterior;
- revisar links para fontes primárias;
- verificar que todos os módulos pedidos aparecem em SPEC/ARCHITECTURE;
- confirmar por busca textual todas as proibições obrigatórias;
- validar Markdown, links locais, árvore e whitespace;
- confirmar ausência de `go.mod`, `package.json`, APK, binário ou feature.

### Teste no S10 real

Nenhum comando foi executado no S10 neste milestone. O único teste futuro
permitido para validar M0 é uma conferência read-only do inventário, sem instalar
ou mudar nada:

```sh
getprop ro.product.model
getprop ro.build.version.release
getprop ro.build.version.sdk
getprop ro.build.version.oneui
getprop ro.build.version.security_patch
uname -m
id
```

Resultado esperado: modelo/arquitetura e versões registrados em `STATUS.md`. Se
algo divergir, corrigir classificação/arquitetura antes do M1.

M0 pode encerrar a produção documental sem esse acesso porque não afirma estado
runtime; o inventário é gate obrigatório antes de validar M1 no aparelho.

**Versão sugerida após aceite:** `v0.0.1-foundation`.

## Milestone 1 — painel local funcional

**Estado:** implementado; caminho principal validado no SM-G975F em 2026-08-20.
O teste de LAN sem WAN e as medições de soak continuam pendentes.

### Escopo exato

Implementar somente o escopo autorizado pelo proprietário no ADR 0002:

1. backend Python/FastAPI com configuração JSON estruturada, SQLite, logs JSON
   e tratamento global de erros;
2. bootstrap de administrador one-time, sessão HttpOnly/SameSite=Strict,
   logout e reset local `s10-control auth reset`;
3. health, sistema, CPU, RAM, armazenamento, uptime, rede e bateria opcional;
4. estados separados para servidor, LAN, Internet, SSH, ADB e Remote Access;
5. listener LAN `0.0.0.0:8080`; Internet/ADB ausentes são degradados, não
   unhealthy; nenhum ADB é executado;
6. dashboard React/TypeScript/Vite mobile-first, dark, com PWA básica e cards;
7. serviço runit somente para `s10-control`, scripts de instalação/atualização
   sem restart do telefone nem alteração de SSH/Wi-Fi/ADB;
8. testes de parsers, métricas, Internet offline e ADB ausente; lockfile npm.

### Fora do M1

Não implementar screenshot/stream, input Android, PowerShare, terminal/ttyd,
Cloudflare, Tailscale, package manager, file manager, túnel, ServiceManager ou
companion. A bateria usa Termux:API somente se já instalada; não há instalação
automática no aparelho nem chamada ADB real.

### Testes no S10 real

Pré-condição: confirmar SSH funcional antes de começar e anotar como verificá-lo
de outro equipamento.

1. instalar dependências de build manualmente, com lista revisada pelo
   proprietário;
2. executar `python --version`, `node --version`, `uname -m` e
   `s10-control version`;
3. instalar o lock Python na venv e buildar o frontend no Termux ARM64,
   verificando que não entrou wheel glibc/extensão nativa incompatível;
4. iniciar manualmente e acessar health/UI por um segundo equipamento na LAN;
5. testar exchange one-time/expiração, token inválido, papéis, emissão,
   rotação/revogação, logout, `auth reset`, CSRF/origin e rate limit;
6. tornar a WAN indisponível **fora do telefone**, mantendo Wi-Fi e SSH ligados,
   e repetir UI/health;
7. confirmar que todos os providers aparecem indisponíveis com motivo, sem erro
   500;
8. iniciar via runit e encerrar somente `s10-control`; confirmar SSH antes,
   durante e depois;
9. medir RSS/CPU/processos por 30 minutos idle e registrar números;
10. validar config corrompida, porta ocupada e diretório read-only usando paths de
    teste, sem tocar em configuração real;
11. restaurar apenas arquivos/serviço do projeto conforme rollback.

Sem reboot. O teste de Termux:Boot não pertence ao M1.

**Versão sugerida:** `v0.1.0`.

## Milestone 2 — ADB, tela PNG e controle Android (etapa autorizada)

**Estado:** implementado e testado no host. Self-ADB, identidade, PNG real
720 × 1520 e input ADB direto foram comprovados uma vez no SM-G975F. A campanha
encontrou dois defeitos de integração (ação invalidada pelo ACK seguinte e crop
portrait); as correções passaram no host e aguardam reteste no aparelho.

O M2 combina o gateway ADB, o ScreenProvider PNG e o AndroidController porque
controle por coordenadas não pode existir sem referência visual atual. O
runbook obrigatório é
[`docs/operations/adb-screen-control-safe.md`](docs/operations/adb-screen-control-safe.md).

### Entregáveis

1. `AdbController` opcional com estados explícitos, discovery opt-in que pode
   iniciar o servidor ADB local/mDNS, target configurado e monitor com backoff
   limitado;
2. validação exata de modelo `SM-G975F` e fingerprint cadastrada manualmente
   antes de captura/controle;
3. subprocessos sem shell, com argumentos separados, deadline e limites de
   stdout/stderr;
4. `ScreenProvider` por `adb -s TARGET exec-out screencap -p`, validação de PNG,
   dimensões, rotação anterior/posterior, display, timestamp, target/geração e
   stream/frame IDs;
5. WebSocket autenticado/same-origin de frames PNG em 0,2–2 fps, um produtor,
   fila latest-only, stream individual, ACK exato, revalidação de sessão e parada
   quando não houver clientes;
6. registry por sessão contendo somente o frame mais recente confirmado;
7. tap, swipe, long press, keyevent allowlisted e texto ASCII restrito, todos
   vinculados a sessão/frame/display/rotação/target/geração ainda atuais;
8. coordenadas normalizadas, rate limit, confirmação para `sleep`, erros
   estáveis e resultado `unverified` sem pós-condição observável;
9. UI mobile-first para status ADB, frame PNG e controles habilitados apenas
   quando a referência estiver válida;
10. testes unitários/integrados com fake ADB para parser, identidade, timeout,
    limite de saída, PNG, backpressure, ACK, frame stale e allowlists.

### Fora do M2

- H.264, scrcpy-server/cliente, `screenrecord`, ffmpeg, áudio, WebCodecs,
  MediaProjection e companion;
- pareamento/autorização/conexão ADB automáticos ou por endpoint;
- `adb kill-server`, `reboot`, `root`, `unroot`, `tcpip`, revogação, limpeza de
  chaves, controle de `adbd`, Wi-Fi ou SSH;
- shell ADB genérico, package/intent arbitrário ou keycode numérico enviado pelo
  cliente;
- bypass de keyguard, DRM, `FLAG_SECURE` ou diálogo protegido;
- promoção para `guaranteed` antes de evidência repetível registrada no S10.

### Testes no host

1. fake `adb devices -l` com nenhum, um, múltiplos, offline e unauthorized;
2. target explícito, modelo falso e fingerprint falsa falham fechados;
3. argv capturado prova `-s` e ausência de shell/metacaracteres;
4. timeout e saída excessiva encerram somente o subprocesso do teste;
5. PNG inválido, truncado, enorme e dimensões inválidas são recusados;
6. fila por cliente nunca excede um frame; ACK antigo ou de outra sessão não
   reautoriza frame;
7. todos os controles recusam frame ausente/stale, rotação durante captura,
   sessão ou geração/target divergentes, inclusive após espera pelo gate ADB;
8. coordenadas, duração, key allowlist e regex de texto exercitam limites;
9. strings proibidas não aparecem como operações alcançáveis;
10. falha total de ADB mantém health, auth, métricas, UI e LAN nos testes.

### Testes no S10 real

Pré-condições: proprietário presente, SSH confirmado de outro equipamento,
rota visual funcional (DeX/HDMI ou scrcpy USB já autorizado nas condições do
runbook) e ADB já autorizado/pareado manualmente. O backend não faz a primeira
autorização.

1. executar o inventário opt-in, reconhecendo que `adb devices -l` pode iniciar
   servidor/mDNS local, e registrar firmware/Termux sem segredos;
2. definir manualmente target e fingerprint conforme o runbook; confirmar modelo
   exato e recusa de fingerprint divergente sem auto-enrollment;
3. capturar uma tela comum, validar assinatura PNG, dimensões, rotação,
   timestamp e checksum; repetir com painel físico apagado;
4. medir sequência PNG em 0,2, 1 e 2 fps; confirmar latest-only, ACK,
   desconexão do último cliente e memória limitada;
5. em app de laboratório, testar tap, swipe, long press, HOME/BACK e texto ASCII
   no frame atual; não usar lockscreen, banco ou Settings críticos;
6. expirar o frame e mudar rotação entre frame/ação; exigir recusa sem input;
7. registrar Unicode/IME, `dumpsys input`, self-ADB e tela apagada como
   experimentais quando divergirem;
8. usar target inexistente para provar degradação, sem revogar ADB, parar Wi-Fi
   ou afetar SSH/LAN;
9. confirmar por inspeção/teste negativo a ausência de `kill-server`, `reboot`,
   `tcpip`, pair/connect automáticos, shell/package/intent arbitrários e H.264;
10. manter 30 minutos em 1 fps, registrando CPU, RSS, bateria, temperatura,
    latência e gaps sem declarar SLA;
11. restaurar somente config/serviço do projeto e reconfirmar SSH.

**Versões:** o M2 funcional foi entregue como `0.2.0` e estabilizado como
`0.2.1`. Self-ADB, PNG e controle permanecem experimentais até o runbook passar
no SM-G975F.

## Estabilização M2.1 — reconciliação com hardware (autorizada)

**Estado:** implementada e validada no SM-G975F real; não adiciona
funcionalidade nem abre um novo milestone.

### Escopo exato

1. reconciliar o lock com Python 3.14.6, FastAPI 0.118.3, Pydantic 1.10.26 e
   Starlette 0.48.0, combinação comprovada no SM-G975F;
2. executar smoke de import/versões em instalação e atualização;
3. limitar o shutdown gracioso do Uvicorn e testar SIGTERM com servidor real e
   WebSocket ativo em ambiente POSIX;
4. descobrir endereço LAN sem depender de `iproute2` ou nome de interface;
5. documentar com precisão a VEX de Starlette 0.48.0 e rejeitar byte ranges
   antes de `FileResponse`;
6. registrar a evidência real do deploy sem promover ADB/controle não testados.

**Versão:** `0.2.1`.

### Validação segura no S10 após instalar a branch

**Resultado em hardware:** aprovada. `update-termux.sh`, versão `0.2.1` e smoke
passaram; `sv restart s10-control` substituiu o PID `8132` por `15504`, ready e
`:8080` voltaram, Dashboard/WebSocket funcionaram após o restart, duas sessões
SSH foram preservadas e a LAN real foi reportada em `192.168.1.13`. ADB
permaneceu desabilitado.

1. manter uma sessão SSH aberta de outro equipamento e confirmar uma segunda
   conexão SSH; não reiniciar nem reconfigurar `sshd`;
2. executar `apps/server/.venv/bin/python scripts/smoke-python-runtime.py` e a
   suíte backend; confirmar Python 3.14.6 e as três versões fixadas;
3. abrir Dashboard e Tela Remota pela LAN, mantendo o WebSocket conectado;
4. executar manualmente `sv restart s10-control`, exigir término em até dez
   segundos, PID novo, ready local e novo acesso LAN;
5. confirmar que o Dashboard mostra o IP privado usado pelo cliente LAN;
6. reconfirmar SSH. Não habilitar nem alterar ADB durante esta validação.

## Milestone 3 — observabilidade local avançada (planejado, não autorizado)

O escopo ADB/snapshot originalmente previsto para M3 foi absorvido pelo M2 por
autorização explícita no ADR 0003. Este milestone passa a concentrar somente o
que excede as métricas básicas já entregues no M1.

### Entregáveis futuros

- coletores independentes com qualidade/staleness e retenção limitada;
- SSE/ring buffer para métricas;
- NetworkInspector estritamente read-only;
- adapter Termux:API opcional com timeout/circuit breaker;
- métricas ADB `dumpsys` somente após fixtures do firmware real.

### Testes futuros no S10

1. comparar CPU/RSS/disco com comandos Termux read-only;
2. confirmar IP LAN mostrado e acesso manual sem WAN;
3. validar Termux:API quando APK/CLI compatíveis existirem;
4. simular timeout/provider ausente sem alterar Wi-Fi;
5. soak de 6 horas com retenção limitada e registro de gaps;
6. comprovar ausência de endpoint para rádio, rota, firewall ou hotspot.

## Milestone 4 — estabilização ADB/controle (planejado, não autorizado)

O controle básico foi absorvido pelo M2. M4 só será aberto após os resultados do
runbook real e um novo aceite. Possíveis itens são pós-condições por comparação
de frame, fixtures de rotação do firmware e revisão da allowlist. Unicode,
intents e novos keycodes não entram automaticamente: cada ampliação exige
evidência, teste negativo e decisão explícita.

## Milestone 5 — arquivos e serviços confinados

### Entregáveis

- FileService com root dedicada por padrão, roots opt-in, range, upload atômico,
  limites, move e trash;
- shared storage somente quando permissionada;
- ServiceManager runit com allowlist e `sshd` read-only;
- auditoria e UI correspondentes.

### Testes no S10 real

1. usar uma root temporária do projeto; testar upload/download/checksum/cancelar;
2. testar `..`, absoluto, URL encoding duplo, symlinks para fora e corrida
   TOCTOU durante open/rename;
3. provar que `.ssh`, `.android`, config/state, prefixo Termux e `.git` não são
   roots e não podem ser alcançados por alias;
4. testar falta de espaço e arquivo grande com limite pequeno configurado;
5. validar shared storage apenas após permissão manual e remover o adapter sem
   revogar a permissão real;
6. start/stop de um serviço fictício do projeto;
7. solicitar stop/restart de `sshd` e exigir `POLICY_BLOCKED`, confirmando SSH;
8. solicitar serviço arbitrário e exigir recusa sem chamar `sv`.

**Versão sugerida:** `v0.5.0`.

## Milestone 6 — terminal web

### Entregáveis

- TerminalBroker via `ttyd` loopback executando somente
  `s10control console --profile diagnostics`;
- uma sessão por padrão, token efêmero, resize, idle/max lifetime;
- console interativo allowlisted, sem `$SHELL`/`adb shell`; SSH manual continua
  sendo o break-glass;
- console não é publicado pelo túnel remoto.

### Testes no S10 real

1. confirmar bind loopback do `ttyd`; outro host não acessa a porta interna;
2. abrir console autenticado pelo backend, redimensionar e encerrar;
3. testar token interno expirado, segunda sessão e idle timeout;
4. derrubar somente o `ttyd` criado e confirmar core/SSH intactos;
5. desconectar navegador e verificar limpeza do subprocesso;
6. medir processos/RSS por 30 min com console fechado e aberto;
7. enviar `adb reboot`, `sv down sshd`, metacaracteres e comando desconhecido
   somente como payloads proibidos contra um provider falso; todos devem ser
   recusados antes de criar processo, nunca executados no aparelho;
8. confirmar que conteúdo do console não aparece no audit por padrão.

**Versão sugerida:** `v0.6.0`.

## Milestone 7 — streaming de tela experimental

### Entregáveis

- provider scrcpy-server versionado/checksum e protocolo H.264;
- WebSocket de vídeo com backpressure;
- decoder WebCodecs e fallback automático para PNG;
- sincronização de sessão, frame, rotação e controller;
- limites de bitrate, resolução, FPS e temperatura.

### Testes no S10 real

1. validar licença/checksum/cleanup do server temporário;
2. testar Chrome/Edge/Firefox relevantes; navegador sem WebCodecs usa snapshot;
3. portrait/landscape, tela apagada, app comum e região `FLAG_SECURE` esperada
   preta, sem tentar contornar;
4. interromper socket/ADB e comprovar fallback/core;
5. soak de 60 min em perfis baixos, registrando CPU, RSS, bateria e térmica;
6. verificar backpressure com cliente lento e encerramento ao desconectar;
7. não aceitar o provider como provável até evidência repetível no SM-G975F.

**Versão sugerida:** `v0.7.0-experimental` até estabilização.

## Milestone 8 — companion Android opcional

Este milestone só ocorre se ADB/scrcpy não satisfizerem requisitos e após ADR.

### Entregáveis

- APK mínimo assinado/sideloaded, sem SDK Samsung privado;
- handshake localhost autenticado;
- MediaProjection provider com foreground service/consentimento;
- Accessibility controller separado e habilitado manualmente;
- revogação/desinstalação documentadas sem afetar Termux.

### Testes no S10 real

1. instalar manualmente e validar assinatura/hash;
2. consentir MediaProjection manualmente usando rota visual segura;
3. negar/cancelar consentimento e confirmar core normal;
4. encerrar serviço/companion e verificar remoção de capability/fallback;
5. habilitar Accessibility manualmente e testar apenas app de laboratório;
6. reboot/autostart de projeção não é testado nem prometido;
7. desinstalar companion e provar que LAN/SSH/Termux continuam.

**Versão sugerida:** separada, `companion-v0.1.0-experimental`.

## Milestone 9 — PowerShare experimental

### Entregáveis

- probes read-only de evidências disponíveis no firmware;
- provider tri-state;
- opcional adapter Samsung UI atrás de flag, somente após ADR/calibração;
- timeout, tentativa única e resultado `unverified` quando necessário.

### Testes no S10 real

1. começar exclusivamente manual pelo Quick Panel com receptor Qi conhecido;
2. registrar bateria, temperatura, timeout sem receptor e notificações;
3. comparar fontes read-only; não escrever em sysfs/settings vendor;
4. testar automação somente após identificar tile e pós-condição confiável;
5. mudar orientação/layout e exigir recusa, não toque aproximado;
6. se o estado não for verificável, concluir formalmente como
   `experimental/unsupported` em vez de forçar solução.

**Versão sugerida:** permanece experimental sem evidência robusta.

## Milestone 10 — acesso remoto opcional

### Entregáveis

- provider reverse SSH e, opcionalmente, cloudflared;
- secrets locais, restart budget, health e auditoria;
- listener loopback como upstream;
- bind remoto loopback, host key SSH fixada, HTTPS no edge e allowlist de
  Host/Origin/proxy headers;
- documentação de ameaça e desativação.

### Testes no S10 real

1. validar LAN/SSH antes de habilitar túnel;
2. acessar por rede externa somente via HTTPS com auth interna ainda obrigatória;
3. usar endpoint/credencial inválidos e confirmar backoff limitado;
4. encerrar somente o processo do túnel e confirmar LAN intacta;
5. cortar WAN externamente mantendo Wi-Fi e repetir LAN;
6. restaurar WAN e observar reconexão sem mudar endereço/listener LAN;
7. confirmar que nenhuma chave/URL sensível foi logada ou versionada;
8. provar recusa de bind remoto wildcard, público plaintext, Host/Origin não
   allowlisted e `X-Forwarded-*` vindo de cliente não confiável.

**Versão sugerida:** `v0.8.0`.

## Milestone 11 — hardening e release operacional

### Entregáveis

- backup/restore de config/state e rollback de binário;
- migrações, SBOM/checksums, limites e runbook;
- auditoria de autenticação, fuzz/property tests de paths/protocolos;
- política de update manual e health de longo prazo;
- decisão documentada sobre Termux:Boot.

### Testes no S10 real

1. soak de 24–72 h com perfis idle e uso moderado;
2. matar somente `s10-control` e comprovar recuperação runit/SSH intacto;
3. atualizar e voltar uma versão sem perder config;
4. restaurar backup em diretório de teste e comparar checksums;
5. roaming entre APs pode ser manual, mas Wi-Fi nunca é desligado pelo projeto;
6. Termux:Boot pode ser testado somente depois dos pré-requisitos de recuperação.
   Qualquer reboot é iniciado e executado manualmente pelo proprietário, com
   autorização específica; o software nunca chama `reboot`.

**Versão sugerida:** `v1.0.0` apenas após critérios globais de `SPEC.md`.

## Estratégia Git

- M0: commits `docs: define S10 Control Server architecture` e
  `chore: scaffold project foundation`;
- M1: commit funcional preservado em `codex/m1-local-dashboard`;
- M2: trabalho isolado em `codex/m2-adb-screen-control`, sem misturar H.264 ou
  milestones futuros;
- M2.1: estabilização isolada em `codex/m2.1-hardware-stabilization`;
- Conventional Commits e mudanças de estado no mesmo commit relevante;
- lockfiles obrigatórios a partir de M1;
- ADRs numerados e imutáveis por decisão relevante;
- tags anotadas somente após teste/aceite;
- push sempre precedido de pedido explícito ao proprietário.

## Instrução exata ao próximo agente

Leia os documentos raiz, ADRs 0003/0004/0005 e o runbook. **Não implemente outro
milestone.** M2.1 foi validada no SM-G975F. O próximo trabalho operacional é
implantar e retestar somente as correções de lease de frame e viewport portrait
encontradas na campanha M2, preservando rota visual e SSH. O próximo milestone
novo planejado é M3 (observabilidade local avançada), ainda não autorizado. Não adicione H.264,
scrcpy, PowerShare, pairing/connect automático, shell/intent/package arbitrário
ou feature futura.
