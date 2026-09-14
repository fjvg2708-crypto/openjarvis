# Grupo DG — base de organização e consulta de projetos

Camada de indexação e consulta sobre a documentação de projetos do Grupo DG,
construída sobre o OpenJarvis. Não move, não renomeia, não apaga e não edita
nenhum documento original: lê o conteúdo, guarda excertos com metadados de
taxonomia numa base local, e responde a perguntas com citação da fonte.

## O que isto é, e o que não é

- **É** uma camada lógica por cima dos seus documentos existentes: um índice
  local pesquisável, com metadados de empresa, projeto, cliente, país, área
  de negócio, estado e categoria documental.
- **Não é** uma cópia nem uma reorganização física dos ficheiros. As pastas
  originais ficam exatamente como estão.
- **Não é** um serviço cloud. Corre inteiramente no seu computador, com um
  modelo local (Ollama por omissão). Nenhum documento sai da máquina, a
  menos que decida ligar `web_search` ou um conector externo, o que este
  preset não faz por omissão.

## Taxonomia

Definida em `taxonomy.py`, editável:

- **Dimensões**: empresa, projeto, cliente, país, área de negócio, estado.
- **Categorias documentais** (10): Documentação Técnica, Documentação
  Comercial, Contratos, Propostas, Orçamentos, Medições, Correspondência,
  Pendências, Decisões, Prazos.

A categoria de cada ficheiro é sugerida automaticamente por palavra-chave no
nome/caminho do ficheiro (`classify_categoria`). Quando nenhuma palavra-chave
corresponde, fica marcado "Por classificar" — nunca é adivinhado às cegas.

## Instalação rápida

Ver `INSTALL.md` para o procedimento completo, incluindo requisitos,
permissões, modelos usados e remoção total. Resumo:

```bash
# 1. Aplicar o preset de configuração
jarvis init --preset grupo-dg --force

# 2. Descrever os seus projetos reais (sem tocar nos ficheiros originais)
cp examples/grupo_dg/manifest.example.toml examples/grupo_dg/manifest.toml
$EDITOR examples/grupo_dg/manifest.toml

# 3. Indexar (ver primeiro em modo simulação)
python examples/grupo_dg/index_projects.py --manifest examples/grupo_dg/manifest.toml --dry-run
python examples/grupo_dg/index_projects.py --manifest examples/grupo_dg/manifest.toml

# 4. Perguntar
jarvis ask --agent deep_research "qual é o estado do projeto X?"

# 5. Painel local
python examples/grupo_dg/dashboard.py
```

## Perguntas que isto responde

Via `jarvis ask --agent deep_research "..."`, usando as ferramentas
`knowledge_search` (pesquisa semântica/lexical) e `knowledge_sql` (consultas
estruturadas sobre os metadados de cada excerto):

- Qual é o estado deste projeto?
- Quais são as pendências?
- Que decisões foram tomadas?
- Que documentos estão em falta? *(o agente só sabe o que foi indexado —
  ver limitações abaixo)*
- Quais são os próximos prazos?
- Que propostas estão pendentes?
- Que riscos comerciais ou contratuais existem?
- Que informação existe sobre determinado cliente ou fornecedor?

O painel local (`dashboard.py`) responde sem depender do modelo de
linguagem, por leitura direta da base, a: projetos ativos, estado por
projeto, pendências, prazos, decisões, propostas, últimas alterações
indexadas.

## Limitações a conhecer

- **Formatos binários** (`.docx`, `.xlsx`, `.dwg`, imagens) não são lidos
  nesta versão. Ficam listados no resumo da indexação como "não suportados".
  Contornos possíveis: exportar para PDF ou `.txt` antes de indexar, ou
  aguardar uma extensão do conector para esses formatos.
- **PDF** requer `pdfplumber` (`uv sync --extra memory-pdf`).
- A classificação por categoria é por palavra-chave, não por leitura do
  conteúdo. Rever `taxonomy.py` e afinar os termos à terminologia real usada
  nas suas pastas.
- "Documentos em falta" é respondido por inferência do agente sobre o que
  falta na documentação indexada, não por comparação com uma lista de
  documentos obrigatórios. Não substitui uma checklist contratual.

## Reindexar depois de alterações

Correr `index_projects.py` novamente. Por omissão, cada projeto é
substituído por inteiro antes de reindexar (`store.delete_by_source`), para
que ficheiros apagados ou renomeados não fiquem a aparecer como fantasmas na
base. Os ficheiros originais nunca são tocados, apenas o índice.

## Remoção completa

Ver a secção "Remover tudo" em `INSTALL.md`.
