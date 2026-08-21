# Scripts

Os scripts de instalação/atualização devem ser idempotentes, fail-fast,
compatíveis com Termux/Bionic e seguros por padrão. Eles gerenciam somente
`s10-control`; não reiniciam Android, Wi-Fi, SSH ou ADB. Diagnósticos futuros são
sempre read-only.

Uma instalação nova cria o serviço com arquivo `down`; ela não chama
`sv-enable` nem abre `0.0.0.0:8080` antes da revisão manual. O script valida
Python 3.11+, pip dentro da venv e o requisito de Node do Vite. Atualizações não
reiniciam o serviço existente. Instalação e atualização executam
`smoke-python-runtime.py` depois do install editável e falham antes do bootstrap
ou build se versões/imports não corresponderem ao stack provado no S10.
O instalador só prepara bootstrap automaticamente quando `auth status` indica
que nenhuma conta existe; reinstalar uma instância configurada não cria token
de recuperação nem invalida sessão.
