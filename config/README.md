# Configuração versionável

Somente exemplos e schemas públicos pertencem aqui. Configuração do aparelho,
tokens, chaves, endpoints privados e qualquer `*.local.json` ficam fora do Git.

## ADB no Milestone 2

A configuração real fica no diretório privado resolvido por
`S10_CONTROL_DATA_DIR`/`XDG_STATE_HOME`, não neste diretório versionado.

```json
{
  "adb": {
    "enabled": true,
    "target_serial": "ENDPOINT_OU_SERIAL_LOCAL",
    "expected_fingerprint": "FINGERPRINT_CONFIRMADA_MANUALMENTE",
    "status_cache_seconds": 3.0,
    "command_timeout_seconds": 4.0,
    "screenshot_timeout_seconds": 8.0
  },
  "screen": {
    "fps": 1.0,
    "frame_max_age_seconds": 5.0,
    "max_clients": 2
  }
}
```

- `adb.enabled` permanece `false` por padrão; altere para `true` somente depois
  das pré-condições e da identidade serem conferidas pelo runbook.
- `adb.target_serial` é a preferência explícita e recomendada. Pode ser serial
  USB ou endpoint Wireless Debugging já conectado manualmente. O backend não
  executa `adb connect`; se a porta mudar, ele apenas pode redescobrir um device
  que já esteja conectado e que passe a validação completa de identidade.
- Sem `target_serial`, discovery não escreve propriedades Android, mas a chamada
  ao cliente pode iniciar o servidor ADB local e o mDNS pode reconectar peers já
  pareados. O adapter prefere um único device que declare o modelo esperado; se
  existir apenas um device pronto, pode consultar modelo/fingerprint. Zero ou múltiplos
  candidatos elegíveis falham fechados. O resultado nunca é persistido.
- `adb.expected_fingerprint` é obrigatório para screenshot e controle. O valor é
  obtido e conferido manualmente pelo proprietário; ausência ou divergência
  falha fechada. O backend nunca faz TOFU/auto-enrollment.
- O modelo aceito é fixo no código como `SM-G975F`; cliente/config remota não o
  substitui.
- `screen.fps` fica entre 0,2 e 2,0 e representa sequência de PNGs, não H.264.
  `frame_max_age_seconds` limita por quanto tempo um frame confirmado pode
  autorizar controle. `max_clients` limita entre 1 e 8 viewers simultâneos para
  proteger memória; o padrão conservador no telefone é 2.

Fingerprint, endpoint e serial não são tratados como senha criptográfica, mas
são dados específicos do aparelho e permanecem fora do Git. Pairing code,
tokens, chaves ADB, cookies e bootstrap token são segredos e jamais entram em
configuração versionável, log ou exemplo preenchido.

Pareamento/autorização são manuais. Consulte o
[runbook seguro](../docs/operations/adb-screen-control-safe.md); nenhuma
configuração habilita `kill-server`, `reboot`, `tcpip`, revogação ou shell
arbitrário.
