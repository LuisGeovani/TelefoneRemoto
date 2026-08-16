# Estado atual

- **Atualizado em:** 2026-08-15 (America/Rio_Branco)
- **Branch de trabalho:** `codex/m1-local-dashboard`
- **Milestone:** M1 implementado no host; validação no SM-G975F pendente
- **Push:** autorizado pelo proprietário após a conclusão desta etapa

## Entregue no M1

- monólito Python/FastAPI em `apps/server`, com configuração JSON privada,
  SQLite, logs JSON, request IDs e handler global de erros;
- bootstrap one-time de administrador, cookie de sessão HttpOnly/SameSite=Strict,
  logout e recuperação somente local por `s10-control auth reset`;
- health público e endpoints autenticados de sistema, CPU, RAM, armazenamento,
  uptime, rede, bateria opcional e dashboard agregado;
- estados separados de servidor, LAN, Internet, SSH, ADB e Remote Access;
  Internet offline não altera `/health/ready` e ADB não é chamado;
- SPA React/TypeScript/Vite mobile-first, dark, PWA básica e assets estáticos
  servidos pelo backend depois de `npm run build`;
- template runit exclusivo de `s10-control` e scripts de instalação/atualização
  que não controlam `sshd`, Wi-Fi, ADB nem reiniciam o telefone;
- testes unitários de parsers/métricas/autenticação/API e lockfiles Python/npm.

## Decisão de runtime

O ADR 0002 substitui Go/Preact/JSON do M0 por Python/FastAPI/React/SQLite para
este milestone, por autorização explícita do proprietário. Continua um único
processo local-first. O listener solicitado é `0.0.0.0:8080`; como M1 usa HTTP,
ele é LAN-only e não deve ser exposto por túnel/WAN. TLS LAN é hardening futuro.

## Validação executada no host

- `apps/web`: `npm install`, `npm run build` e `npm run test` passaram;
- `apps/server`: `unittest discover -s tests -v` passou (7 testes), junto de
  `compileall` com Python 3.12 isolado;
- cenários cobertos: parser de `/proc`, métricas portáveis, Internet offline,
  ADB ausente, bootstrap de uso único/revogação e health/API sem Internet;
- dependências Python foram resolvidas em `requirements.lock`; Pydantic v1.10.26
  foi escolhido para evitar tornar `pydantic-core` uma dependência nativa
  obrigatória.

## Ainda não validado no S10 real

- instalação de Python 3.11+, Node.js e termux-services da mesma origem Termux;
- compatibilidade do lock Python com aarch64/Bionic, especialmente fallback puro
  de Pydantic;
- bind LAN `0.0.0.0:8080`, acesso de outro equipamento e comportamento do AP;
- leitura de `/proc`, espaço, interfaces e `termux-battery-status` no firmware;
- porta SSH local configurada (o probe assume 8022), presença de `adb` e o
  comportamento em background/runit.

Nenhuma dessas limitações reduz a classe de qualquer capacidade para
`guaranteed`: não houve comando no aparelho, alteração ADB, captura, controle,
PowerShare, túnel, terminal, arquivos, reboot, reset ou alteração de Wi-Fi/SSH.

## Riscos atuais

1. HTTP em LAN não fornece confidencialidade de transporte; não publicar a porta
   nem usá-la por túnel antes de uma decisão de TLS.
2. Android/One UI pode encerrar Termux/runit em background.
3. O lock foi testado em host Windows, não em Termux ARM64/Bionic.
4. A bateria depende de Termux:API já instalado e compatível; sua ausência é
   reportada como `unavailable`.
5. O probe de Internet é observacional e pode ficar `offline` por DNS/firewall
   externo sem afetar o servidor ou a LAN.

## Próximo passo seguro

Com o proprietário presente e SSH confirmado, executar o roteiro M1 do
`PLAN.md`: instalar dependências manualmente no Termux, rodar
`scripts/install-termux.sh`, obter o token local, testar a LAN inclusive sem
WAN e confirmar que somente `s10-control` é supervisionado. Não avançar para
tela, controle, PowerShare, terminal, túnel ou arquivos.
