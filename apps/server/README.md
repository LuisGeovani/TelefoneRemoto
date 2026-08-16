# Backend

O M1 é um monólito Python/FastAPI. O pacote `s10_control` fornece configuração
JSON validada, SQLite privado, autenticação bootstrap/sessão e coletores locais
read-only. Ele serve os assets compilados de `web_dist/` no mesmo processo.

Comandos locais: `s10-control serve`, `s10-control bootstrap-token` e
`s10-control auth reset --yes`. Não existe comando ADB, Wi-Fi, SSH ou reboot.
