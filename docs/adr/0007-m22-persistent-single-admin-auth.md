# ADR 0007 — autenticação persistente de uma única conta administrativa

- **Status:** aceita e implementada; validação no S10 pendente
- **Data:** 2026-08-20
- **Escopo:** M2.2, sem expansão do protocolo ADB/tela

## Contexto

Até a M2, o bootstrap de curta duração era trocado diretamente por uma sessão.
Isso servia à implantação inicial, mas tornava a recuperação local uma etapa do
uso cotidiano. A M2.2 precisa oferecer username/senha, manter a sessão por 30
dias e sobreviver a restart e atualização sem criar cadastro público, múltiplos
usuários ou gestão de sessões.

O runtime comprovado é Python 3.14.6 no Termux aarch64/Bionic. Argon2id seria a
primeira escolha geral para senha, porém as implementações Python usuais trazem
extensão nativa. Adicionar uma dependência não comprovada no S10 violaria a
política de compatibilidade e poderia quebrar o deploy já funcional.

## Decisão

### Conta e password

Usar a tabela singleton `admin_account`, com `CHECK (id = 1)`, contendo
username, esquema, salt, digest, `auth_version` e timestamps. Não há tabela
genérica de usuários. O campo de role nas sessões antigas permanece fixo em
`admin` somente para compatibilidade interna com o controle M2.

Usar `hashlib.scrypt`, já presente na biblioteca padrão e exercitado no runtime
do projeto, com `N=16384`, `r=8`, `p=1` e salt aleatório de 16 bytes. O banco
guarda somente digest e salt. A escolha evita código caseiro e dependência
nativa nova; o rate limit reduz tentativa online. Aumentar custo ou migrar para
Argon2id exige benchmark/prova de instalação no SM-G975F e novo esquema.

### Sessão

Continuar com token opaco aleatório. O navegador recebe `id.segredo`, mas o
SQLite persiste apenas digest salgado do segredo. Cada sessão carrega a versão
de autenticação vigente e expira inicialmente em 30 dias. A validação exige:

1. sessão existente, não expirada e não revogada;
2. digest do segredo correto;
3. `auth_version` igual ao singleton atual.

O cookie é `HttpOnly`, `SameSite=Strict`, `Path=/` e tem `Max-Age` e `Expires`
explícitos. `Secure=false` é o default deliberado do HTTP LAN atual; há opção de
configuração para ativá-lo somente quando HTTPS existir. Não há credencial em
Web Storage ou query string.

Sessões expiradas/revogadas são removidas oportunisticamente na criação de uma
nova sessão, mantendo crescimento limitado sem uma página de gestão.

### Setup, recuperação e revogação

O bootstrap continua em arquivo privado `0600`, mas serve apenas a dois fluxos:

- `/setup`, permitido somente quando o singleton não existe;
- `/recovery`, que troca a senha e invalida todas as sessões anteriores.

`s10-control bootstrap-token` cria/reutiliza uma credencial curta sem invalidar
uma sessão ativa. `s10-control auth reset --yes` é a ação explícita que primeiro
incrementa `auth_version` e revoga sessões. Nenhum desses tokens é logado pelo
servidor.

### Proteção HTTP e WebSocket

- setup/login/recovery exigem `Origin` igual a `Host`;
- logout e controles mutáveis exigem cookie, CSRF e Origin;
- login responde a username/senha incorretos com o mesmo erro genérico;
- o limitador em memória reserva no máximo cinco tentativas por cliente em 60
  segundos, com no máximo 256 chaves e limpeza após sucesso/restart;
- o WebSocket usa somente cookie e Origin e revalida expiração/revogação durante
  o stream e após cada ACK.

O endpoint antigo `/auth/bootstrap/exchange` deixa de existir: bootstrap não é
mais uma sessão cotidiana.

### Migração

A abertura do SQLite cria `admin_account` e adiciona `sessions.auth_version`
quando ausente. Sessões legadas recebem versão zero e falham fechadas porque não
existe conta correspondente. O servidor continua ready, cria bootstrap de
setup, e o proprietário configura a primeira conta pela UI. Configs antigas sem
bloco `auth` recebem defaults em memória; nenhum JSON local é reescrito.

## Consequências

- Fechar/reabrir navegador, reiniciar o servidor/Termux e atualizar código não
  elimina a sessão enquanto cookie, SQLite, prazo e versão forem válidos.
- Cookies pertencem à origem do navegador. Se o endereço/hostname LAN mudar
  após reboot, o servidor preserva a sessão, mas a nova origem exigirá login;
  não é seguro compartilhar cookie entre hosts distintos.
- Um reset de senha invalida imediatamente HTTP e WebSocket antigos.
- O update seguro deve preservar `~/.local/share/s10-control`; apagar esse
  diretório remove conta e sessões e continua proibido.
- HTTP LAN não protege senha/cookie contra observação na rede. Publicação WAN ou
  túnel antes de HTTPS/hardening continua proibida.
- Scrypt bloqueia brevemente a thread do request; o custo e o limitador são
  aceitáveis para uma única conta/LAN, mas precisam de medição no S10.
- A implementação permanece host-validated até setup/login/persistência/reset e
  Tela Remota serem exercitados no SM-G975F.

## Alternativas rejeitadas

- **Argon2id agora:** boa primitiva, mas a extensão nativa ainda não tem prova
  no Python 3.14/Termux aarch64 deste aparelho.
- **Senha/config em JSON:** mistura segredo com configuração e dificulta
  migração/transação.
- **Cookie autossuficiente assinado:** exigiria gerir outro segredo persistente
  e tornaria revogação/limpeza menos direta.
- **Múltiplos usuários/RBAC:** fora do escopo e amplia desnecessariamente a
  superfície administrativa.
- **Bootstrap cotidiano ou token em localStorage:** não atende o objetivo e
  aumenta exposição da credencial.
