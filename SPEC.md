# S10 Control Server — especificação consolidada

- **Baseline:** M0
- **Data:** 2026-08-15
- **Alvo:** Samsung Galaxy S10+ SM-G975F, Exynos ARM64, Android/One UI a confirmar
- **Execução:** Termux, sem root, display físico inoperante

## 1. Autoridade e alcance

Esta especificação consolida a solicitação mestre recebida nesta tarefa, a
inspeção do repositório vazio e as restrições verificáveis das APIs oficiais de
Android, Samsung e Termux. Não havia especificação ou código anterior no GitHub.

Ordem de precedência:

1. proibições de segurança de `AGENTS.md`;
2. esta especificação;
3. decisões aceitas em `docs/adr/`;
4. planejamento e estado corrente.

Uma capacidade técnica não autoriza uma ação proibida. Por exemplo, uma sessão
ADB pode tecnicamente aceitar `reboot`, mas o projeto jamais deve chamá-lo.

## 2. Visão do produto

O S10 Control Server transforma o telefone em um nó administrável pela rede
local, apesar do painel quebrado. Um navegador na LAN deve conseguir observar o
estado do serviço e, conforme os providers disponíveis, acessar arquivos
permitidos, terminal Termux, métricas, tela e controles Android.

O servidor não promete romper o sandbox Android. Ele explicita o que está
disponível, o que está degradado e por quê. Acesso remoto usa um túnel de saída
opcional e nunca altera o caminho LAN.

## 3. Objetivos

- funcionar localmente, sem conta cloud e sem Internet;
- preservar SSH e ADB como canais de recuperação;
- oferecer API e UI autenticadas, versionadas e auditáveis;
- detectar capacidades em runtime em vez de assumir permissões;
- isolar ADB, tela, controle, PowerShare, métricas, rede, túnel, serviços,
  terminal e arquivos atrás de interfaces substituíveis;
- sobreviver logicamente à indisponibilidade de qualquer integração opcional;
- operar com poucos processos e consumo adequado a um S10 com Android 12;
- permitir validação incremental no aparelho real sem ações irreversíveis.

## 4. Não objetivos

- root, bootloader unlock, custom ROM, Magisk ou bypass de SELinux;
- burlar PIN, senha, biometria, keyguard, DRM ou `FLAG_SECURE`;
- acesso aos dados privados de outros aplicativos;
- controle silencioso garantido de PowerShare, hotspot ou rádios;
- substituir SSH, modificar o firmware ou gerenciar componentes Android
  críticos;
- disponibilidade 24/7 garantida contra o gerenciador de processos do Android;
- suporte genérico a qualquer aparelho antes de estabilizar o SM-G975F;
- depender de serviço externo para autenticação, UI ou operação na LAN.

## 5. Restrições invariantes

- O aparelho não tem root e executa binários ARM64 ligados ao Bionic por meio do
  Termux.
- O painel físico não é uma rota confiável de confirmação.
- O primeiro pareamento/autorização ADB e o consentimento MediaProjection podem
  exigir interação visível; o software não pode contorná-los.
- Android pode matar Termux e seus processos-filho. Wakelock, runit e
  Termux:Boot reduzem risco, mas não oferecem garantia de uptime.
- Portas privilegiadas (por exemplo 22, 80 e 443) não são baseline; usar portas
  acima de 1024.
- Reboot automático, factory reset, revogação ADB, desativação de Wi-Fi/SSH e
  alteração de componentes críticos são proibidos.

## 6. Requisitos funcionais

### 6.1 Núcleo/backend

- **CORE-001:** iniciar e responder health sem consultar ADB, Internet ou túnel.
- **CORE-002:** manter um registro de capacidades com classe de suporte, estado
  atual, causa, dependências, instante da última observação e validade.
- **CORE-003:** aplicar autenticação, autorização por papel, rate limit, timeout,
  limite de saída e auditoria antes de chegar a adapters de comando.
- **CORE-004:** modelar comandos demorados como operações observáveis e
  canceláveis, com idempotency key.
- **CORE-005:** carregar configuração local validada e persistir estado por
  escrita atômica; corrupção deve produzir diagnóstico, não defaults perigosos.
