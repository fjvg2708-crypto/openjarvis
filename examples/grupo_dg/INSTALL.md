# Instalação, arquitetura e remoção

Este documento existe para ser lido antes de correr qualquer comando, tal
como pedido. Assume que a instalação corre no seu computador ou num servidor
sob o seu controlo, nunca numa sessão cloud partilhada.

## O que vai ser instalado

- O OpenJarvis (`uv sync --extra dev`), um framework Python com uma extensão
  Rust, um CLI (`jarvis`) e, opcionalmente, um servidor local e uma app
  desktop.
- Ollama, como motor de inferência local por omissão, com um modelo pequeno
  (`qwen3.5:9b` neste preset, ajustável ao seu hardware).
- Os ficheiros deste diretório (`examples/grupo_dg/`), que não instalam nada
  por si, são scripts Python correm dentro do ambiente OpenJarvis.

## Onde fica instalado

- O código em `~/OpenJarvis` (ou onde clonar o repositório).
- A configuração e os dados em `~/.openjarvis/` (`config.toml`,
  `knowledge.db`, `memory.db`, `telemetry.db`, `traces.db`).
- Os modelos do Ollama em `~/.ollama/`.
- Nada é escrito fora destas pastas. Os documentos originais dos seus
  projetos não são copiados, apenas lidos no momento da indexação.

## Que dados são acedidos

- Apenas as pastas que descrever em `manifest.toml`, que o próprio cria a
  partir de `manifest.example.toml`. Nenhuma pasta é acedida por omissão.
- Dentro de cada pasta, todos os ficheiros de texto/markdown/PDF elegíveis,
  exceto os marcados como sensíveis pela política de segurança do OpenJarvis
  (`.env`, chaves privadas, credenciais) e exceto formatos binários ainda
  não suportados (ver README.md).
- Nada é enviado para fora do computador durante a indexação nem durante as
  perguntas ao agente `deep_research`, desde que o modelo usado seja local
  (Ollama, por omissão neste preset) e a ferramenta `web_search` continue
  desligada, como está por omissão neste preset.

## Que permissões são necessárias

- Leitura das pastas de projeto listadas no manifesto.
- Escrita apenas em `~/.openjarvis/` e na pasta do repositório.
- Nenhuma permissão de rede é necessária para o fluxo local. Só é necessária
  se decidir ligar conectores (Gmail, Google Drive, SharePoint) ou um motor
  cloud, o que é uma escolha explícita e posterior, não parte deste preset.

## Que modelos de IA são usados

- Por omissão, um modelo local via Ollama (`qwen3.5:9b`), executado no seu
  hardware. Pode trocar por outro tamanho de modelo ou por vLLM/llama.cpp,
  editando `[intelligence]` e `[engine]` em
  `configs/openjarvis/examples/grupo-dg.toml` antes de aplicar o preset.
- Nenhum modelo cloud (OpenAI, Anthropic, etc.) é usado a menos que o
  configure explicitamente.

## Que informação pode sair da máquina

- Nenhuma, no fluxo por omissão deste preset.
- Sai informação da máquina apenas se: (a) ligar um motor de modelo cloud,
  (b) ativar a ferramenta `web_search`, ou (c) ligar um conector externo
  (`jarvis connect ...`). Todas estas são ações explícitas e nenhuma está
  ativa neste preset.

## Como é feita a memória

- `~/.openjarvis/memory.db`, backend SQLite local, para o histórico de
  conversas do assistente.
- `~/.openjarvis/knowledge.db`, backend SQLite/FTS5 local (`KnowledgeStore`),
  onde ficam os excertos de documentos com os metadados de taxonomia. É esta
  base que `index_projects.py` preenche e que `dashboard.py` lê.
- Sem sincronização remota, sem backup automático para a cloud.

## Como é feita a indexação

- `index_projects.py` lê `manifest.toml`, percorre cada pasta de projeto
  listada, classifica cada ficheiro numa das 10 categorias documentais por
  palavra-chave, e guarda excertos (chunking automático) com metadados
  (empresa, projeto, cliente, país, área de negócio, estado, categoria,
  caminho do ficheiro) em `knowledge.db`.
- Reindexar é seguro e repetível: por omissão, o conteúdo anterior de cada
  projeto é substituído antes de reindexar.
- Recomenda-se correr primeiro com `--dry-run` para conferir a classificação
  antes de escrever na base.

## Como remover tudo, por completo

```bash
# 1. Parar qualquer processo do jarvis em execução
jarvis daemon stop 2>/dev/null || true

# 2. Apagar toda a configuração e dados locais do OpenJarvis
rm -rf ~/.openjarvis

# 3. Remover o ambiente Python do projeto
cd ~/OpenJarvis && rm -rf .venv

# 4. Desinstalar o Ollama e os modelos descarregados, se já não forem
#    necessários para outros usos
ollama rm qwen3.5:9b
# Linux: sudo rm -rf /usr/local/bin/ollama ~/.ollama
# macOS: remover a aplicação Ollama e ~/.ollama

# 5. Remover o próprio repositório clonado
cd .. && rm -rf OpenJarvis
```

Nada disto toca nos documentos originais das pastas de projeto: eles nunca
foram copiados nem movidos, só lidos.

## Passo a passo completo

```bash
# Clonar e preparar o ambiente
git clone https://github.com/open-jarvis/OpenJarvis.git
cd OpenJarvis
uv sync --extra dev
uv run maturin develop --manifest-path rust/crates/openjarvis-python/Cargo.toml

# Instalar e arrancar o Ollama, e obter o modelo
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull qwen3.5:9b

# Aplicar o preset Grupo DG
uv run jarvis init --preset grupo-dg --force

# Descrever os seus projetos reais
cp examples/grupo_dg/manifest.example.toml examples/grupo_dg/manifest.toml
$EDITOR examples/grupo_dg/manifest.toml

# Rever antes de indexar
uv run python examples/grupo_dg/index_projects.py --manifest examples/grupo_dg/manifest.toml --dry-run

# Indexar
uv run python examples/grupo_dg/index_projects.py --manifest examples/grupo_dg/manifest.toml

# Verificar a instalação
uv run jarvis doctor
uv run jarvis scan

# Perguntar
uv run jarvis ask --agent deep_research "qual é o estado do projeto X?"

# Painel local
uv run python examples/grupo_dg/dashboard.py
```

`jarvis scan` corre a auditoria de privacidade própria do OpenJarvis
(`PrivacyScanner`) sobre a instalação, incluindo se algum dado local está a
alimentar uma ferramenta que o exponha a um motor cloud. Vale a pena correr
depois de qualquer alteração ao preset.
