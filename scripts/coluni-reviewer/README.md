# Modo local de revisão do COLUNI

Este modo fica fora de `content/` e `static/`, então não é incluído no site
público do Hugo. O servidor aceita conexões somente em `127.0.0.1`.

Inicie a partir da raiz do repositório:

```sh
python3 scripts/coluni_review_server.py
```

Abra <http://127.0.0.1:8765/>. O painel mostra a página original do PDF, a fonte
LaTeX, sua prévia formatada e o status de revisão. O botão **Salvar** escreve
somente em `data/coluni/latex-source/AAAA-NN.tex`. O status é guardado localmente
em `.local/coluni-review-status.json` e não entra na saída do site.

Depois de revisar um lote, use **Gerar banco do simulador**. Ele executa
`scripts/digitize_coluni_questions.py`, que atualiza `questions.json` usando as
fontes LaTeX como origem.
