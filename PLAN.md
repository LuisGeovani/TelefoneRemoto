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

**Estado:** fundação documental concluída localmente; aceite e inventário real
pendentes; M1 não iniciado.

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

## Milestone 1 — fundação local (próximo agente)

### Escopo exato

Implementar somente:

1. módulo Go em `apps/server` e comandos:
   - `s10control serve`;
   - `s10control doctor` estritamente read-only;
   - `s10control version`;
   - `s10control auth reset` local, explicitamente mutável e confirmado;
2. paths portáveis, configuração JSON validada e store com escrita atômica;
3. logging estruturado, request IDs e redaction;
4. tipos comuns de capability, operation e erro;
5. NullProviders para **todos** os módulos, sem chamar ADB/Android/binários;
6. policy engine com testes negativos para as proibições de `AGENTS.md`;
7. autenticação por token bootstrap one-time, sessão, emissão por papel,
   rotação/revogação e recuperação por `s10control auth reset` local;
8. endpoints:
   - `GET /api/v1/health/live`;
   - `GET /api/v1/health/ready`;
   - `GET /api/v1/capabilities`;
9. listener HTTPS LAN em porta não privilegiada e HTTP somente loopback;
10. SPA mínima Preact/TypeScript embutida, mostrando health e NullProviders;
11. templates runit para **apenas** `s10-control`, sem instalar/alterar `sshd`;
12. unit, policy, contract e integração do core; lockfiles versionados;
13. guia de instalação manual e rollback do serviço do projeto.

### Fora do M1

Não implementar ADB real, screenshot/stream, input Android, PowerShare, métricas
reais, network inspector real, túnel, terminal/ttyd, arquivos, ServiceManager,
Termux:API ou companion. Não instalar dependência no telefone automaticamente.

### Testes no S10 real

Pré-condição: confirmar SSH funcional antes de começar e anotar como verificá-lo
de outro equipamento.

1. instalar dependências de build manualmente, com lista revisada pelo
   proprietário;
2. executar `go env`, `node --version`, `uname -m` e `s10control doctor`;
3. buildar frontend/backend no Termux ARM64 e verificar que não há dependência
   glibc;
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

## Milestone 2 — métricas locais e inspeção de rede

### Entregáveis

- coletores Go/processo/volumes acessíveis;
- NetworkInspector read-only;
- SSE, ring buffer limitado, qualidade/staleness e retenção opcional;
- adapter Termux:API opcional com timeout e capability clara;
- UI de métricas/rede sem qualquer controle de rádio.

### Testes no S10 real

1. comparar processo/RSS/disco com comandos Termux read-only;
2. confirmar IP LAN mostrado e acesso por IP manual;
3. comparar bateria Termux:API quando app/CLI compatíveis existirem;
4. remover somente o adapter da configuração e confirmar fallback/stale;
5. apontar Termux:API para timeout de teste e verificar circuit breaker;
6. cortar WAN externamente e confirmar métricas locais/SSE;
7. manter 6 horas com tela apagada e registrar gaps/morte de processo, sem
   `force-stop` e sem reboot;
8. comprovar que não existe endpoint para Wi-Fi, rota, firewall ou hotspot.

**Versão sugerida:** `v0.2.0`.

## Milestone 3 — ADB gateway e snapshot read-only

### Entregáveis

- discovery observacional, alvo explícito, estados ADB e circuit breaker;
- validação de modelo/fingerprint;
- comandos read-only tipados necessários a identidade/probes;
- `adb-screencap` PNG e metadados de frame;
- métricas `dumpsys` opcionais com fixtures por firmware;
- UI de diagnóstico ADB/snapshot.

### Testes no S10 real

Pré-condição: ADB já autorizado/pareado por rota manual segura. O projeto não
cria a primeira autorização.

1. registrar `adb version`, endpoint/serial sem segredo, `adb devices -l` e
   identidade do shell;
2. provar recusa de um serial/fingerprint falso com fake adapter;
3. capturar tela comum em PNG, validar assinatura, dimensões, rotação e checksum;
4. repetir com painel físico apagado, sem app sensível;
5. configurar endpoint inexistente e confirmar que LAN/core continuam;
6. testar estados offline/unauthorized com fixtures/fakes, **sem revogar ADB**;
7. medir frequência segura de snapshot, CPU, bateria e temperatura por 30 min;
8. confirmar ausência de pair/tcpip/revoke/reboot na API e no binário.

Se self-ADB não funcionar, registrar `experimental/unavailable`. ADB em um
computador autorizado serve somente para recuperação e comparação de testes;
não é provider do backend. Qualquer bridge remota futura exige ADR próprio.

**Versão sugerida:** `v0.3.0`.

## Milestone 4 — controle Android básico

### Entregáveis

- AndroidController ADB com key/tap/swipe/text/intents allowlisted;
- transformação frame/rotação/display e rejeição de frame stale;
- confirmações, operações auditadas e pós-condição quando observável;
- UI de controle, desabilitada sem snapshot atual.

### Testes no S10 real

1. usar página/app de teste inofensiva, nunca lockscreen, banco ou Settings
   críticos;
2. testar HOME, BACK, tap central, bordas e swipe em portrait/landscape;
3. girar entre captura e tap e provar rejeição por `STALE_FRAME`;
4. testar ASCII, espaço e acentos; registrar Unicode como experimental quando
   divergir;
5. testar timeout com fake adapter e uma ação real inofensiva;
6. comprovar via testes negativos bloqueio de power/reboot/reset/Wi-Fi/SSH e
   intents arbitrários;
7. medir latência sem prometer SLA antes da evidência.

**Versão sugerida:** `v0.4.0`.

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
7. tentar `adb reboot`, `sv down sshd`, shell metacharacters e comando
   desconhecido; todos devem ser recusados sem criar processo;
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

- M0: commits `docs: establish S10 Control Server foundation` e
  `chore: scaffold project module boundaries`;
- próximo trabalho: branch `codex/m1-foundation` criada a partir de `main` após
  publicação/aceite desta base;
- Conventional Commits e mudanças de estado no mesmo commit relevante;
- lockfiles obrigatórios a partir de M1;
- ADRs numerados e imutáveis por decisão relevante;
- tags anotadas somente após teste/aceite;
- push sempre precedido de pedido explícito ao proprietário.

## Instrução exata ao próximo agente

Leia os cinco documentos raiz e implemente **somente o Milestone 1** listado
acima. Comece por testes dos tipos comuns e das proibições, depois core/CLI,
fluxo auth completo (inclusive reset local), listeners, NullProviders, UI mínima
e template runit. Não execute probe ADB,
não instale pacote no S10 sem revisão, não crie feature de módulo e não avance ao
Milestone 2. Entregue testes de host e roteiro; a validação real só ocorre com o
proprietário presente.