- **CORE-006:** falha de provider nunca encerra o processo principal.

### 6.2 Frontend

- **WEB-001:** ser uma SPA estática entregue pelo backend, sem CDN ou recurso
  obrigatório da Internet.
- **WEB-002:** derivar controles do registro de capacidades e mostrar a causa de
  indisponibilidade; não simular sucesso.
- **WEB-003:** funcionar em navegador desktop e móvel atual na mesma LAN.
- **WEB-004:** exigir nova confirmação para ações sensíveis e mostrar resultado
  verificado ou `unverified`.
- **WEB-005:** não chamar ADB, `ttyd`, túnel ou companion diretamente.
- **WEB-006:** controle por coordenadas só é habilitado para um frame confirmado
  pela mesma sessão/stream, com largura, altura, display, rotação, target e
  geração ADB correspondentes.

### 6.3 ADB

- **ADB-001:** o gateway ADB é o único módulo autorizado a iniciar `adb`.
- **ADB-002:** usar sempre endpoint/serial explícito e conferir identidade do
  alvo (`SM-G975F` mais fingerprint cadastrado) antes de ações.
- **ADB-003:** distinguir `ready`, `offline`, `unauthorized`, `not_paired`,
  `misconfigured`, `timeout` e `unavailable`.
- **ADB-004:** oferecer comandos tipados/allowlisted; nenhuma API genérica de
  shell remoto.
- **ADB-005:** nunca parear, executar `adb tcpip`, revogar, esquecer chaves,
  reiniciar `adbd` ou reiniciar o telefone automaticamente.
- **ADB-006:** reconectar com backoff limitado e sem afetar o servidor local.

### 6.4 Screen provider

- **SCREEN-001:** definir providers independentes para snapshot e stream.
- **SCREEN-002:** usar PNG por `adb exec-out screencap -p` como primeiro provider
  a validar.
- **SCREEN-003:** tratar scrcpy-server/H.264 para navegador como experimental e
  manter fallback para snapshot.
- **SCREEN-004:** publicar codec/MIME, dimensões, rotação, display, frame ID,
  timestamp e geração/target do provider; medir rotação antes/depois da captura
  e descartar divergência.
- **SCREEN-005:** reconhecer que janelas seguras podem aparecer pretas e não
  tentar contornar a proteção.
- **SCREEN-006:** encerrar somente stream/subprocesso criado pelo projeto quando
  houver timeout, cliente ausente ou pressão térmica.

### 6.5 Android controller

- **CTRL-001:** expor ações tipadas de tecla, tap, swipe, texto e abertura de
  app/intent allowlisted.
- **CTRL-002:** começar com adapter ADB `input`/`am`; adapter scrcpy ou companion
  é opcional.
- **CTRL-003:** transformar coordenadas usando os metadados do frame e rejeitar
  frame velho, de outra sessão, rotação/geração/target divergentes ou tela
  desconhecida, com revalidação dentro do gate imediatamente antes do input.
- **CTRL-004:** não prometer Unicode completo nem interação com diálogo seguro.
- **CTRL-005:** não oferecer bypass de bloqueio, confirmação de segurança, power
  menu destrutivo ou reboot.

### 6.6 PowerShare

- **POWER-001:** iniciar com provider nulo que retorna `unsupported/unknown`.
- **POWER-002:** representar estado como `on`, `off` ou `unknown`, acompanhado
  da evidência observada.
- **POWER-003:** qualquer adapter Samsung/UI é experimental, opt-in e desativado
  por padrão.
- **POWER-004:** uma solicitação explícita permite no máximo uma tentativa, com
  timeout e leitura posterior; sem confirmação, o resultado é `unverified`.
- **POWER-005:** nunca escrever em sysfs/vendor settings ou usar API oculta que
  exija root/permissão de sistema.

### 6.7 Métricas

- **METRIC-001:** coletar primeiro métricas do processo e volumes acessíveis ao
  Termux.
- **METRIC-002:** enriquecer com Termux:API e ADB apenas quando disponíveis.
- **METRIC-003:** toda amostra contém fonte, qualidade, timestamp e flag `stale`.
- **METRIC-004:** polling usa cadências e timeouts por coletor; fila e retenção
  são limitadas.
