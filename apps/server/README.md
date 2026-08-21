# Backend

Monólito Python/FastAPI para Termux. O pacote `s10_control` fornece configuração
JSON validada, SQLite privado, autenticação, métricas e adapters opcionais para
ADB, screenshot PNG e controle Android tipado. Os assets de `web_dist/` são
servidos no mesmo processo; falha de ADB não afeta health, auth ou LAN.

O runtime fixa FastAPI 0.118.3/Starlette 0.48.0 com Pydantic 1.10.26,
Uvicorn 0.51.0, HTTP h11 e WebSocket wsproto 1.3.2. Essa combinação importou e
executou no S10 real com Termux/Python 3.14.6. Starlette 0.48.0 ainda está em
ranges afetados por advisories; a VEX estreita e as mitigações estão no ADR
0004 e em `STATUS.md`.

Comandos locais: `s10-control serve`, `s10-control bootstrap-token` e
`s10-control auth reset --yes`. Não existe CLI/API de shell ADB, Wi-Fi, SSH,
reboot ou lifecycle do telefone.
