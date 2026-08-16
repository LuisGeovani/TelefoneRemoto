# Runbook seguro — ADB, screenshot PNG e controle no S10

Este roteiro valida o Milestone 2 no **Samsung Galaxy S10+ SM-G975F** real. Ele
não concede autorização ao backend para preparar ou reparar ADB. Pareamento,
`adb connect` e edição da configuração são passos manuais do proprietário.

## 1. Pare imediatamente se

- SSH não estiver acessível a partir de um segundo equipamento;
- não houver uma rota visual segura por DeX/HDMI para confirmações Android;
- o telefone pedir primeiro desbloqueio e ele não puder ser realizado;
- o modelo não for exatamente `SM-G975F`;
- a fingerprint observada não puder ser conferida ou tiver mudado sem uma
  atualização de firmware conhecida;
- qualquer passo sugerir desligar/reconfigurar Wi-Fi, parar SSH, revogar ADB,
  reiniciar o telefone ou limpar chaves.

Não improvise recuperação pelo painel quebrado.

## 2. Proibições deste runbook

Não execute, nem “para testar”:

```text
adb kill-server
adb reboot
adb root
adb unroot
adb tcpip ...
adb shell reboot ...
adb shell svc wifi ...
adb shell settings put ...
```

Também não use a opção Android **Revogar autorizações de depuração USB**, não
apague `~/.android`, não remova chaves e não reinicie `adbd`. Estados
`unauthorized`/`offline` são testados com fakes ou alvo inválido, nunca causando
a falha real.

## 3. Pré-condições e inventário read-only

Primeiro confirme uma sessão SSH funcional de outro equipamento e mantenha-a
aberta. No Termux do S10, execute:

```sh
uname -m
getprop ro.product.model
getprop ro.build.version.release
getprop ro.build.version.sdk
getprop ro.build.version.security_patch
command -v adb
adb version
adb devices -l
```

Embora esses comandos não escrevam propriedades Android, iniciar o cliente
`adb` pode iniciar o servidor ADB local e o mDNS pode tentar reconectar
automaticamente endpoints já pareados. Por isso este inventário é opt-in,
manual e só ocorre depois de confirmar SSH/DeX; não é um probe sem efeito
colateral no lifecycle do cliente ADB.

Esperado antes de continuar:

- `uname -m` indica `aarch64`/ARM64;
- o modelo é `SM-G975F`;
- `adb` vem do pacote `android-tools` do repositório Termux compatível com a
  origem do app.

Se `adb` não existir, a instalação é manual e deve ser previamente revisada:

```sh
apt-get -s install android-tools
pkg install android-tools
```

Leia o plano simulado antes de confirmar a instalação. Não execute `pkg
upgrade` como parte deste roteiro.

## 4. Autorização e pareamento são manuais

Se o telefone já estiver pareado e conectado ao ADB local, pule para a seção 5.
Caso contrário, abra manualmente **Opções do desenvolvedor > Depuração sem fio**
por DeX/HDMI. Não habilite opções às cegas.

Escolha **Parear dispositivo com código de pareamento**. Há duas portas
diferentes: a porta temporária de pareamento e a porta do serviço ADB mostrada
na tela principal de Depuração sem fio. Copie cada uma sem adivinhar.

No Termux, substitua os exemplos pelos endpoints exibidos pelo próprio Android:

```sh
ADB_PAIR_ENDPOINT='192.168.1.50:37123'
adb pair "$ADB_PAIR_ENDPOINT"
```

Digite o código somente quando `adb pair` solicitar; não o coloque na linha de
comando nem em arquivo. Depois use a porta do serviço, não a porta de pairing:

```sh
ADB_TARGET='192.168.1.50:39201'
adb connect "$ADB_TARGET"
adb -s "$ADB_TARGET" get-state
```

Use o endereço mostrado pelo Android. `127.0.0.1` pode funcionar em alguns
firmwares, mas self-ADB não é fluxo oficial e permanece experimental. ADB USB
em um computador autorizado é somente recuperação/comparação de testes; não é
provider do backend.