- **METRIC-005:** sob CPU/temperatura alta, reduzir métricas e stream antes de
  prejudicar health/autenticação.

### 6.8 Rede

- **NET-001:** listar endereços, interfaces, rotas/listeners visíveis e estado de
  conectividade sem modificar a rede.
- **NET-002:** aceitar acesso LAN por IP:porta sem DNS, mDNS ou Internet.
- **NET-003:** mDNS é conveniência opcional; sempre mostrar alternativa manual.
- **NET-004:** o módulo não terá operação para desligar Wi-Fi, alterar rota,
  firewall, tethering ou hotspot.

### 6.9 Acesso remoto

- **REMOTE-001:** estar desligado por padrão e depender de habilitação explícita.
- **REMOTE-002:** implementar providers substituíveis (reverse SSH como
  baseline; cloudflared opcional).
- **REMOTE-003:** o túnel conecta a listener loopback e preserva a autenticação
  local.
- **REMOTE-004:** queda ou ausência de Internet/túnel não altera listener,
  endereço, estado nem autenticação LAN.
- **REMOTE-005:** credenciais ficam em arquivo local protegido, nunca no Git.
- **REMOTE-006:** reverse SSH usa host key fixada e bind remoto loopback; a
  exposição pública exige HTTPS no edge e allowlists de Host/Origin/proxy.
- **REMOTE-007:** a classe de ingresso remoto não pode acessar rotas do console
  web, independentemente do papel autenticado.

### 6.10 Serviços

- **SERVICE-001:** integrar somente serviços allowlisted do projeto via
  termux-services/runit.
- **SERVICE-002:** `s10-control` e `s10-tunnel` podem ser gerenciáveis;
  `sshd` é protegido e somente leitura.
- **SERVICE-003:** serviços Android e nomes arbitrários são fora de escopo.
- **SERVICE-004:** o processo principal não tenta reiniciar o telefone para se
  recuperar.

### 6.11 Terminal

- **TERM-001:** terminal web é admin-only, desativável, limitado a uma sessão
  por padrão e tem idle timeout.
- **TERM-002:** usar `ttyd` do Termux em loopback somente para executar
  `s10control console`, um console interativo allowlisted; não expor `$SHELL` ou
  `adb shell` arbitrário.
- **TERM-003:** token interno é curto, aleatório e descartável.
- **TERM-004:** auditar abertura, identidade, duração e encerramento, não gravar
  conteúdo integral por padrão.
- **TERM-005:** o console web é LAN-only e não é publicado pelo túnel remoto
  gerenciado pelo projeto.
- **TERM-006:** shell irrestrito continua disponível apenas pelo SSH manual já
  administrado pelo proprietário e não é roteado pelo backend/túnel do projeto.

### 6.12 Arquivos

- **FILE-001:** expor somente roots virtuais explícitas; baseline é um diretório
  dedicado `project-share`. Home completo nunca é root; roots adicionais não
  sensíveis e shared storage são opt-in.
- **FILE-002:** aceitar somente caminho relativo e operar por handle de root/
  descritor (`os.Root` ou equivalente `openat`/no-follow), bloqueando `..`,
  caminho absoluto, symlink escape e corrida TOCTOU.
- **FILE-003:** upload usa arquivo temporário, limite de tamanho, checksum
  opcional e rename atômico.
- **FILE-004:** home, `.ssh`, `.android`, configuração/estado do servidor,
  prefixo Termux, `.git`, chaves, bancos e segredos nunca podem ser roots, mesmo
  por configuração explícita, alias ou symlink.
- **FILE-005:** exclusão usa lixeira/rename recuperável quando possível.
- **FILE-006:** não prometer `/data/data` ou `Android/data` de outros apps.

## 7. Requisitos não funcionais

- **NFR-001 Segurança:** HTTPS na LAN ou listener loopback; bearer/session token
  aleatório, papéis `viewer`, `operator`, `admin`, origem validada e logs sem
  segredos.
- **NFR-002 Local-first:** build da UI não consulta Internet em runtime; health e
  core permanecem íntegros sem WAN.
