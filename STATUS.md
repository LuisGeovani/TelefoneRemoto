# Estado atual

- **Atualizado em:** 2026-08-15 (America/Rio_Branco)
- **Branch local:** `main`
- **Milestone:** M0 documental concluído localmente; aceite/inventário pendentes;
  M1 não iniciado
- **Push:** pendente de autorização explícita do proprietário

## Resumo executivo

O projeto foi iniciado como fundação documental. O repositório remoto e o
workspace estavam vazios, portanto não havia código, histórico ou especificação
anterior a preservar. A mensagem mestre desta tarefa foi consolidada em
`SPEC.md`; arquitetura e plano foram definidos sem implementar funcionalidades.

## Repositório

- remoto: `https://github.com/LuisGeovani/TelefoneRemoto.git`;
- GitHub: público, não arquivado e sem refs/commits no momento da auditoria;
- branch padrão remota indicada pelo GitHub: `main`, ainda unborn na auditoria;
- remoto local `origin` configurado;
- branch local renomeada de `master` para `main`;
- não houve fetch/merge necessário porque o remoto não contém histórico;
- nenhum push foi realizado.

## Artefatos desta fundação

- `README.md` — entrada do projeto;
- `SPEC.md` — escopo, requisitos e classificação;
- `ARCHITECTURE.md` — módulos, interfaces e dependências;
- `PLAN.md` — milestones/testes e próximo escopo;
- `STATUS.md` — este estado;
- `AGENTS.md` — guardrails permanentes;
- esqueleto em `apps/`, `contracts/`, `config/`, `deploy/`, `docs/`, `scripts/` e
  `tests/` sem código de feature;
- `.gitignore`, `.gitattributes` e `.editorconfig` de base.

## Decisões aceitas no M0

| Tema | Decisão |
|---|---|
| Topologia | monólito modular Go no Termux, não microserviços |
| UI | TypeScript + Preact + Vite, assets embutidos e offline |
| Persistência inicial | JSON atômico + NDJSON rotacionado, sem SQLite/CGO |
| Integrações | ports/providers com capability registry |
| ADB | opcional, alvo explícito, identidade validada, sem setup automático |
| Tela | snapshot ADB primeiro; scrcpy H.264 experimental |
| Controle | ADB tipado primeiro; companion opcional |
| Terminal | `ttyd` executa console allowlisted; shell completo fica no SSH manual |
| Serviços | termux-services/runit com allowlist; `sshd` protegido |
| PowerShare | nulo/unknown por padrão; UI Samsung experimental |
| Remoto | reverse SSH/cloudflared opcional; LAN inalterada |
| Estado | support class e runtime state são campos distintos |
| Segurança | LAN autenticada; HTTPS externo, HTTP apenas loopback; roots dedicadas |

## Dependências escolhidas, ainda não instaladas/validadas

Runtime/Termux: `android-tools`, `openssh`, `termux-services`; opcionais
`termux-api`, `ttyd`, `cloudflared`, `ffmpeg` e Termux:Boot. Build:
`golang` e `nodejs-lts`. Backend usa standard library e futuramente
`github.com/coder/websocket`; frontend usa TypeScript/Vite/Preact.

Não existem ainda `go.mod`, `package.json`, lockfiles, APK ou binários. As
versões serão fixadas somente no M1 após provar build aarch64/Bionic.

A licença pública do código ainda não foi escolhida; nenhuma licença foi
inventada no M0.

## Evidência técnica reunida

- o SM-G975F possui firmware Samsung Android 12/One UI 4.1 publicado;
- Android 11+ oferece Wireless Debugging, mas requer pareamento/autorização;
- self-ADB no mesmo telefone não é fluxo oficial e permanece experimental;
- `screencap`/`screenrecord` são ferramentas ADB oficiais, com limites de
  captura/áudio/rotação;
- MediaProjection exige consentimento de sessão; `FLAG_SECURE` bloqueia captura;
- AccessibilityService precisa ser habilitado pelo usuário;
- PowerShare é documentado pela Samsung via Quick Panel, sem API pública de
  controle de terceiro identificada;
