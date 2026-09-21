"""Command line entry point. The only module that touches the filesystem."""

from __future__ import annotations

import argparse
import json
import sys

from parfum import paths
from parfum.extract import normalize, run_pdftotext
from parfum.model import Book
from parfum.segment import HI, LO, build_book, reconstruct


def _squash(text: str) -> str:
    return "".join(text.split())


def _extract(_args) -> int:
    paths.ensure_dirs()
    pdfs = sorted(paths.RAW.glob("*.pdf"))
    if not pdfs:
        print(f"no PDF found in {paths.RAW}", file=sys.stderr)
        return 1

    raw_path = paths.INTERIM / "pdftotext.txt"
    run_pdftotext(pdfs[0], raw_path)
    result = normalize(raw_path.read_text(encoding="utf-8"))
    (paths.INTERIM / "raw.txt").write_text(result.text, encoding="utf-8")
    (paths.INTERIM / "pagemap.json").write_text(
        json.dumps({
            "page_offsets": result.page_offsets,
            "hyphen_joins": result.hyphen_joins,
            "page_joins": result.page_joins,
            "page_lines_removed": result.page_lines_removed,
        }, indent=2),
        encoding="utf-8",
    )
    print(f"pages: {len(result.page_offsets)}  chars: {len(result.text)}  "
          f"hyphen joins: {result.hyphen_joins}  page joins: {result.page_joins}  "
          f"page lines removed: {result.page_lines_removed}")
    return 0


def _segment(_args) -> int:
    book = build_book((paths.INTERIM / "raw.txt").read_text(encoding="utf-8"))
    (paths.INTERIM / "book.json").write_text(
        json.dumps(book.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"teile: {len(book.teile)}  "
          f"kapitel: {sum(len(t.kapitel) for t in book.teile)}  "
          f"sektionen: {len(list(book.iter_sektionen()))}  "
          f"sentences: {len(list(book.iter_saetze()))}")
    return 0


def _check(_args) -> int:
    """Verify book.json against raw.txt. Reports counts only, never book text."""
    from parfum.structure import detect

    text = (paths.INTERIM / "raw.txt").read_text(encoding="utf-8")
    book = Book.from_dict(
        json.loads((paths.INTERIM / "book.json").read_text(encoding="utf-8"))
    )

    source = _squash("".join(
        paragraph
        for teil in detect(text)
        for kapitel in teil.kapitel
        for paragraph in kapitel.paragraphs
    ))
    chapters = [k.number for t in book.teile for k in t.kapitel]
    sizes = [len(s.saetze) for s in book.iter_sektionen()]

    problems = []
    if _squash(reconstruct(book)) != source:
        problems.append("concatenation invariant FAILED — text was lost or duplicated")
    if chapters != list(range(1, len(chapters) + 1)):
        problems.append(f"chapter sequence irregular ({len(chapters)} chapters found)")
    if not sizes:
        problems.append("no Sektionen were produced")

    print(f"teile: {len(book.teile)}  kapitel: {len(chapters)}  "
          f"sektionen: {len(sizes)}  sentences: {sum(sizes)}")
    if sizes:
        print(f"sektion size: min={min(sizes)} max={max(sizes)} "
              f"mean={sum(sizes) / len(sizes):.1f}")
        print(f"outside the {LO}-{HI} band: "
              f"{sum(1 for n in sizes if not LO <= n <= HI)} "
              f"(chapter-final Sektionen are expected to be short)")

    for problem in problems:
        print(f"PROBLEM: {problem}", file=sys.stderr)
    return 1 if problems else 0


def _glossary_candidates(args) -> int:
    """Generate glossary candidates from book, filtered by frequency and sense count."""
    from parfum.candidates import count_lemmas, monosemous, recurring
    from parfum.sentences import load_nlp
    from parfum.wiktextract import load_subset

    book = Book.from_dict(
        json.loads((paths.INTERIM / "book.json").read_text(encoding="utf-8"))
    )
    senses = load_subset(paths.REFERENCE / "senses.json")

    counted = count_lemmas(book, load_nlp())
    kept = monosemous(recurring(counted, args.min_count), senses)

    rows = ["lemma\tpos\tcount\tgloss"] + [
        f"{c.lemma}\t{c.pos}\t{c.count}\t{senses[c.lemma][0].gloss}" for c in kept
    ]
    (paths.INTERIM / "candidates.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    print(f"lemmas: {len(counted)}  recurring: {len(recurring(counted, args.min_count))}  "
          f"candidates: {len(kept)}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="parfum")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("extract", help="PDF -> raw.txt + pagemap.json")
    sub.add_parser("segment", help="raw.txt -> book.json")
    sub.add_parser("check", help="verify book.json against raw.txt")
    cand = sub.add_parser("glossary-candidates",
                          help="book.json -> candidates.tsv for curation")
    cand.add_argument("--min-count", type=int, default=8)
    args = parser.parse_args(argv)
    return {
        "extract": _extract,
        "segment": _segment,
        "check": _check,
        "glossary-candidates": _glossary_candidates,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