O projeto nunca executa `adb pair`, `adb connect` ou `adb disconnect`. Se a
porta mudar, o proprietário faz a nova conexão manualmente. O provider poderá
redescobrir o target já conectado somente se ele for inequívoco e passar nas
verificações de modelo/fingerprint; atualizar `target_serial` continua sendo o
caminho operacional recomendado.

## 5. Fixar modelo e fingerprint

Ainda na mesma sessão, com `ADB_TARGET` definido:

```sh
ADB_MODEL="$(adb -s "$ADB_TARGET" shell getprop ro.product.model | tr -d '\r')"
ADB_FINGERPRINT="$(adb -s "$ADB_TARGET" shell getprop ro.build.fingerprint | tr -d '\r')"
printf 'model=%s\nfingerprint=%s\n' "$ADB_MODEL" "$ADB_FINGERPRINT"
test "$ADB_MODEL" = 'SM-G975F'
test -n "$ADB_FINGERPRINT"
```

Qualquer falha nos dois últimos comandos encerra a validação. Registre a
fingerprint somente em configuração local privada; não a aceite automaticamente
de discovery. Depois de firmware update, divergência deve bloquear captura e
controle até nova conferência manual.

O arquivo atual é resolvido sem hardcode do prefixo Termux:

```sh
CONFIG_DIR="${S10_CONTROL_DATA_DIR:-${XDG_STATE_HOME:-$HOME/.local/share}/s10-control}"
CONFIG_FILE="$CONFIG_DIR/config.json"
printf '%s\n' "$CONFIG_FILE"
```

Faça backup local com permissão privada e edite apenas o objeto `adb`:

```sh
cp -p -- "$CONFIG_FILE" "$CONFIG_FILE.before-adb"
chmod 600 "$CONFIG_FILE.before-adb"
${EDITOR:-nano} "$CONFIG_FILE"
python -m json.tool "$CONFIG_FILE" >/dev/null
chmod 600 "$CONFIG_FILE"
```

Valores esperados no objeto existente, preservando as demais chaves:

```json
{
  "adb": {
    "enabled": true,
    "target_serial": "192.168.1.50:39201",
    "expected_fingerprint": "FINGERPRINT_EXATA_OBSERVADA",
    "status_cache_seconds": 3.0,
    "command_timeout_seconds": 4.0,
    "screenshot_timeout_seconds": 8.0
  }
}
```

Substitua os dois valores ilustrativos. O modelo permitido é fixo no servidor e
não é recebido da API.

Se o serviço já estiver instalado, confirme SSH novamente e reinicie somente o
serviço do projeto, por decisão manual:

```sh
sv status sshd
sv restart s10-control
sv status sshd
```

Teste também uma nova conexão SSH a partir do segundo equipamento. Nunca use
`sv down sshd` nem `sv restart sshd`.

## 6. Probe manual de screenshot PNG

Capture apenas uma tela comum, sem banco, gerenciador de senha, códigos 2FA ou
outro conteúdo sensível. O arquivo temporário fica fora do repositório:

```sh
S10_PROBE_DIR="$(mktemp -d "${TMPDIR:-$PREFIX/tmp}/s10-screen.XXXXXX")"
chmod 700 "$S10_PROBE_DIR"
FRAME_PATH="$S10_PROBE_DIR/frame.png"
PART_PATH="$S10_PROBE_DIR/frame.png.part"
if command -v timeout >/dev/null 2>&1 &&
   (ulimit -f 49152; timeout 12s adb -s "$ADB_TARGET" exec-out screencap -p > "$PART_PATH") &&
   chmod 600 "$PART_PATH" &&
   test "$(wc -c < "$PART_PATH")" -le 25165824; then
  mv -- "$PART_PATH" "$FRAME_PATH"
  sha256sum "$FRAME_PATH"
else
  rm -f -- "$PART_PATH" "$FRAME_PATH"
  echo "CAPTURE_FAILED: pare aqui; não valide nem use um PNG parcial" >&2
  false
fi
```

Valide assinatura, IHDR e dimensões sem biblioteca externa:

