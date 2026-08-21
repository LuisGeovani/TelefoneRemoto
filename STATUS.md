# Estado atual

- **Atualizado em:** 2026-08-20 (America/Rio_Branco)
- **Branch:** `codex/m2.2-persistent-auth`
- **Versão:** `0.2.2`
- **Milestone:** M2.2 implementada e validada no host; hardware pendente
- **Base validada no S10:** `38e09631580e8dcb62aa88e896a3cca445cacc0d`
- **Push:** autorizado pelo proprietário se toda a validação ficar verde

## Fechamento real do M2

O proprietário aprovou o fechamento do M2 no Samsung Galaxy S10+ SM-G975F
real. No commit base acima foram observados:

- self-ADB funcional e identidade esperada validada;
- stream PNG funcional, portrait 720 × 1520 correto e aproximadamente 1 FPS;
- imagem sem flicker e último frame preservado entre atualizações;
- texto auxiliar sem flicker;
- HOME, BACK, RECENTS, tap, swipe e long press funcionais;
- controles continuaram utilizáveis entre frames.

Pareamento/conexão ADB e configuração foram ações manuais do proprietário. O
projeto não executou `kill-server`, `tcpip`, root/unroot, reboot, revogação,
mudança de Wi-Fi ou ação sobre SSH. Fingerprint, target, chaves e screenshots
reais não foram registrados no Git.

Capacidades não citadas na evidência — ENTER, volume, wake/sleep, texto ASCII,
rotação real e stale real — continuam sem validação individual no hardware.
Uma campanha única não satisfaz o critério de `guaranteed`; ADB/PNG/controle
continuam classificados como `experimental`.

## Resultado da M2.2

A M2.2 substitui bootstrap cotidiano por autenticação persistente:

- exatamente uma conta administrativa, sem cadastro público/múltiplos usuários;
- username configurável e senha scrypt com salt aleatório;
- nenhum password, hash real ou segredo é versionado;
- sessão opaca armazenada por digest no SQLite privado;
- cookie `HttpOnly`, `SameSite=Strict`, `Path=/`, `Max-Age` e `Expires` de 30
  dias; `Secure` configurável e desligado no HTTP LAN atual;
- sessão sobrevive a recriação do app usando o mesmo diretório de estado;
- logout exige cookie, CSRF e Origin e revoga a sessão atual;
- recuperação troca a senha, incrementa `auth_version` e invalida sessões
  anteriores;
- bootstrap serve somente a `/setup` e `/recovery`; a troca direta antiga foi
  removida;
- `s10-control auth status`, `auth reset --yes` e `bootstrap-token` preservam
  recuperação local sem mostrar hashes/sessões;
- limitador de login em memória reserva cinco tentativas por cliente em 60
  segundos, com cardinalidade bounded e limpeza após sucesso/restart;
- WebSocket mantém cookie/Origin e revalida a sessão durante o stream e ACK;
- UI oferece setup, login, recovery, usuário atual e Sair sem Web Storage;
- SQLite migra aditivamente a coluna `auth_version`; config antiga recebe o
  default de 30 dias sem reescrever JSON/estado local.

O hash escolhido é scrypt da biblioteca padrão (`N=16384`, `r=8`, `p=1`).
Argon2id não foi adicionado porque sua extensão nativa ainda não foi comprovada
no Python 3.14/Termux aarch64 do S10. A decisão e suas consequências estão no
ADR 0007.

## Migração esperada no aparelho

O update preserva `~/.local/share/s10-control/`. Uma instalação M2 existente
não possui `admin_account`; suas sessões bootstrap legadas falham fechadas, mas
o servidor continua ready. O proprietário obtém bootstrap pela CLI local, cria
a conta uma vez em `/setup` e passa a usar `/login`.

Nenhum arquivo local precisa ser editado, removido ou copiado ao repositório.
Não foi executada qualquer ação no S10 nesta branch.

## Evidência anterior do hardware

Antes da M2.2 já estavam comprovados uma vez no SM-G975F:

| Item | Evidência observada |
|---|---|
| Runtime | Termux aarch64, Python 3.14.6 |
| Stack | FastAPI 0.118.3, Pydantic 1.10.26, Starlette 0.48.0 |
| Lifecycle M2.1 | update/smoke, SIGTERM/restart com PID novo e ready recuperado |
| Recuperação | duas sessões SSH e rota scrcpy USB preservadas |
| LAN | listener `0.0.0.0:8080`, Dashboard e WebSocket acessíveis de outro equipamento |
| Métricas | CPU, RAM, storage, rede, Internet/SSH e bateria via Termux:API |
| Tela | PNG 720 × 1520 portrait, contain correto, aproximadamente 1 FPS |
| Controle | HOME/BACK/RECENTS/tap/swipe/long press e lease entre frames |
| UX M2 | frame e texto auxiliar sem flicker |

