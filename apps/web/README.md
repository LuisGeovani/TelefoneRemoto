# Frontend

SPA React/TypeScript/Vite sem CDN. `npm run build` gera `../server/web_dist/`,
servido pelo FastAPI. Além do Dashboard local, a UI possui tela remota PNG de
baixo FPS com WebSocket same-origin, ACK, reconnect/fullscreen e controles
frame-bound. Ela é mobile-first, dark e consome somente o mesmo host.

O lock usa TypeScript 6.0.2, ainda implementado em JavaScript e portanto
portável ao Node.js oficial do Termux ARM64. TypeScript 7 nativo não é usado
porque não publica binário Android aarch64.
