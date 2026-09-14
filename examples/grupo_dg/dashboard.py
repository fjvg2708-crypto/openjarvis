#!/usr/bin/env python3
"""Dashboard local, só leitura, sobre a base de conhecimento do Grupo DG.

Lê diretamente ~/.openjarvis/knowledge.db (a base que index_projects.py
preenche) e serve uma página HTML num único endereço local. Não usa
nenhuma biblioteca externa, não faz nenhum pedido de rede a serviços
externos e não altera a base de dados.

Por omissão fica acessível apenas em 127.0.0.1, ou seja, só a partir deste
computador.

Uso:
    python examples/grupo_dg/dashboard.py
    python examples/grupo_dg/dashboard.py --db ~/.openjarvis/knowledge.db --port 8787
"""

from __future__ import annotations

import argparse
import html
import json
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

_PAGE_TITLE = "Grupo DG — Painel de projetos"

_STYLE = """
body { font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif;
       margin: 0; padding: 24px; background: #f4f5f7; color: #1a1a1a; }
h1 { margin-bottom: 4px; }
.subtitulo { color: #555; margin-bottom: 24px; }
.grelha { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
          gap: 16px; }
.cartao { background: #fff; border-radius: 8px; padding: 16px 20px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.cartao h2 { font-size: 15px; text-transform: uppercase; letter-spacing: 0.04em;
             color: #666; margin: 0 0 12px 0; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
td, th { text-align: left; padding: 4px 6px; border-bottom: 1px solid #eee;
         vertical-align: top; }
.tag { display: inline-block; padding: 1px 8px; border-radius: 10px;
       font-size: 11px; background: #eef1f6; color: #333; }
.tag-atraso { background: #fdeaea; color: #a12b2b; }
.tag-concluido { background: #e8f5e9; color: #2e7d32; }
.vazio { color: #888; font-style: italic; }
footer { margin-top: 24px; color: #888; font-size: 12px; }
"""

_ESTADOS_ATIVOS_EXCLUIDOS = {"concluído", "concluido", "cancelado"}


def _connect(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _meta(row: sqlite3.Row) -> dict:
    try:
        return json.loads(row["metadata"]) if row["metadata"] else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _tag_estado(estado: str) -> str:
    e = (estado or "").strip().lower()
    if e in _ESTADOS_ATIVOS_EXCLUIDOS:
        return f'<span class="tag tag-concluido">{html.escape(estado)}</span>'
    if "atraso" in e or "litígio" in e or "litigio" in e:
        return f'<span class="tag tag-atraso">{html.escape(estado)}</span>'
    return f'<span class="tag">{html.escape(estado or "-")}</span>'


def _fmt_ts(value) -> str:
    try:
        ts = float(value)
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return "-"


def _projetos_ativos(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            json_extract(metadata, '$.projeto') AS projeto,
            json_extract(metadata, '$.empresa') AS empresa,
            json_extract(metadata, '$.estado') AS estado,
            json_extract(metadata, '$.cliente') AS cliente,
            json_extract(metadata, '$.pais') AS pais,
            COUNT(*) AS n_excertos,
            MAX(created_at) AS ultima_indexacao
        FROM knowledge_chunks
        WHERE source LIKE 'grupo_dg:%' AND deleted_at IS NULL
        GROUP BY projeto, empresa
        ORDER BY projeto
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _por_categoria(conn: sqlite3.Connection, categoria: str, limite: int = 30) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            title,
            json_extract(metadata, '$.projeto') AS projeto,
            json_extract(metadata, '$.empresa') AS empresa,
            json_extract(metadata, '$.ficheiro') AS ficheiro,
            url,
            created_at
        FROM knowledge_chunks
        WHERE source LIKE 'grupo_dg:%' AND doc_type = ? AND deleted_at IS NULL
        GROUP BY doc_id
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (categoria, limite),
    ).fetchall()
    return [dict(r) for r in rows]


def _ultimas_alteracoes(conn: sqlite3.Connection, limite: int = 20) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            title,
            doc_type,
            json_extract(metadata, '$.projeto') AS projeto,
            created_at
        FROM knowledge_chunks
        WHERE source LIKE 'grupo_dg:%' AND deleted_at IS NULL
        GROUP BY doc_id
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limite,),
    ).fetchall()
    return [dict(r) for r in rows]