LAN sem WAN e soak térmico/energético continuam pendentes. O teste M2.1 de
restart, versões e LAN foi real, mas seus identificadores de processo/endereço
foram omitidos daqui por não serem necessários à reprodução.

## Classificação e estado verificável

| Capacidade | Classe | Estado/evidência |
|---|---|---|
| Runtime/lifecycle Termux | `probable` | Python 3.14.6, smoke e restart real validados uma vez |
| Core, health, Dashboard e métricas | `probable` | executados no S10; soak/LAN-sem-WAN pendentes |
| Listener/LAN | `probable` | acesso LAN e telemetria privada real observados |
| SSH observacional | `probable` | serviço preservado e somente leitura |
| Termux:API/bateria | `probable` | APK+CLI compatíveis responderam |
| ADB no próprio Termux | `experimental` | conexão manual e identidade validadas uma vez |
| Screenshot PNG ADB | `experimental` | 720 × 1520 portrait/~1 FPS observado uma vez |
| Controle frame-bound | `experimental` | seis famílias de ação validadas no painel |
| Auth M2.2 | `probable` | host-validated; ainda não instalada/testada no S10 |
| H.264/scrcpy integrado/PowerShare | `experimental` | não implementados |
| Operações root/sistema | `privileged_required` | fora do projeto |

## Validação no host da M2.2

- backend completo: 75 testes passaram; 2 skips esperados no Windows
  (permissões POSIX e SIGTERM real);
- a suíte inclui migração, persistência, revogação, rate limiting atômico,
  HTTP/WS anônimo, WebSocket autenticado e todos os contratos M2;
- frontend: 21 testes/typecheck passaram; build Vite 0.2.2 gerou 23 módulos e
  assets locais;
- `compileall` de source, testes e smoke passou;
- `pip check`: `No broken requirements found`;
- smoke direto: ready com Python 3.12.13 e os pins FastAPI 0.118.3, Pydantic
  1.10.26 e Starlette 0.48.0;
- `bash -n` passou para install, update e runit.
- `git diff --check` passou; 1.688 linhas adicionadas foram verificadas contra
  IP privado real, chave privada/SSH, fingerprint preenchida, cookie e token
  longos, sem achados;
- revisão do instalador confirmou que update não reinicia serviços e que uma
  reinstalação com conta configurada não gera bootstrap de recuperação.

Os skips de bits POSIX e SIGTERM continuam obrigatórios no Termux durante a
validação de hardware. Nenhuma chamada desta branch tocou o S10, ADB, SSH,
Wi-Fi ou configuração real.

## VEX estreita: Starlette 0.48.0

Starlette 0.48.0 permanece em ranges afetados por advisories. O ADR 0004 registra
links e mitigação: todo `Range` é recusado antes de `FileResponse`; não há
decisão por `request.url`, forms/multipart, `StaticFiles` no runtime,
`HTTPEndpoint` ou deploy Windows. A M2.2 não amplia essas superfícies. Qualquer
mudança nelas invalida a VEX e exige nova revisão.

## Riscos remanescentes

1. A M2.2 ainda não foi executada no Python 3.14/Termux real; custo do scrypt e
   persistência após restart precisam ser medidos no aparelho.
2. HTTP LAN não oferece confidencialidade para senha/cookie. A porta 8080 não
   deve ser publicada em WAN/túnel; `Secure` só pode ser ligado com HTTPS.
3. O rate limiter é intencionalmente em memória e reinicia com o processo; não é
   proteção contra ataque distribuído.
4. Pydantic 1 não tem suporte upstream formal para Python 3.14, apesar da
   combinação fixada ter funcionado no S10.
5. A VEX da Starlette depende da superfície continuar estreita.
6. Android/One UI ainda pode matar o processo Termux e `sshd`; runit não garante
   uptime do aplicativo Android.
7. Sobrevivência ao reboot é propriedade do estado/cookie, mas reboot não será
   executado para validar esta branch sem autorização e rota de recuperação.
8. O cookie é vinculado à origem; mudança do endereço/hostname LAN após reboot
   exige novo login embora a sessão continue persistida no servidor.

## Próximo passo seguro

Implantar **somente M2.2** pelo runbook de autenticação, preservar config/SQLite,
ADB, Wi-Fi, SSH e rota scrcpy, e validar setup, login persistente, restart apenas
de `s10-control`, logout, recuperação e Tela Remota autenticada. Não iniciar M3,
Tailscale, PowerShare, H.264, terminal, arquivos ou outro milestone antes do
aceite real da autenticação.
