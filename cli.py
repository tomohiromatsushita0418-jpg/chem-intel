"""コマンドラインからレポート生成（テスト・バッチ・自動化用）。

例:
    python cli.py "アクリロニトリル"
    python cli.py 107-13-1 --hs 292610 --pdf out.pdf
"""
from __future__ import annotations

import argparse
import sys

from chem_intel import pdf_export, report, storage
from chem_intel.config import load_settings


def main() -> int:
    ap = argparse.ArgumentParser(description="化学品インテリジェンスレポート生成")
    ap.add_argument("query", help="化学品名 / CAS / HSコード")
    ap.add_argument("--hs", help="HSコードを明示指定", default=None)
    ap.add_argument("--pdf", help="PDF出力先パス", default=None)
    ap.add_argument("--md", help="Markdown出力先パス", default=None)
    ap.add_argument("--no-save", action="store_true", help="履歴に保存しない")
    args = ap.parse_args()

    settings = load_settings()
    if not settings.has_llm:
        print("ERROR: ANTHROPIC_API_KEY が未設定です。", file=sys.stderr)
        return 1

    def prog(msg, ratio):
        print(f"[{ratio*100:5.1f}%] {msg}", file=sys.stderr)

    result = report.generate(settings, args.query, hs_code=args.hs, progress=prog)
    ident = result["identity"]

    if not args.no_save:
        rid = storage.save_report(
            settings,
            query=args.query,
            query_type=ident.query_type,
            display_name=ident.display_name,
            cas=ident.cas,
            hs_code=result.get("hs_code"),
            formula=ident.molecular_formula,
            markdown=result["markdown"],
            citations=result["citations"],
        )
        print(f"履歴に保存しました (id={rid})", file=sys.stderr)

    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(result["markdown"])
        print(f"Markdown: {args.md}", file=sys.stderr)
    if args.pdf:
        with open(args.pdf, "wb") as f:
            f.write(pdf_export.to_pdf(result["markdown"], ident.display_name))
        print(f"PDF: {args.pdf}", file=sys.stderr)
    if not args.md and not args.pdf:
        print(result["markdown"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
