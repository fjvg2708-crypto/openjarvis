"""Esquema de taxonomia para a indexação documental do Grupo DG.

Este ficheiro não contém nenhum documento real. Define apenas o vocabulário
usado para classificar documentos que o utilizador aponta a partir do
``manifest.toml`` (ver ``manifest.example.toml``).

Editar livremente. Nenhuma destas listas é usada para validar ou rejeitar
dados, servem apenas de referência e de base à classificação automática por
palavra-chave em ``classify_categoria``.
"""

from __future__ import annotations

import unicodedata

# ---------------------------------------------------------------------------
# Dimensões da taxonomia
# ---------------------------------------------------------------------------

# Pré-preenchido a partir das entidades já referidas na configuração do
# utilizador (skill "contencioso-dgpw"). Ajustar à estrutura societária real.
EMPRESAS = [
    "DGPW S.A.",
    "DGPW Instalações Técnicas, Lda.",
]

AREAS_NEGOCIO = [
    "Construção",
    "Energia",
    "Imobiliário",
    "Defesa",
    "Desenvolvimento de Projetos",
]

PAISES_EXEMPLO = [
    "Portugal",
    "Angola",
    "Moçambique",
    "Espanha",
    "França",
]

ESTADOS = [
    "Por iniciar",
    "Em curso",
    "Em atraso",
    "Suspenso",
    "Em negociação",
    "Litígio",
    "Concluído",
    "Cancelado",
]

# As dez categorias documentais pedidas, por esta ordem exata.
CATEGORIAS_DOCUMENTAIS = [
    "Documentação Técnica",
    "Documentação Comercial",
    "Contratos",
    "Propostas",
    "Orçamentos",
    "Medições",
    "Correspondência",
    "Pendências",
    "Decisões",
    "Prazos",
]

CATEGORIA_POR_CLASSIFICAR = "Por classificar"

# ---------------------------------------------------------------------------
# Classificação automática por palavra-chave
# ---------------------------------------------------------------------------
#
# Cada entrada mapeia uma categoria documental a um conjunto de termos que,
# quando presentes no caminho ou no nome do ficheiro, indicam essa categoria.
# A comparação ignora maiúsculas e acentuação. Editar estas listas para
# afinar a classificação à terminologia real usada nas pastas do utilizador.

_KEYWORDS: dict[str, list[str]] = {
    "Documentação Técnica": [
        "memoria descritiva",
        "especificacao",
        "caderno de encargos tecnico",
        "desenho",
        "planta",
        "projeto de execucao",
        "ficha tecnica",
        "manual de",
    ],
    "Documentação Comercial": [
        "apresentacao comercial",
        "catalogo",
        "brochura",
        "dossier comercial",
    ],
    "Contratos": [
        "contrato",
        "minuta",
        "aditamento",
        "adenda",
        "acordo",
        "escritura",
    ],
    "Propostas": [
        "proposta",
        "submissao",
        "candidatura ao concurso",
        "peca concursal",
    ],
    "Orçamentos": [
        "orcamento",
        "mapa de quantidades",
        "mapa de trabalhos",
        "bdc",
        "preco unitario",
    ],
    "Medições": [
        "medicao",
        "auto de medicao",
        "auto de trabalhos",
    ],
    "Correspondência": [
        "carta",
        "email",
        "e-mail",
        "oficio",
        "notificacao",
        "comunicacao",
    ],
    "Pendências": [
        "pendencia",
        "por resolver",
        "accao pendente",
        "acao pendente",
    ],
    "Decisões": [
        "decisao",
        "acta",
        "ata de reuniao",
        "deliberacao",
    ],
    "Prazos": [
        "prazo",
        "cronograma",
        "calendario",
        "planeamento",
        "plano de trabalhos",
    ],
}


def _normalizar(texto: str) -> str:
    """Minúsculas e sem acentos, para comparação tolerante a variações."""
    sem_acentos = unicodedata.normalize("NFKD", texto)
    sem_acentos = "".join(c for c in sem_acentos if not unicodedata.combining(c))
    return sem_acentos.lower()


def classify_categoria(caminho_relativo: str, default: str = "") -> str:
    """Devolve a categoria documental sugerida para *caminho_relativo*.

    Compara o caminho (pasta + nome do ficheiro) normalizado contra as
    palavras-chave de ``_KEYWORDS``. Devolve *default* (ou
    ``CATEGORIA_POR_CLASSIFICAR`` se *default* for vazio) quando nenhuma
    palavra-chave corresponde. Nunca lança exceção.
    """
    alvo = _normalizar(caminho_relativo)
    for categoria, termos in _KEYWORDS.items():
        for termo in termos:
            if _normalizar(termo) in alvo:
                return categoria
    return default or CATEGORIA_POR_CLASSIFICAR


__all__ = [
    "EMPRESAS",
    "AREAS_NEGOCIO",
    "PAISES_EXEMPLO",
    "ESTADOS",
    "CATEGORIAS_DOCUMENTAIS",
    "CATEGORIA_POR_CLASSIFICAR",
    "classify_categoria",
]
