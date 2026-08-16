# Deploy Termux

O template `runit/s10-control/run` supervisiona somente o processo do projeto.
`scripts/install-termux.sh` cria o serviço e `scripts/update-termux.sh` apenas
recompila/atualiza arquivos; ambos nunca alteram `sshd`, Wi-Fi, ADB ou o ciclo
de vida do telefone. Nenhum script reinicia o aparelho.
