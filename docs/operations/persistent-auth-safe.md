# Runbook seguro — autenticação persistente M2.2

Este roteiro cobre somente setup, login, logout e recuperação da única conta
administrativa. Ele não altera ADB, Wi-Fi, SSH ou Android. Nunca copie senha,
bootstrap, cookie, banco ou saída sensível para Git, chat, issue ou log.

O estado vive, por padrão, em `~/.local/share/s10-control/`. Atualização e
rollback preservam esse diretório. Não apague, substitua ou sincronize para o
repositório `config.json`, `s10-control.sqlite3` ou `bootstrap.token`.

## 1. Pré-check e atualização

Mantenha duas sessões SSH e a rota visual de recuperação. No S10, depois de
transferir o código pelo fluxo seguro já adotado pelo proprietário:

```sh
cd "$HOME/s10-control" || exit 1
sv status sshd
sv status s10-control
apps/server/.venv/bin/python -m s10_control version
scripts/update-termux.sh
apps/server/.venv/bin/python scripts/smoke-python-runtime.py
apps/server/.venv/bin/python -m s10_control version
apps/server/.venv/bin/s10-control auth status
```

`update-termux.sh` não reinicia serviço. A versão esperada depois do build é
`0.2.2`. Se smoke/import falhar, pare; não altere o estado local.

Reinicie manualmente somente o projeto quando estiver pronto:

```sh
old_pid=$(sv status s10-control | sed -n 's/.*(pid \([0-9][0-9]*\)).*/\1/p')
timeout 10s sv restart s10-control
sv status s10-control
curl --fail --max-time 2 http://127.0.0.1:8080/api/v1/health/ready
sv status sshd
printf 'old s10-control pid: %s\n' "$old_pid"
```

Não aplique `sv restart` a `sshd`. Se o projeto não voltar ready, preserve as
sessões SSH e faça diagnóstico antes de qualquer outra ação.

## 2. Primeiro setup após upgrade

Uma instalação anterior não possui `AdminAccount`; sessões bootstrap legadas
falham fechadas. O servidor continua ready e o estado do dashboard leva a
`/setup`.

No terminal privado do S10:

```sh
cd "$HOME/s10-control" || exit 1
apps/server/.venv/bin/s10-control auth status
apps/server/.venv/bin/s10-control bootstrap-token
```

Não cole a saída aqui. No navegador LAN, abra `/setup`, informe o token, escolha
um username e uma senha exclusiva de 12–256 caracteres, confirme a senha e
envie. O resultado deve abrir o Dashboard. Em seguida:

```sh
apps/server/.venv/bin/s10-control auth status
```

A saída pode mostrar apenas `configured: true` e o username. Ela nunca deve
mostrar hash, senha, sessão ou token. Uma segunda tentativa de `/setup` deve ser
recusada.

## 3. Uso normal e persistência

O uso cotidiano é somente `/login` com username/senha. Valide, nessa ordem:

1. fechar e reabrir a aba/navegador mantém a sessão;
2. refresh mantém Dashboard e Tela Remota;
3. Tela Remota abre WebSocket sem token em URL;
4. restart manual somente de `s10-control` mantém a sessão;
5. Sair retorna a `/login` e a sessão anterior deixa de acessar API/WS;
6. senha errada mostra erro genérico e limpa o campo.

Não teste reboot nesta campanha. O formato persistente foi desenhado para
sobreviver, mas reboot exige autorização e rota de recuperação próprias.

## 4. Recuperação sem invalidar antecipadamente

Se a senha foi esquecida, gere bootstrap no terminal privado:

```sh
cd "$HOME/s10-control" || exit 1
apps/server/.venv/bin/s10-control bootstrap-token
```

Abra `/recovery`, informe o token e a nova senha. O sucesso incrementa
`auth_version`, invalida todas as sessões antigas e cria uma sessão nova.

## 5. Reset local explícito

Use apenas quando quiser invalidar todas as sessões **antes** da recuperação:

```sh
cd "$HOME/s10-control" || exit 1
apps/server/.venv/bin/s10-control auth reset --yes
```

O comando imprime a credencial de recuperação no terminal. Use-a em
`/recovery`; não a registre. Sem `--yes`, a CLI recusa a operação.

## 6. Permissões e pós-check

Inspecione apenas metadados, nunca conteúdo:

```sh
stat -c '%a %n' "$HOME/.local/share/s10-control" \
  "$HOME/.local/share/s10-control/s10-control.sqlite3"
test ! -e "$HOME/.local/share/s10-control/bootstrap.token" || \
  stat -c '%a %n' "$HOME/.local/share/s10-control/bootstrap.token"
sv status sshd
sv status s10-control
```

Esperado: diretório `700`, arquivos sensíveis `600`, SSH e projeto ativos. O
bootstrap some após setup/recovery bem-sucedido. Não execute comandos ADB,
restart de SSH, mudança de Wi-Fi ou reboot durante esta validação.
