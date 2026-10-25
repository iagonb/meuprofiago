# Fontes LaTeX das questões do COLUNI

Cada arquivo `latex-source/AAAA-NN.tex` é a fonte editável de uma questão.
O simulador transforma esses arquivos em HTML tipografado e os associa ao
gabarito já estruturado em `static/simulados/coluni/questions.json`.

Depois de revisar ou editar uma questão, regenere a saída com:

```sh
python3 scripts/digitize_coluni_questions.py
```

Para comparar o PDF com a fonte LaTeX em um painel local, execute
`python3 scripts/coluni_review_server.py` na raiz do projeto e abra
<http://127.0.0.1:8765/>. O painel salva diretamente nas fontes acima, mantém o
status de revisão no arquivo local ignorado pelo Git e oferece o comando de
regeneração do banco ao fim do lote. Detalhes em
[`scripts/coluni-reviewer/README.md`](../../scripts/coluni-reviewer/README.md).

As figuras recortadas das provas ficam em
`static/simulados/coluni/figuras/AAAA/questao-NN/` e são chamadas pelas fontes
LaTeX com blocos `figure` marcados `COLUNI-AUTO-FIGURES`. O manifesto
`figures-manifest.json` registra a origem dos recortes; figuras de textos ou
tirinhas compartilhados são copiadas para a pasta de cada questão relacionada.
Para refazer os recortes após substituir um PDF, instale as dependências em um
ambiente isolado e execute:

```sh
python3 -m venv /tmp/coluni-venv
/tmp/coluni-venv/bin/pip install PyMuPDF Pillow
/tmp/coluni-venv/bin/python scripts/extract_coluni_figures.py
python3 scripts/digitize_coluni_questions.py
```

O script recria a pasta de figuras automaticamente. Confira os recortes novos
contra a prova original antes de publicar.

As 70 questões de Matemática que já existiam em `Matemática/questoes.tex`
foram aproveitadas. As demais foram inicialmente transcritas do texto embutido nos PDFs. Essa transcrição inicial precisa ser conferida com a prova original, principalmente onde houver fórmulas, gráficos, imagens ou textos de apoio. O simulador conserva o recorte e o PDF originais para essa conferência.
