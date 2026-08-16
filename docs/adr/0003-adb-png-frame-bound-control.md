# ADR 0003 — ADB, frames PNG e controle vinculado ao frame

- **Estado:** aceita
- **Data:** 2026-08-15
- **Escopo:** Milestone 2

## Contexto

O M1 entregou no host o painel local em Python/FastAPI e React. O proprietário
autorizou a próxima etapa como um único recorte vertical: detectar ADB, mostrar a
tela e controlar o Android. O display físico do SM-G975F não funciona, o Termux
não tem root e ADB/SSH são canais de recuperação que não podem ser reconfigurados
ou revogados pelo projeto.

Separar captura e controle em milestones distintos deixaria controle sem o
contexto visual necessário. Por outro lado, adicionar scrcpy/H.264 nesta etapa
traria protocolo, encoder, decoder, processo remoto e carga térmica antes de
validar o caminho mais simples no aparelho real.

## Decisão

O Milestone 2 combina três adapters atrás de contratos separados:

1. `AdbController`, para estado, identidade e comandos tipados;
2. `ScreenProvider`, usando exclusivamente PNG produzido por
   `adb -s <target> exec-out screencap -p`;
3. `AndroidControlService`, aceitando apenas eventos allowlisted associados ao
   frame PNG confirmado pelo cliente.

O backend pode distribuir uma sequência de PNGs por WebSocket em baixa
frequência, com fila “latest only” e ACK do frame. Isso não é vídeo e não usa
H.264. scrcpy-server, `screenrecord`, MediaProjection, ffmpeg, transcodificação
e áudio ficam fora do M2.

### Trust bootstrap e identidade

- O provider ADB é opt-in e permanece desabilitado na configuração padrão.
- O projeto nunca habilita Wireless Debugging, pareia, aceita autorização,
  executa `adb connect`/`disconnect` ou altera portas. Essas ações são manuais e
  fora da API, usando DeX/HDMI ou outra rota visual segura.
- O alvo configurado é a preferência. Discovery por `adb devices -l` e
  `adb mdns services` não altera propriedades Android, mas pode iniciar o
  servidor ADB local e seu mDNS pode reconectar peers já pareados. Por isso é
  opt-in e não é descrito como livre de efeito no lifecycle. Uma porta já
  conectada pode ser adotada
  somente quando a seleção é inequívoca e modelo+fingerprint conferem. Toda
  operação continua passando o target resolvido por `-s`; seleção ambígua falha
  fechada e nada é persistido automaticamente.
- Antes de captura ou controle, o gateway exige modelo exatamente `SM-G975F` e
  fingerprint exatamente igual ao valor cadastrado manualmente. O cache de
  identidade é curto e deve ser invalidado quando o transporte mudar.
- Mudança de fingerprint falha fechada com `FINGERPRINT_MISMATCH`; atualização
  automática do valor confiável é proibida.
- Cada identidade verificada recebe uma geração monotônica. Frames carregam
  target e geração; qualquer mudança de estado/target invalida seu uso para
  input.

### Comandos permitidos ao adapter

O processo é criado sem shell, com argumentos separados, alvo `-s` explícito,
deadline e limite de saída. A união tipada admite apenas:

- `getprop ro.product.model` e `getprop ro.build.fingerprint`;
- `exec-out screencap -p`;
- `dumpsys input`, somente para o probe read-only de rotação;
- `input tap`, `input swipe` e long press representado por swipe no mesmo ponto;
- `input keyevent` para a allowlist documentada do M2;
- `input text` com alfabeto ASCII estreito e tamanho limitado.

Não existe comando remoto genérico. O projeto nunca invoca `adb kill-server`,
`adb reboot`, `adb root`, `adb unroot`, `adb tcpip`, pareamento, revogação,
limpeza de chaves, `settings put`, `svc wifi`, gerência de `adbd`, package name
arbitrário ou intent arbitrário.

### Vínculo obrigatório ao frame

Todo tap, swipe, long press, keyevent ou texto referencia `stream_id`,
`frame_id`, `display_id`, rotação, target e geração ADB. O servidor só executa
se o frame:

- foi entregue e confirmado pelo mesmo protocolo;
- foi confirmado pela mesma sessão no stream individual daquele navegador;
- é o mais recente no registro;
- ainda está dentro do limite de idade;
- mantém display, dimensões e rotação atuais.

Rotação é medida antes e depois do PNG sob o mesmo gate ADB; divergência descarta
a captura. O input tem espera limitada e revalida sessão, frame, idade,
identidade e rotação dentro do gate imediatamente antes de iniciar o comando.
Sessões WebSocket são revalidadas a cada 500 ms durante o stream e após cada
ACK. O cliente só habilita controle depois de receber `frame_acknowledged`; um
epoch no registry rejeita ACK tardio após erro ou invalidação.

Coordenadas chegam normalizadas entre 0 e 1 e são convertidas no servidor.
Frame ausente, antigo ou divergente produz recusa, inclusive para admin. O
retorno inicial de controle é `unverified`; um exit code zero do `input` não
comprova que a UI mudou.

## Consequências

- O core, autenticação, métricas, dashboard e LAN continuam funcionando sem ADB.
- Self-ADB, parsing de rotação, captura com o painel apagado e controles Android
  permanecem `experimental/unknown` até evidência repetível no SM-G975F.
- PNG de baixa frequência terá mais latência e tráfego que vídeo comprimido, mas
  reduz dependências e oferece uma referência visual auditável.
- `FLAG_SECURE`, DRM, keyguard e diálogos protegidos podem gerar frame preto ou
  impedir controle; não haverá tentativa de bypass.
- Texto Unicode, IME Samsung e composição são experimentais; o M2 limita texto
  ao conjunto ASCII documentado.
- Porta/endereço de Wireless Debugging pode mudar. Conectar a nova porta é ação
  manual; depois disso o provider pode redescobrir o único target verificado. O
  projeto não tenta `adb tcpip`, revogar ou refazer pareamento.

## Validação

O runbook obrigatório é
[`docs/operations/adb-screen-control-safe.md`](../operations/adb-screen-control-safe.md).
Até ele passar no S10 real, nenhuma capacidade desta ADR é `guaranteed` nem
`ready` por evidência de host.