- Termux alerta para processos phantom/CPU no Android 12+;
- Android/Termux isolam dados de outros apps e restringem `/proc/net`/storage;
- os pacotes Termux `android-tools`, `ttyd`, OpenSSH, runit e ffmpeg existem para
  o ambiente, mas ainda precisam de prova no aparelho exato.

Fontes estão listadas em `SPEC.md` e `ARCHITECTURE.md`.

## Validações locais desta entrega

- revisão cruzada dos seis documentos raiz sem inconsistência bloqueante;
- 20 arquivos Markdown examinados e todos os links locais resolvidos;
- documentos e diretórios obrigatórios presentes;
- guardrails mandatórios encontrados em `AGENTS.md`;
- nenhum arquivo de implementação ou manifesto de dependências criado;
- nenhum whitespace no fim de linha encontrado nos artefatos versionáveis.

Essas validações comprovam somente a coerência da fundação documental no host.
Nenhum build, serviço ou comportamento no S10 foi testado.

## O que não foi feito

- nenhum comando, instalação ou teste no S10 real;
- nenhuma conexão, autorização ou alteração ADB;
- nenhuma captura ou entrada Android;
- nenhuma tentativa de PowerShare;
- nenhum listener, terminal, túnel ou serviço iniciado;
- nenhum reboot, reset, revogação, alteração de Wi-Fi/SSH ou componente Android;
- nenhuma implementação do M1 ou posterior;
- nenhum push.

## Estado das capacidades

Como o S10 não foi sondado, todas as capacidades dependentes do aparelho estão
`unknown/unverified`. A documentação sustenta classes `probable`, `experimental`
e `privileged_required`, mas ainda nenhuma capacidade positiva `guaranteed`.
Não há provider em execução.

## Riscos prioritários

1. ADB pode não estar previamente habilitado/autorizado; não existe bootstrap
   puramente por software sem confirmação visual.
2. Um reboot acidental pode exigir primeiro desbloqueio e impedir Termux/ADB;
   por isso nunca é automático.
3. Android 12/One UI pode matar Termux ou subprocessos apesar de wake lock.
4. Porta/discovery de self-ADB pode mudar após rede/reboot.
5. A falha física pode afetar o display lógico/encoder, não só o painel.
6. `FLAG_SECURE`, keyguard e diálogos protegidos limitam captura/controle.
7. PowerShare não tem contrato público de controle/telemetria; automação de UI é
   frágil.
8. Stream contínuo pode aquecer e acelerar desgaste de uma bateria antiga.
9. DHCP/AP isolation/Doze podem interromper acesso LAN.
10. Console, arquivos e ADB aumentam severamente o impacto de falha de auth;
    shell irrestrito não será exposto pelo backend.
11. Binários Linux glibc ou pacotes nativos genéricos não funcionam no Bionic.
12. O S10 pode estar sem patches atuais; exposição WAN direta é inadequada.

## Bloqueios e dados pendentes

Antes de aceitar M1 no aparelho, obter de forma read-only:

- Android/API/One UI/build/patch/CSC e `uname -m`;
- origem e versões de Termux/add-ons;
- estado do SSH e método de recuperação DeX/HDMI;
- memória/espaço/política de bateria;
- sem modificar nada, apenas registrar se ADB já está disponível.

O PowerShare deve permanecer `unknown`; o teste de boot permanece bloqueado.

## Próxima ação autorizável

O próximo agente deve abrir branch `codex/m1-foundation` e implementar somente o
escopo de **Milestone 1** em `PLAN.md`: core/CLI/config/store/logging, tipos e
NullProviders, policy guardrails, auth completo com reset local,
health/capabilities, dois listeners, UI mínima embutida, template runit e testes.
Não deve implementar ou sondar ADB,
tela, controle, métricas reais, rede real, PowerShare, arquivos, serviços,
terminal, túnel ou companion.

M1 só começa depois de autorização explícita do proprietário.