- **NFR-003 Compatibilidade:** runtime aarch64/Bionic; no M1, Python/Node são
  instalados pelo repositório oficial Termux e os pacotes Python não podem exigir
  binário glibc genérico. Qualquer extensão nativa requer prova no SM-G975F.
- **NFR-004 Recursos:** um processo principal; subprocessos sob demanda. Alvos
  iniciais a medir no M1: até 150 MiB RSS ocioso e no máximo 1% de um core em
  idle, sem transformar esses alvos ainda não medidos em garantia.
- **NFR-005 Observabilidade:** logs estruturados, request/operation IDs, health
  separado de readiness e motivo de degradação legível.
- **NFR-006 Resiliência:** deadlines, circuit breaker, backoff com jitter, filas
  limitadas e nenhuma repetição infinita de ação de controle.
- **NFR-007 Privacidade:** sem telemetria externa; retenção configurável e
  mínima; terminal e vídeo não gravados por padrão.
- **NFR-008 Evolução:** API `/api/v1`, contratos versionados e migrações de
  configuração explícitas.

## 8. Classes de viabilidade

- **Garantido:** demonstrado de forma repetível no SM-G975F real e registrado em
  `STATUS.md`, dentro das dependências e pré-condições declaradas; não significa
  que o Android manterá o processo vivo para sempre.
- **Provável:** sustentado por interface oficial ou comportamento maduro, mas
  ainda depende de permissão, configuração, firmware ou teste no SM-G975F.
- **Experimental:** depende de self-ADB, protocolo/codec, parsing instável,
  automação de UI ou detalhe Samsung não público.
- **Impossível sem privilégios adicionais:** a sandbox/permissão do Android
  impede o Termux comum; exige root, app de sistema/device owner, consentimento
  interativo ou hardware externo.

`Proibido` é uma marca independente: mesmo algo tecnicamente possível não pode
ser implementado quando ameaça recuperação ou dados.

Esta é a classificação de viabilidade solicitada para o projeto, separada do
estado de runtime. Sem probes no S10, toda capacidade dependente do aparelho
permanece `unknown/unverified`; documentação sozinha alcança no máximo
`Provável`. Portanto, nesta fundação ainda não há capacidade positiva marcada
`Garantido`. As classes impossíveis derivam de limites explícitos da plataforma
e não alegam ter executado testes destrutivos.

## 9. Matriz de viabilidade

