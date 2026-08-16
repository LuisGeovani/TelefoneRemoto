# Aplicações

- `server`: backend Go que roda no Termux;
- `web`: SPA estática compilada e embutida no backend;
- `companion`: APK Android opcional e experimental, sem privilégios.

No M0 estes diretórios contêm somente fronteiras. Código começa no M1 e apenas
em `server`/`web`; o companion exige milestone e ADR próprios.
