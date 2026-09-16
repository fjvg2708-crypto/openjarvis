#!/usr/bin/env python3
"""Indexa as pastas de projeto descritas em manifest.toml no OpenJarvis.

Não move, renomeia, apaga nem edita nenhum documento original. Apenas lê o
conteúdo de texto de cada ficheiro elegível e guarda excertos (chunks) numa
base local, ``~/.openjarvis/knowledge.db`` por omissão, junto com metadados
de taxonomia (empresa, projeto, cliente, país, área de negócio, estado,
categoria documental).

Essa base é a mesma que os agentes ``deep_research`` do OpenJarvis já sabem
consultar através das ferramentas ``knowledge_search`` e ``knowledge_sql``.
Depois de indexar, basta usar ``jarvis ask --agent deep_research "..."``.

Uso:
    python examples/grupo_dg/index_projects.py --manifest manifest.toml
    python examples/grupo_dg/index_projects.py --manifest manifest.toml --dry-run
    python examples/grupo_dg/index_projects.py --manifest manifest.toml --db ~/.openjarvis/grupo-dg.db

Requisitos:
    OpenJarvis instalado neste ambiente (uv sync --extra dev, extensão Rust
    compilada com "make build"). Ver INSTALL.md para o procedimento completo.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from taxonomy import CATEGORIA_POR_CLASSIFICAR, classify_categoria

# Diretórios a ignorar durante a travessia de cada pasta de projeto.
_SKIP_DIRS = {
    ".git",
    ".svn",
    ".hg",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".obsidian",
    ".trash",
    "$RECYCLE.BIN",
    "System Volume Information",
}

# Extensões binárias que o OpenJarvis ainda não sabe converter para texto
# nesta versão. Não são indexadas, mas ficam listadas no resumo final para
# o utilizador saber o que falta cobrir (converter para PDF ou .txt, ou
# aguardar suporte nativo). O ficheiro original nunca é tocado.
_BINARY_SKIP_EXTS = {
    ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
    ".dwg", ".dxf", ".zip", ".rar", ".7z",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
}


def _slugify(texto: str) -> str:
    sem_acentos = unicodedata.normalize("NFKD", texto)
    sem_acentos = "".join(c for c in sem_acentos if not unicodedata.combining(c))
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", sem_acentos).strip("-").lower()
    return slug or "projeto"


@dataclass
class Projeto:
    path: Path
    empresa: str
    projeto: str
    cliente: str
    pais: str
    area_negocio: str
    estado: str
    categoria_default: str

    @property
    def source(self) -> str:
        return f"grupo_dg:{_slugify(self.empresa)}:{_slugify(self.projeto)}"


def load_manifest(manifest_path: Path) -> list[Projeto]:
    with manifest_path.open("rb") as fh:
        data = tomllib.load(fh)

    projetos: list[Projeto] = []
    for entry in data.get("projeto", []):
        raw_path = str(entry.get("path", "")).strip()
        nome = str(entry.get("projeto", "")).strip()
        if not raw_path or raw_path.startswith("[") or not nome or nome.startswith("["):
            # Entrada de exemplo por preencher — ignorar em silêncio.
            continue
        path = Path(raw_path).expanduser()
        if not path.is_dir():
            print(f"[aviso] pasta não encontrada, a ignorar: {path}", file=sys.stderr)
            continue
        projetos.append(
            Projeto(
                path=path,
                empresa=str(entry.get("empresa", "")).strip(),
                projeto=nome,
                cliente=str(entry.get("cliente", "")).strip(),
                pais=str(entry.get("pais", "")).strip(),
                area_negocio=str(entry.get("area_negocio", "")).strip(),
                estado=str(entry.get("estado", "")).strip(),
                categoria_default=str(entry.get("categoria_default", "")).strip(),
            )
        )
    return projetos


def _iter_files(root: Path):
    import os

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for filename in filenames:
            if filename.startswith("."):
                continue
            yield Path(dirpath) / filename


def build_documents(projeto: Projeto, stats: dict[str, int]):
    """Gera um Document por ficheiro elegível da pasta do projeto."""
    from datetime import datetime, timezone

    from openjarvis.connectors._stubs import Document
    from openjarvis.security.file_policy import is_sensitive_file
    from openjarvis.tools.storage.ingest import read_document

    for fpath in sorted(_iter_files(projeto.path)):
        rel = fpath.relative_to(projeto.path)

        if is_sensitive_file(fpath):
            stats["sensiveis_ignorados"] = stats.get("sensiveis_ignorados", 0) + 1
            continue

        if fpath.suffix.lower() in _BINARY_SKIP_EXTS:
            stats["nao_suportados"] = stats.get("nao_suportados", 0) + 1
            continue

        try:
            text, _meta = read_document(fpath)
        except ImportError:
            # PDF sem pdfplumber instalado.
            stats["sem_pdfplumber"] = stats.get("sem_pdfplumber", 0) + 1
            continue
        except (OSError, UnicodeDecodeError, ValueError):
            stats["erros_leitura"] = stats.get("erros_leitura", 0) + 1
            continue

        if not text.strip():
            stats["vazios"] = stats.get("vazios", 0) + 1
            continue

        categoria = classify_categoria(str(rel), default=projeto.categoria_default)
        mtime = datetime.fromtimestamp(fpath.stat().st_mtime, tz=timezone.utc)

        stats["indexados"] = stats.get("indexados", 0) + 1
        stats[f"categoria::{categoria}"] = stats.get(f"categoria::{categoria}", 0) + 1

        yield Document(
            doc_id=f"{projeto.source}:{rel}",
            source=projeto.source,
            doc_type=categoria,
            content=text,
            title=fpath.name,
            timestamp=mtime,
            url=f"file://{fpath}",
            metadata={
                "empresa": projeto.empresa,
                "projeto": projeto.projeto,
                "cliente": projeto.cliente,
                "pais": projeto.pais,
                "area_negocio": projeto.area_negocio,
                "estado": projeto.estado,
                "categoria": categoria,
                "ficheiro": str(rel),
                "pasta_projeto": str(projeto.path),
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        default="manifest.toml",
        help="Caminho para o manifest.toml preenchido (default: manifest.toml).",
    )
    parser.add_argument(
        "--db",
        default=None,
        help=(
            "Caminho da base de conhecimento. Default: "
            "~/.openjarvis/knowledge.db (a mesma que os agentes deep_research "
            "usam automaticamente)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra o que seria indexado, sem escrever na base.",
    )
    parser.add_argument(
        "--no-replace",
        action="store_true",
        help=(
            "Não apagar o conteúdo anterior de cada projeto antes de "
            "reindexar. Por omissão cada projeto é substituído por inteiro "
            "para que documentos removidos ou renomeados não fiquem "
            "duplicados nem obsoletos na base."
        ),
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser()
    if not manifest_path.exists():
        print(
            f"Manifesto não encontrado: {manifest_path}\n"
            "Copie manifest.example.toml para manifest.toml e preencha os "
            "seus projetos reais antes de indexar.",
            file=sys.stderr,
        )
        sys.exit(1)

    projetos = load_manifest(manifest_path)
    if not projetos:
        print(
            "Nenhum projeto válido encontrado no manifesto "
            "(as entradas de exemplo entre parênteses retos são ignoradas).",
            file=sys.stderr,
        )
        sys.exit(1)

    total_stats: dict[str, Any] = {}

    if args.dry_run:
        print("Modo de simulação. Nada será escrito na base de conhecimento.\n")
        for projeto in projetos:
            stats: dict[str, int] = {}
            docs = list(build_documents(projeto, stats))
            print(f"Projeto: {projeto.projeto}  ({projeto.path})")
            print(f"  empresa={projeto.empresa!r} cliente={projeto.cliente!r} "
                  f"pais={projeto.pais!r} estado={projeto.estado!r}")
            print(f"  ficheiros a indexar: {len(docs)}")
            for chave, valor in sorted(stats.items()):
                if chave.startswith("categoria::"):
                    print(f"    {chave.split('::', 1)[1]}: {valor}")
            print()
        return

    from openjarvis.connectors.pipeline import IngestionPipeline
    from openjarvis.connectors.store import KnowledgeStore
    from openjarvis.core.config import DEFAULT_CONFIG_DIR

    db_path = Path(args.db).expanduser() if args.db else DEFAULT_CONFIG_DIR / "knowledge.db"
    store = KnowledgeStore(str(db_path))
    try:
        # Apagar primeiro o conteúdo antigo de todos os projetos a substituir,
        # e só depois construir o IngestionPipeline: este carrega o conjunto de
        # doc_id já vistos a partir da base no momento em que é criado, por
        # isso tem de ver a base já sem os registos que vão ser substituídos,
        # senão volta a tratá-los como duplicados e ignora-os silenciosamente.
        if not args.no_replace:
            for projeto in projetos:
                removidos = store.delete_by_source(projeto.source)
                if removidos:
                    print(f"[{projeto.projeto}] {removidos} excertos antigos substituídos.")

        pipeline = IngestionPipeline(store)
        for projeto in projetos:
            stats = {"indexados": 0, "sensiveis_ignorados": 0, "nao_suportados": 0,
                      "sem_pdfplumber": 0, "erros_leitura": 0, "vazios": 0}
            docs = list(build_documents(projeto, stats))
            n_chunks = pipeline.ingest(iter(docs))

            print(f"[{projeto.projeto}] {stats['indexados']} ficheiros -> {n_chunks} excertos indexados")
            if stats["nao_suportados"]:
                print(f"    {stats['nao_suportados']} ficheiro(s) em formato ainda não suportado "
                      f"(docx/xlsx/imagens/etc) — não indexados, originais intactos.")
            if stats["sensiveis_ignorados"]:
                print(f"    {stats['sensiveis_ignorados']} ficheiro(s) sensível(eis) ignorado(s) por política de segurança.")
            if stats["sem_pdfplumber"]:
                print(f"    {stats['sem_pdfplumber']} PDF(s) não lido(s) — instalar com: uv sync --extra memory-pdf")
            if stats["erros_leitura"]:
                print(f"    {stats['erros_leitura']} ficheiro(s) com erro de leitura, ignorado(s).")

            for chave, valor in stats.items():
                total_stats[chave] = total_stats.get(chave, 0) + valor
    finally:
        store.close()

    print(f"\nBase de conhecimento: {db_path}")
    print(f"Total indexado: {total_stats.get('indexados', 0)} ficheiros em {len(projetos)} projeto(s).")
    print('Consultar com: jarvis ask --agent deep_research "..."')
    print("Ou abrir o dashboard local com: python examples/grupo_dg/dashboard.py")


if __name__ == "__main__":
    main()
