"""Converte os documentos Markdown de entrega em PDF (A4).

Uso:
    python -m scripts.gerar_pdf                 # gera todos
    python -m scripts.gerar_pdf RELATORIO_TECNICO.md

Dependências (não fazem parte do runtime): `markdown`, `xhtml2pdf`.
    pip install markdown xhtml2pdf
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import markdown
from pypdf import PdfReader, PdfWriter
from xhtml2pdf import pisa

ROOT = Path(__file__).resolve().parent.parent
PADRAO = ["RELATORIO_TECNICO.md", "ARQUITETURA.md", "PITCH.md", "ROTEIRO_VIDEO.md"]

# Metadados do documento (campo "Autor" do PDF) — não altera Producer/Creator,
# que continuam refletindo honestamente a ferramenta usada para gerar o arquivo.
AUTOR = "Felippe de Barros Ribeiro"
RM = "369425"

# Emojis / símbolos que o motor de PDF não renderiza -> texto
_EMOJI = {
    "✅": "[x]", "✓": "[x]", "✗": "[ ]", "⬜": "[ ]", "🔥": "(quente)", "🌤️": "(morno)",
    "❄️": "(frio)", "🤖": "", "🧑": "", "💬": "", "📊": "", "📇": "", "📅": "", "🔁": "",
    "🔍": "", "👁️": "", "📨": "", "📋": "", "🏠": "", "🏙️": "", "😊": "", "😕": "", "🙂": "",
    "→": "->", "►": ">", "└": "|_", "├": "|-", "│": "|", "─": "-", "▼": "v", "•": "-",
}

_CSS = """
@page { size: A4; margin: 1.8cm 1.6cm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 10pt; line-height: 1.45; color: #1a1a1a; }
h1 { font-size: 19pt; color: #111; border-bottom: 2px solid #e5484d; padding-bottom: 4px; }
h2 { font-size: 14pt; color: #111; margin-top: 20px; border-bottom: 1px solid #ccc; padding-bottom: 2px; }
h3 { font-size: 11.5pt; color: #333; margin-top: 14px; }
p, li { font-size: 10pt; }
code { font-family: Courier, monospace; font-size: 8.5pt; background: #f2f2f2; }
pre { font-family: Courier, monospace; font-size: 8pt; background: #f5f5f5; border: 1px solid #ddd;
      padding: 6px; -pdf-keep-in-frame-mode: shrink; white-space: pre-wrap; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; }
th { background: #f0f0f0; border: 1px solid #bbb; padding: 4px 6px; font-size: 8.5pt; text-align: left; }
td { border: 1px solid #ccc; padding: 4px 6px; font-size: 8.5pt; vertical-align: top; }
hr { border: 0; border-top: 1px solid #ccc; margin: 14px 0; }
a { color: #1a56db; text-decoration: none; }
blockquote { border-left: 3px solid #e5484d; margin: 8px 0; padding: 2px 10px; color: #444; background: #fafafa; }
"""


def _preprocess(md: str) -> str:
    # diagramas mermaid viram blocos de texto (o motor não desenha mermaid)
    md = md.replace("```mermaid", "```text")
    for k, v in _EMOJI.items():
        md = md.replace(k, v)
    # remove emojis restantes (faixas Unicode altas)
    md = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", md)
    return md


def _titulo(md_raw: str, fallback: str) -> str:
    for linha in md_raw.splitlines():
        if linha.startswith("# "):
            return linha[2:].strip()
    return fallback


def _aplicar_metadados(pdf_path: Path, titulo: str) -> None:
    """Preenche Autor/Título/Assunto. Producer/Creator seguem refletindo a
    ferramenta real (xhtml2pdf) — não fabricamos a proveniência do arquivo."""
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    writer.append(reader)
    writer.add_metadata(
        {
            "/Author": AUTOR,
            "/Title": titulo,
            "/Subject": f"Tech Challenge Fase 5 (8IADT) — RM {RM}",
            "/Keywords": f"FIAP, Tech Challenge, Fase 5, RM {RM}, {AUTOR}",
        }
    )
    with pdf_path.open("wb") as fh:
        writer.write(fh)


def converter(md_path: Path) -> Path:
    raw = _preprocess(md_path.read_text(encoding="utf-8"))
    titulo = _titulo(raw, md_path.stem)
    html_body = markdown.markdown(
        raw, extensions=["tables", "fenced_code", "sane_lists", "toc"]
    )
    html = f"<html><head><meta charset='utf-8'><style>{_CSS}</style></head><body>{html_body}</body></html>"
    out = md_path.with_suffix(".pdf")
    with out.open("wb") as fh:
        result = pisa.CreatePDF(html, dest=fh, encoding="utf-8")
    if result.err:
        raise RuntimeError(f"falha ao gerar {out.name}")
    _aplicar_metadados(out, titulo)
    print(f"  {md_path.name}  ->  {out.name}  ({out.stat().st_size // 1024} KB)  autor: {AUTOR}")
    return out


def main() -> None:
    alvos = sys.argv[1:] or PADRAO
    print("Gerando PDFs:")
    for nome in alvos:
        p = ROOT / nome
        if p.exists():
            converter(p)
        else:
            print(f"  (pulado, não existe: {nome})")


if __name__ == "__main__":
    main()