```sh
python - "$FRAME_PATH" <<'PY'
import struct
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = path.read_bytes()
if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
    raise SystemExit("INVALID_PNG")
width, height = struct.unpack(">II", data[16:24])
if not (1 <= width <= 16384 and 1 <= height <= 16384):
    raise SystemExit("INVALID_DIMENSIONS")
print(f"PNG_OK width={width} height={height} bytes={len(data)}")
PY
```

O rename para `frame.png` só ocorre quando `timeout`, captura e limite exato de
24 MiB passam. Esse pós-teste é autoritativo porque a unidade de `ulimit -f`
pode variar entre shells. Sucesso confirma somente assinatura/IHDR, dimensões
plausíveis e o limite do arquivo; a decodificação completa ainda é feita pelo
navegador. Frame preto pode ser efeito de `FLAG_SECURE`, DRM, keyguard, display
lógico apagado ou da falha física; não tente contornar essas proteções.

Depois de registrar somente metadados/checksum necessários, remova apenas o
arquivo temporário criado acima, na mesma sessão:

```sh
case "$S10_PROBE_DIR" in
  "${TMPDIR:-$PREFIX/tmp}"/s10-screen.*)
    rm -f -- "$FRAME_PATH"
    rmdir -- "$S10_PROBE_DIR"
    ;;
  *)
    printf 'Recusa de cleanup fora do diretório temporário esperado: %s\n' "$S10_PROBE_DIR"
    ;;
esac
```

Screenshots, gravações e dumps nunca entram no Git.

## 7. Validar a UI e o controle

Use uma página ou app de laboratório inofensivo. Não teste em lockscreen,
Settings críticos, banco, autenticação, instalação de APK ou diálogo protegido.

1. Abra a página **Tela remota** na UI autenticada; ela cria o WebSocket
   `/api/v1/screen/ws` internamente.
2. Confirme que cada item anuncia `image/png`, dimensões, rotação, display,
   geração/target ADB, `stream_id`, `frame_id` e timestamp antes dos bytes.
3. Confirme o ACK exato do frame; a autorização fica ligada à sessão e ao
   stream que exibiram a imagem, não a outro navegador.
4. Teste tap, swipe e long press com coordenadas normalizadas no frame atual.
5. Teste HOME/BACK e texto ASCII simples somente pelo endpoint tipado.
6. Gire a UI ou espere o frame expirar e confirme `STALE_FRAME`/
   `ROTATION_MISMATCH`, sem executar input.
7. Desconecte o último navegador e confirme que a captura periódica para.

O adapter pode formar somente estes vetores, sempre com `-s <target>` e sem
shell do host:

```text
adb -s <target> shell input tap <x> <y>
adb -s <target> shell input swipe <x1> <y1> <x2> <y2> <duration-ms>
adb -s <target> shell input keyevent <keycode-allowlisted>
adb -s <target> shell input text <ascii-restrito>
```

Não digite esses comandos manualmente: o backend precisa aplicar autenticação,
rate limit, frame atual, rotação e allowlist antes de executá-los. Exit code zero
resulta inicialmente em `unverified`; confira a mudança no frame seguinte.

## 8. Falhas esperadas e rollback

- `unauthorized`, `offline`, timeout, endpoint ausente e ADB sem binário devem
  degradar apenas ADB/tela/controle; health, auth, métricas, UI, LAN e SSH
  continuam.
- Teste `unauthorized`/`offline` com fake adapter no host. No S10, um serial
  propositalmente inválido testa indisponibilidade sem revogar nada.
- Em `MODEL_MISMATCH` ou `FINGERPRINT_MISMATCH`, não atualize config
  automaticamente; pare e investigue.
- Não há H.264, scrcpy, `screenrecord`, MediaProjection, ffmpeg, áudio ou
  companion nesta etapa.

Para rollback, restaure somente a configuração do projeto e reinicie somente
`s10-control`, mantendo SSH e Wi-Fi intactos:

```sh
cp -p -- "$CONFIG_FILE.before-adb" "$CONFIG_FILE"
chmod 600 "$CONFIG_FILE"
sv restart s10-control
sv status sshd
```

O resultado, firmware, fingerprint sanitizada conforme decisão do proprietário,
limites observados e falhas devem ser registrados em `STATUS.md` antes de mudar
qualquer classe para `guaranteed` ou runtime para `ready`.