| Capacidade | Classe | Condições e limite |
|---|---|---|
| Backend/API/UI local com processo vivo | Provável | Termux e porta >1024 disponíveis; validar no S10 |
| Acesso LAN sem Internet | Provável | mesma rede roteável, sem isolamento de clientes; validar no AP real |
| Auth, auditoria e estado local | Provável | arquivos privados do Termux íntegros; implementação/teste pendentes |
| SSH Termux já configurado | Provável | confirmar `openssh`/`sshd` vivos sem alterá-los |
| Arquivos do projeto e root dedicada | Provável | limites do UID Termux; roots sensíveis são sempre proibidas |
| CPU/RSS próprios e espaço acessível | Provável | APIs POSIX/Go; validar procfs disponível no firmware |
| Console web allowlisted no Termux | Provável | implementação futura; não expõe shell arbitrário |
| Serviços próprios via runit | Provável | pacote/execução devem ser validados no S10 |
| Shared storage | Provável | permissão Android/`termux-setup-storage`; scoped storage limita |
| Bateria/rede via Termux:API | Provável | APK e CLI da mesma origem, permissões e versão compatíveis |
| Autostart com Termux:Boot | Provável | add-on aberto uma vez, bateria/One UI permitem |
| Permanência em background | Provável | wake lock e exclusão de otimização ajudam, não garantem |
| `adb` como cliente ARM64 no Termux | Provável | pacote `android-tools` existe; instalar/validar só em milestone autorizado |
| USB ADB por computador já autorizado | Provável | confirmar debugging ativo e chave RSA já aceita, sem revogar |
| Primeira autorização ADB sem rota visual | Impossível | exige desbloqueio/aceite; usar DeX/display externo |
| Wireless Debugging Android 11+ | Provável | ativação e pareamento interativos; porta pode mudar |
| Termux conectar ao `adbd` do mesmo telefone | Experimental | cenário self-ADB não é o fluxo oficial; validar firmware/rede |
| `adb root` em firmware Samsung comercial | Impossível | `adbd` de produção não fornece UID 0 |
| Screenshot PNG via ADB | Provável | ADB ready e display lógico capturável |
| `screenrecord` | Provável | sem áudio, duração/resolução/rotação limitadas; não é stream permanente |
| Stream scrcpy-server para navegador | Experimental | protocolo H.264, encoder e decoder/browser a validar |
| MediaProjection por companion | Provável | APK + consentimento visível + foreground service |
| MediaProjection autônoma após reboot | Impossível | API pública exige consentimento de sessão |
| Captura de DRM/`FLAG_SECURE` | Impossível | proteção deliberada do Android |
| `adb shell input` em UI comum | Provável | ADB ready; OEM/keyguard podem restringir |
| Texto Unicode confiável por `input text` | Experimental | IME Samsung, escape e composição variam |
| Injeção global direta pelo UID Termux | Impossível | `INJECT_EVENTS` é permissão privilegiada |
| Accessibility companion | Provável | usuário habilita explicitamente; uso e escopo limitados |
| Bypass de PIN/biometria/keyguard | Impossível | fora das APIs suportadas e do escopo |
| PowerShare manual pelo Quick Panel | Provável | documentado para o S10+; estado do aparelho e rota visual não verificados |
| API pública de controle PowerShare | Impossível | não há API pública Samsung/Android documentada |
| PowerShare por tile/automação de UI | Experimental | One UI/layout/estado; opt-in e pós-verificação |
| Estado/potência exata de PowerShare | Experimental | `dumpsys`/sysfs/notificação seriam heurísticas |
| Métricas Android agregadas via ADB | Provável | parsing de `dumpsys` é dependente de versão |
| Temperaturas Samsung detalhadas | Experimental | sysfs/vendor pode estar oculto ou negar acesso |
| Métricas de todos os apps sem ADB | Impossível | sandbox, `hidepid` e restrição por UID |
| Network inspector read-only | Provável | `/proc/net` é restringido; combinar APIs/ADB |
| mDNS | Provável | multicast/AP/Doze podem impedir; IP manual obrigatório |
| IP LAN estável | Provável | depende de DHCP; reserva é externa ao projeto |
| Bind direto em 22/80/443 | Impossível | requer capability/root; usar 8022/8080/8443 |
| Alterar rota/firewall/hotspot | Impossível | exige privilégio de sistema/root |
| Desligar Wi-Fi | Impossível para app comum e proibido | nunca implementar, inclusive via ADB |
| Reverse SSH remoto | Provável | Internet, host externo e processo vivos |
| cloudflared no Termux | Provável | pacote ARM64 existe; validar conta/binário no S10 |
| WAN direta atrás de CGNAT | Impossível sem infraestrutura | usar túnel outbound opcional |
| Uptime 24/7 garantido | Impossível | Android/One UI pode matar Termux |
| Dados privados de outros apps | Impossível | sandbox UID/SELinux; `run-as` só para app debuggable |
| Escrever em `/system`/`vendor` | Impossível e proibido | root/build modificada; risco de inutilização |
| Reboot/reset/revogação ADB/stop SSH | Proibido | não deve existir em API, teste ou recuperação automática |

## 10. Segurança e ameaça

Mesmo o console allowlisted e as roots de arquivos confinadas ampliam a
superfície de ataque do UID Termux; eles não equivalem a um shell completo. ADB
equivale a controle amplo do usuário Android. Portanto:

- nenhum endpoint sensível é anônimo;
- LAN não é tratada como confiável por si só;
- tokens têm entropia alta, expiram/rotacionam e não aparecem em URL/log;
- bootstrap é one-time e recuperável somente pela CLI local/SSH, que pode
  invalidar sessões e emitir novo token; perda também do SSH exige intervenção
  manual, não bypass remoto;
- adapters validam argumentos após autorização, não apenas no frontend;
- túnel não remove autenticação interna;
- segredos têm permissões de arquivo restritas;
- operações alteradoras registram ator, origem, alvo, intenção, resultado e
  evidência de pós-condição;
- firmware sem patches correntes deve ser isolado de exposição WAN direta.

## 11. Degradação obrigatória

