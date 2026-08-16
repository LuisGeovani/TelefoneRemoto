# Regras permanentes para agentes

Este arquivo vale para todo trabalho futuro no repositório. Leia integralmente
`SPEC.md`, `ARCHITECTURE.md`, `PLAN.md` e `STATUS.md` antes de alterar código.
Em caso de conflito, as proibições de segurança deste arquivo prevalecem.

## Contexto imutável do projeto

- O dispositivo-alvo é um **Samsung Galaxy S10+ SM-G975F, Exynos, ARM64**.
- O **display físico não funciona**. Não presuma que haverá confirmação visual
  ou toque disponível no próprio painel.
- O ambiente de execução é o **Termux** no Android.
- O aparelho **não tem root**. Não desenhe soluções que dependam de `su`,
  Magisk, SELinux permissivo, `CAP_SYS_ADMIN`, systemd, Docker ou chroot real.
- A arquitetura é **LOCAL-FIRST**.
- **Internet é opcional**. O acesso pela LAN deve funcionar sem Internet.
- Acesso remoto é um complemento da LAN, jamais sua substituição ou
  pré-condição.
- O sistema deve degradar graciosamente quando ADB, Internet, túnel,
  Termux:API, companion ou outro provider falhar.

## Proibições absolutas

Nenhum código, teste, script, endpoint, migração ou ação automática pode:

- reiniciar ou desligar o telefone;
- executar ou preparar factory reset, wipe, recovery wipe ou apagamento global;
- revogar ADB, esquecer chaves ADB, apagar chaves do host ou desativar USB/
  Wireless Debugging;
- desabilitar, reiniciar ou reconfigurar automaticamente o Wi-Fi;
- desabilitar, parar, reiniciar, reconfigurar ou remover o SSH/`sshd`;
- remover, desabilitar, congelar ou substituir componentes Android críticos;
- alterar bootloader, partições, `/system`, `/vendor`, `/data/system`, SELinux
  ou Verified Boot;
- expor à rede uma API de `adb shell` arbitrário ou um nome de serviço/pacote
  arbitrário recebido do cliente.

Essas ações não devem existir na API normal. Uma ferramenta de diagnóstico não
pode executá-las nem “só para testar”. Se alguma investigação parecer exigir
uma delas, pare e peça decisão explícita ao proprietário. Mesmo com autorização,
reboot e recuperação física são operações manuais do proprietário, nunca uma
automação deste projeto.

## Proteção dos canais de recuperação

- `sshd` é serviço protegido e somente leitura para o gerenciador do projeto.
- A configuração e as chaves ADB existentes são preservadas.
- Testes de falha de ADB usam provider falso, serial inválido ou injeção de
  falha; nunca revogação real.
- Testes de falha de Internet cortam apenas a WAN fora do telefone ou usam um
  endpoint de túnel inválido; o Wi-Fi do telefone permanece ligado.
- Testes de serviços nunca param o SSH real.
- Teste de boot fica bloqueado até haver backup, rota DeX/HDMI funcional, ADB
  externo previamente autorizado, método de primeiro desbloqueio comprovado e
  autorização explícita do proprietário.

## Regras arquiteturais

- Manter um monólito modular pequeno no Termux; não introduzir microserviços.
- Toda integração externa implementa um port/provider e publica capacidade e
  estado de runtime separadamente.
- Ausência de provider é estado esperado (`unavailable`, `permission_required`,
  `unsupported`), não erro fatal do processo.
- Backend, autenticação, UI, health e LAN não dependem de ADB nem de Internet.
- ADB usa alvo explícito e valida modelo/fingerprint antes de qualquer ação.
- Comandos Android são tipados e allowlisted; nunca concatenar shell a partir
  de entrada remota.
- PowerShare começa como `unsupported/unknown`; qualquer automação Samsung é
  experimental, opt-in, limitada a uma tentativa e exige verificação posterior.
- Controle “às cegas” fica desabilitado por padrão. Um evento de toque deve
  referenciar frame, dimensões e rotação conhecidos.
- O terminal web normal não expõe `$SHELL`, `adb shell` ou comando arbitrário.
  Ele executa somente o console interativo allowlisted do projeto. O SSH manual
  existente é o canal break-glass e permanece fora da API de automação.
- Ações destrutivas de arquivos usam lixeira/rename recuperável quando possível;
  roots editáveis são explícitas e protegidas contra traversal e symlink escape.
- Home, `.ssh`, `.android`, configuração/estado do servidor, prefixo Termux,
  `.git`, chaves, bancos e segredos nunca são roots, inclusive por opt-in.
- Segredos, tokens, chaves, bancos, logs, capturas e gravações nunca entram no
  Git.

## Compatibilidade e dependências

- O runtime precisa funcionar em Android/Termux **aarch64 com Bionic**. Binário
  Linux/glibc comum não é considerado compatível.
- Prefira dependências existentes no repositório oficial do Termux e bibliotecas
  Go puras/pequenas.
- Não adicione dependência nativa, CGO, APK companion ou pacote npm de runtime
  sem uma prova documentada no S10 real.
- O frontend deve ser compilado para arquivos estáticos locais; CDN, fonte
  remota, telemetria cloud e login cloud são proibidos no caminho principal.
- Não hardcode caminhos internos do Termux. Resolva diretórios a partir do
  ambiente e normalize-os.

## Qualidade, testes e classificação

- Cada mudança deve ter teste automatizado compatível com host quando possível
  e roteiro de teste seguro no S10 real.
- Não marque uma capacidade como `guaranteed`, um estado runtime como `ready` ou
  uma capacidade como validada com base apenas em emulador, documentação ou
  outro modelo. `guaranteed` exige evidência repetível do SM-G975F registrada em
  `STATUS.md` sob pré-condições explícitas.
- Preserve quatro classes: `guaranteed`, `probable`, `experimental` e
  `privileged_required`. Preserve separadamente o estado atual do provider.
- Experimentos ficam atrás de feature flag desativada por padrão e têm timeout,
  circuit breaker e fallback.
- Todo subprocesso tem deadline, limite de saída, cancelamento e encerramento
  apenas do processo que o projeto criou.
- O teste deve comprovar degradação: a falha de ADB/túnel/provider não pode
  derrubar health, autenticação ou acesso LAN.

## Disciplina de escopo e documentação

- Implemente somente o milestone autorizado pelo proprietário.
- Atualize `STATUS.md` no mesmo commit que muda o estado do projeto.
- Mudanças de arquitetura aceitas ganham ADR em `docs/adr/`; uma decisão antiga
  não é reescrita silenciosamente, é substituída por novo ADR.
- Se um fato depender do firmware, permissão ou estado real do aparelho,
  marque-o como não verificado e crie um probe read-only em milestone apropriado.
- Não transforme hipótese em requisito nem resultado de comando em sucesso sem
  pós-condição observável.

## Git e entrega

- `main` deve permanecer utilizável; trabalho futuro usa branches
  `codex/<milestone>-<tema>`.
- Use Conventional Commits, commits pequenos e lockfiles versionados.
- Não reescreva histórico compartilhado e não faça force-push.
- **Faça push somente após autorização explícita do proprietário.**
- Antes de pedir push: execute testes aplicáveis, revise `git diff --check`,
  mostre commits e informe exatamente o que ainda não foi testado no S10.
