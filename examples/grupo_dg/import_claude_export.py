#!/usr/bin/env python3
"""Importa o export de conversas do claude.ai para a base de conhecimento local.

Como obter o export: claude.ai, Definições, Conta, Exportar dados. Chega por
email um ficheiro .zip com "conversations.json" (e outros ficheiros que este
script ignora). Aponte --export para esse .zip, ou para a pasta já
extraída, ou diretamente para o conversations.json.

Nada é enviado para lado nenhum. A leitura e a indexação acontecem só no seu
computador, para a mesma base (~/.openjarvis/knowledge.db) que
index_projects.py e o agente deep_research já usam.

O formato exato de conversations.json pode variar entre versões do export.
Este importador foi escrito de forma defensiva contra a estrutura pública
conhecida (lista de conversas, cada uma com "name"/"uuid"/"created_at" e uma
lista de mensagens), mas não foi validado contra um export real nesta
sessão porque esta sessão não tem acesso à sua conta. Corra primeiro com
--dry-run: se o resumo não bater certo com o que espera, o próprio aviso de
"formato não reconhecido" mostra a estrutura encontrada, o que ajuda a
ajustar as funções _extrair_* abaixo.

Uso:
    python examples/grupo_dg/import_claude_export.py --export ~/Downloads/data-export.zip --dry-run
    python examples/grupo_dg/import_claude_export.py --export ~/Downloads/data-export.zip
    python examples/grupo_dg/import_claude_export.py --export ~/Downloads/data-export.zip --filtro "Grupo DG" --filtro "DGPW"
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from taxonomy import CATEGORIA_CONVERSAS

DOC_TYPE_CONVERSAS = CATEGORIA_CONVERSAS
SOURCE_PREFIX = "claude_conversas"


def _load_conversations_json(export_path: Path) -> Any:
    """Devolve o conteúdo já em JSON de conversations.json, a partir de
    --export, seja um .zip, uma pasta extraída, ou o ficheiro direto."""
    if export_path.is_file() and export_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(export_path) as zf:
            candidatos = [n for n in zf.namelist() if n.endswith("conversations.json")]
            if not candidatos:
                raise FileNotFoundError(
                    "conversations.json não encontrado dentro do .zip. "
                    f"Ficheiros presentes: {zf.namelist()[:20]}"
                )
            with zf.open(candidatos[0]) as fh:
                return json.load(fh)

    if export_path.is_dir():
        candidato = export_path / "conversations.json"
        if not candidato.exists():
            achados = [p.name for p in export_path.glob("*.json")]
            raise FileNotFoundError(
                f"conversations.json não encontrado em {export_path}. "
                f"Ficheiros .json presentes: {achados}"
            )
        export_path = candidato

    with export_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _extrair_texto_mensagem(msg: dict) -> str:
    """Tenta várias formas conhecidas de guardar o texto de uma mensagem."""
    if isinstance(msg.get("text"), str) and msg["text"].strip():
        return msg["text"]

    conteudo = msg.get("content")
    if isinstance(conteudo, str):
        return conteudo
    if isinstance(conteudo, list):
        partes = []
        for bloco in conteudo:
            if isinstance(bloco, dict) and isinstance(bloco.get("text"), str):
                partes.append(bloco["text"])
            elif isinstance(bloco, str):
                partes.append(bloco)
        if partes:
            return "\n".join(partes)

    return ""


def _extrair_mensagens(conversa: dict) -> list[dict]:
    for chave in ("chat_messages", "messages"):
        valor = conversa.get(chave)
        if isinstance(valor, list):
            return valor
    return []


def _extrair_remetente(msg: dict) -> str:
    valor = msg.get("sender") or msg.get("role") or "?"
    return {"human": "Humano", "user": "Humano", "assistant": "Claude"}.get(
        str(valor).lower(), str(valor)
    )


def _extrair_data(conversa: dict) -> datetime:
    bruto = conversa.get("created_at") or conversa.get("updated_at")
    if isinstance(bruto, str):
        try:
            return datetime.fromisoformat(bruto.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(tz=timezone.utc)


def _passa_filtro(titulo: str, texto: str, filtros: list[str]) -> bool:
    if not filtros:
        return True
    alvo = f"{titulo}\n{texto}".lower()
    return any(termo.lower() in alvo for termo in filtros)


def iter_documents(dados: Any, *, filtros: list[str], stats: dict[str, int]):
    from openjarvis.connectors._stubs import Document

    if isinstance(dados, dict) and "conversations" in dados:
        dados = dados["conversations"]

    if not isinstance(dados, list):
        stats["formato_nao_reconhecido"] = 1
        stats["_diagnostico"] = (
            f"tipo de topo: {type(dados).__name__}, "
            f"chaves: {list(dados.keys())[:20] if isinstance(dados, dict) else 'n/a'}"
        )
        return

    for conversa in dados:
        if not isinstance(conversa, dict):
            continue
        stats["conversas_vistas"] = stats.get("conversas_vistas", 0) + 1

        titulo = str(conversa.get("name") or conversa.get("title") or "Conversa sem título")
        uid = str(conversa.get("uuid") or conversa.get("id") or titulo)
        mensagens = _extrair_mensagens(conversa)

        linhas = []
        for msg in mensagens:
            if not isinstance(msg, dict):
                continue
            texto = _extrair_texto_mensagem(msg)
            if not texto.strip():
                continue
            linhas.append(f"{_extrair_remetente(msg)}: {texto}")

        corpo = "\n\n".join(linhas)
        if not corpo.strip():
            stats["conversas_vazias"] = stats.get("conversas_vazias", 0) + 1
            continue

        if not _passa_filtro(titulo, corpo, filtros):
            stats["excluidas_pelo_filtro"] = stats.get("excluidas_pelo_filtro", 0) + 1
            continue

        stats["conversas_importadas"] = stats.get("conversas_importadas", 0) + 1

        yield Document(
            doc_id=f"{SOURCE_PREFIX}:{uid}",
            source=SOURCE_PREFIX,
            doc_type=DOC_TYPE_CONVERSAS,
            content=corpo,
            title=titulo,
            timestamp=_extrair_data(conversa),
            metadata={
                "categoria": DOC_TYPE_CONVERSAS,
                "n_mensagens": len(linhas),
                "origem": "claude_export",
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--export", required=True, help="Caminho do .zip exportado, da pasta extraída, ou de conversations.json.")
    parser.add_argument("--db", default=None, help="Caminho da base de conhecimento (default: ~/.openjarvis/knowledge.db).")
    parser.add_argument(
        "--filtro",
        action="append",
        default=[],
        help="Só importa conversas cujo título ou conteúdo contenha este termo. Pode repetir a opção. Sem filtro, importa tudo.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria importado, sem escrever na base.")
    parser.add_argument("--replace", action="store_true", help="Apaga as conversas já importadas antes de reimportar (evita duplicados ao reimportar o mesmo export).")
    args = parser.parse_args()

    export_path = Path(args.export).expanduser()
    if not export_path.exists():
        print(f"Caminho não encontrado: {export_path}", file=sys.stderr)
        sys.exit(1)

    try:
        dados = _load_conversations_json(export_path)
    except (FileNotFoundError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"Não foi possível ler o export: {exc}", file=sys.stderr)
        sys.exit(1)

    stats: dict[str, Any] = {}
    docs = list(iter_documents(dados, filtros=args.filtro, stats=stats))

    if stats.get("formato_nao_reconhecido"):
        print(
            "Formato de conversations.json não reconhecido por este importador.\n"
            f"Diagnóstico: {stats.get('_diagnostico')}\n"
            "Ajustar _extrair_mensagens / _extrair_texto_mensagem a este formato.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Conversas encontradas: {stats.get('conversas_vistas', 0)}")
    print(f"Vazias (ignoradas): {stats.get('conversas_vazias', 0)}")
    if args.filtro:
        print(f"Excluídas pelo filtro {args.filtro}: {stats.get('excluidas_pelo_filtro', 0)}")
    print(f"A importar: {len(docs)}")

    if args.dry_run:
        print("\nModo de simulação, nada escrito na base. Primeiras 10 conversas:")
        for doc in docs[:10]:
            print(f"  - {doc.title}  ({doc.timestamp.date()}, {doc.metadata['n_mensagens']} mensagens)")
        return

    if not docs:
        print("Nada para importar.")
        return

    from openjarvis.connectors.pipeline import IngestionPipeline
    from openjarvis.connectors.store import KnowledgeStore
    from openjarvis.core.config import DEFAULT_CONFIG_DIR

    db_path = Path(args.db).expanduser() if args.db else DEFAULT_CONFIG_DIR / "knowledge.db"
    store = KnowledgeStore(str(db_path))
    try:
        if args.replace:
            removidos = store.delete_by_source(SOURCE_PREFIX)
            if removidos:
                print(f"{removidos} excertos de conversas anteriores substituídos.")
        pipeline = IngestionPipeline(store)
        n_chunks = pipeline.ingest(iter(docs))
    finally:
        store.close()

    print(f"\n{len(docs)} conversas -> {n_chunks} excertos indexados em {db_path}")
    print('Consultar com: jarvis ask --agent deep_research "o que discutimos sobre..."')


if __name__ == "__main__":
    main()