| Falha | Resultado exigido |
|---|---|
| ADB ausente/offline/unauthorized | UI, auth, health, root dedicada, console seguro e LAN continuam; tela/controle degradam |
| Screen provider falha | fallback para snapshot; depois `unavailable`, sem derrubar API |
| Internet cai | LAN continua integral; acesso remoto mostra indisponível |
| Túnel cai | listener LAN não muda; retry limitado só do sidecar |
| Termux:API ausente | coletores dependentes degradam; core e ADB continuam |
| Shared storage revogada | `project-share` permanece; root compartilhada some com motivo |
| Provider trava | deadline encerra somente subprocesso criado pelo projeto |
| Alta carga/temperatura | reduzir/pausar stream e polling; preservar auth/health |
| PowerShare incerto | `unknown`/`unverified`; nenhuma repetição automática |
| Só o processo `s10-control` morre | `sshd` não é tocado e runit tenta recuperar o servidor |
| Android mata Termux/processos-filho | servidor e SSH podem cair juntos; recuperação é apenas best-effort após o app poder voltar |

## 12. Critérios globais de aceite

Uma release só pode ser chamada estável quando:

- LAN funciona a partir de outro equipamento com WAN indisponível;
- ADB e túnel podem estar ausentes desde o boot do servidor sem crash;
- tentativa não autenticada e papel insuficiente são recusados;
- `sshd` não pode ser parado pelo ServiceManager;
- nenhuma rota contém reboot, reset, revogação ADB, Wi-Fi off ou componente
  Android arbitrário;
- paths maliciosos e symlink escape são recusados;
- o consumo e soak test previstos no milestone foram medidos no S10 real;
- o resultado e as limitações reais estão registrados em `STATUS.md`.

## 13. Fatos ainda a medir no aparelho

- versão Android, API, One UI, CSC, build e patch de segurança;
- origem/versão/assinatura de Termux e add-ons;
- arquitetura reportada, memória, armazenamento e política de bateria;
- estado atual de SSH, ADB USB, Wireless Debugging, chaves e endpoint;
- primeiro desbloqueio e contingência DeX/HDMI;
- tipo exato da falha do display e funcionamento de `screencap`/encoder;
- acesso real a shared storage, `/proc`, thermal e Termux:API;
- comportamento de background/phantom processes no firmware instalado;
- existência de uma evidência confiável do estado PowerShare.

Nenhum desses probes foi executado nesta tarefa.

## 14. Fontes primárias

- [Android Debug Bridge e Wireless Debugging](https://developer.android.com/tools/adb)
- [MediaProjection](https://developer.android.com/media/grow/media-projection)
- [AccessibilityService](https://developer.android.com/reference/android/accessibilityservice/AccessibilityService)
- [`FLAG_SECURE`](https://developer.android.com/reference/android/view/WindowManager.LayoutParams#FLAG_SECURE)
- [Android Application Sandbox](https://source.android.com/docs/security/app-sandbox)
- [Restrições de Wi-Fi](https://developer.android.com/reference/android/net/wifi/WifiManager#setWifiEnabled(boolean))
- [Termux: ambiente e Android 12](https://github.com/termux/termux-app)
- [Termux filesystem](https://github.com/termux/termux-packages/wiki/Termux-file-system-layout)
- [Termux:Boot](https://github.com/termux/termux-boot)
- [termux-services](https://github.com/termux/termux-services/blob/master/README.md)
- [Pacote Termux `android-tools`](https://github.com/termux/termux-packages/blob/master/packages/android-tools/build.sh)
- [Pacote Termux `ttyd`](https://github.com/termux/termux-packages/blob/master/packages/ttyd/build.sh)
- [scrcpy e protocolo do servidor](https://github.com/Genymobile/scrcpy/blob/master/doc/develop.md)
- [Samsung SM-G975F / Android 12](https://doc.samsungmobile.com/SM-G975F/003165190302/eng.html)
- [Samsung Wireless PowerShare](https://www.samsung.com/us/support/answer/ANS10002057/)
- [Samsung DeX no S10](https://www.samsung.com/sg/support/mobile-devices/how-to-connect-samsung-dex-with-samsung-galaxy-s10-series/)