def _tabela(linhas: list[dict], colunas: list[tuple[str, str]]) -> str:
    if not linhas:
        return '<p class="vazio">Sem registos.</p>'
    cabecalho = "".join(f"<th>{html.escape(rotulo)}</th>" for _, rotulo in colunas)
    corpo = []
    for linha in linhas:
        celulas = []
        for chave, _ in colunas:
            valor = linha.get(chave)
            if chave == "estado":
                celulas.append(f"<td>{_tag_estado(valor)}</td>")
            elif chave == "created_at":
                celulas.append(f"<td>{_fmt_ts(valor)}</td>")
            elif chave == "url" and valor:
                celulas.append(f'<td><a href="{html.escape(str(valor))}">abrir</a></td>')
            else:
                celulas.append(f"<td>{html.escape(str(valor) if valor is not None else '-')}</td>")
        corpo.append(f"<tr>{''.join(celulas)}</tr>")
    return f"<table><thead><tr>{cabecalho}</tr></thead><tbody>{''.join(corpo)}</tbody></table>"


def render_page(db_path: Path) -> str:
    if not db_path.exists():
        return (
            f"<html><body style='font-family:sans-serif;padding:40px'>"
            f"<h1>{html.escape(_PAGE_TITLE)}</h1>"
            f"<p>Base de conhecimento não encontrada em "
            f"<code>{html.escape(str(db_path))}</code>.</p>"
            f"<p>Corra primeiro: <code>python examples/grupo_dg/index_projects.py "
            f"--manifest manifest.toml</code></p></body></html>"
        )

    conn = _connect(db_path)
    try:
        projetos = _projetos_ativos(conn)
        ativos = [p for p in projetos if (p.get("estado") or "").strip().lower()
                  not in _ESTADOS_ATIVOS_EXCLUIDOS]
        pendencias = _por_categoria(conn, "Pendências")
        prazos = _por_categoria(conn, "Prazos")
        decisoes = _por_categoria(conn, "Decisões")
        propostas = _por_categoria(conn, "Propostas")
        recentes = _ultimas_alteracoes(conn)
    finally:
        conn.close()

    cols_projeto = [
        ("projeto", "Projeto"), ("empresa", "Empresa"), ("cliente", "Cliente"),
        ("pais", "País"), ("estado", "Estado"), ("n_excertos", "Excertos indexados"),
    ]
    cols_doc = [("title", "Documento"), ("projeto", "Projeto"), ("empresa", "Empresa"), ("url", "")]
    cols_recente = [("title", "Documento"), ("doc_type", "Categoria"), ("projeto", "Projeto"), ("created_at", "Indexado em")]

    return f"""<!doctype html>
<html lang="pt">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(_PAGE_TITLE)}</title>
<style>{_STYLE}</style>
</head>
<body>
<h1>{html.escape(_PAGE_TITLE)}</h1>
<p class="subtitulo">Leitura local, sem ligação a serviços externos. Base: {html.escape(str(db_path))}</p>
<div class="grelha">
  <div class="cartao">
    <h2>Projetos ativos ({len(ativos)} de {len(projetos)})</h2>
    {_tabela(ativos, cols_projeto)}
  </div>
  <div class="cartao">
    <h2>Todos os projetos e estado</h2>
    {_tabela(projetos, cols_projeto)}
  </div>
  <div class="cartao">
    <h2>Pendências</h2>
    {_tabela(pendencias, cols_doc)}
  </div>
  <div class="cartao">
    <h2>Prazos</h2>
    {_tabela(prazos, cols_doc)}
  </div>
  <div class="cartao">
    <h2>Decisões tomadas</h2>
    {_tabela(decisoes, cols_doc)}
  </div>
  <div class="cartao">
    <h2>Propostas</h2>
    {_tabela(propostas, cols_doc)}
  </div>
  <div class="cartao">
    <h2>Últimas alterações indexadas</h2>
    {_tabela(recentes, cols_recente)}
  </div>
  <div class="cartao">
    <h2>Próximas ações</h2>
    <p>Pendências e prazos acima são as próximas ações candidatas. Para uma
    resposta com raciocínio sobre o conteúdo, use
    <code>jarvis ask --agent deep_research "quais são as minhas próximas ações"</code>.</p>
  </div>
</div>
<footer>Gerado localmente a partir de {html.escape(str(db_path))}. Nenhum dado sai deste computador ao ver esta página.</footer>
</body>
</html>"""


def make_handler(db_path: Path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — nome exigido por BaseHTTPRequestHandler
            if self.path not in ("/", "/index.html"):
                self.send_response(404)
                self.end_headers()
                return
            body = render_page(db_path).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args) -> None:  # silencia o log por defeito
            pass

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=str(Path.home() / ".openjarvis" / "knowledge.db"),
        help="Caminho da base de conhecimento (default: ~/.openjarvis/knowledge.db).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Interface de escuta (default: 127.0.0.1, apenas local).")
    parser.add_argument("--port", type=int, default=8787, help="Porta de escuta (default: 8787).")
    args = parser.parse_args()

    db_path = Path(args.db).expanduser()
    server = HTTPServer((args.host, args.port), make_handler(db_path))
    print(f"Painel disponível em http://{args.host}:{args.port}  (ctrl+c para parar)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
