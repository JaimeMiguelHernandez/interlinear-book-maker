"""Command line entry point. The only module that touches the filesystem."""

from __future__ import annotations

import argparse
import json
import os
import sys

from parfum import paths
from parfum.deepl import Client as DeepLClient
from parfum.extract import normalize, run_pdftotext
from parfum.model import Book
from parfum.segment import HI, LO, build_book, reconstruct


def _read_book() -> Book:
    return Book.from_dict(
        json.loads((paths.INTERIM / "book.json").read_text(encoding="utf-8"))
    )


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
    book = _read_book()

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


def _senses(args) -> int:
    from parfum.candidates import count_lemmas, recurring
    from parfum.sentences import load_nlp
    from parfum.wiktextract import build_subset, save_subset

    book = _read_book()
    wanted = {c.lemma for c in recurring(count_lemmas(book, load_nlp()), args.min_count)}
    with open(args.jsonl, encoding="utf-8") as handle:
        senses = build_subset(handle, wanted)
    save_subset(senses, paths.REFERENCE / "senses.json")
    print(f"wanted: {len(wanted)}  found: {len(senses)}")
    return 0


def _glossary_candidates(args) -> int:
    """Generate glossary candidates from book, filtered by frequency and sense count."""
    from parfum.candidates import count_lemmas, monosemous, recurring
    from parfum.sentences import load_nlp
    from parfum.wiktextract import load_subset

    book = _read_book()
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


def _client():
    import httpx

    auth_key = os.environ.get("DEEPL_AUTH_KEY")
    if not auth_key:
        raise SystemExit("DEEPL_AUTH_KEY is not set")
    client = httpx.Client(timeout=60.0)
    return DeepLClient(auth_key, lambda method, url, **kw: client.request(method, url, **kw))


def _load_glossary():
    from parfum.glossary import parse_tsv

    path = paths.CONFIG / "glossary.tsv"
    return parse_tsv(path.read_text(encoding="utf-8")) if path.is_file() else []


def _glossary_validate(_args) -> int:
    from parfum.wiktextract import load_subset

    entries = _load_glossary()
    senses = load_subset(paths.REFERENCE / "senses.json")
    problems = []
    for entry in entries:
        found = senses.get(entry.source, [])
        if len(found) != 1:
            problems.append(f"{entry.source}: {len(found)} senses, expected exactly 1")
        elif not entry.evidence.strip():
            problems.append(f"{entry.source}: no dictionary evidence")
    print(f"entries: {len(entries)}  problems: {len(problems)}")
    for problem in problems:
        print(f"PROBLEM: {problem}", file=sys.stderr)
    return 1 if problems else 0


def _glossary_upload(_args) -> int:
    glossary_id = _client().create_glossary("parfum", _load_glossary())
    (paths.INTERIM / "glossary_id.txt").write_text(glossary_id, encoding="utf-8")
    print(f"glossary_id: {glossary_id}")
    return 0


def _glossary_ab(args) -> int:
    from parfum.ab import compare, report
    from parfum.deepl import load_instructions

    book = _read_book()
    diffs = compare(book, _load_glossary(),
                    load_instructions(paths.CONFIG / "translation_instructions.json"),
                    _client(), scope=args.scope,
                    glossary_id=(paths.INTERIM / "glossary_id.txt").read_text().strip(),
                    cache_root=paths.TRANSLATION_CACHE / "ab")
    print(report(diffs))
    return 0


def _translate(args) -> int:
    from parfum.cache import Cache
    from parfum.deepl import MODEL_TYPE, load_instructions, preflight
    from parfum.cache import key as cache_key
    from parfum.translate import run, write_translated

    book = _read_book()
    entries = _load_glossary()
    instructions = load_instructions(paths.CONFIG / "translation_instructions.json")
    cache = Cache(paths.TRANSLATION_CACHE)
    client = _client()

    saetze = [s for s in book.iter_saetze()
              if args.scope is None or s.id.startswith(args.scope)]
    pending = [s.text for s in saetze
               if args.force or cache.get(cache_key(s.text, entries, MODEL_TYPE, instructions)) is None]
    check = preflight(pending, client.usage())
    print(f"pending sentences: {check.pending_sentences}  "
          f"pending characters: {check.pending_characters}  "
          f"remaining: {check.remaining}  fits: {check.fits}")
    if args.dry_run:
        return 0
    if not check.fits:
        return 1

    glossary_path = paths.INTERIM / "glossary_id.txt"
    result = run(book, entries, instructions, cache, client,
                 glossary_path.read_text().strip() if glossary_path.is_file() else None,
                 scope=args.scope, force=args.force)
    write_translated(result, paths.INTERIM / "translated.json")
    print(f"cache: {result.from_cache}  api: {result.from_api}  billed: {result.billed}")
    if result.stopped_at:
        print(f"STOPPED: {result.stopped_at}", file=sys.stderr)
        return 1
    return 0


def _verify(args) -> int:
    from parfum.verify import verify, write_flags

    translated_path = paths.INTERIM / "translated.json"
    if not translated_path.is_file():
        print(f"ERROR: {translated_path} does not exist. Run 'parfum translate' first.", file=sys.stderr)
        return 1

    book = _read_book()
    with open(translated_path, encoding="utf-8") as handle:
        translated = json.load(handle)

    result = verify(book, translated, scope=args.scope)
    write_flags(result, paths.INTERIM / "flags.json")

    print(f"checked: {result.checked_saetze} sentences, {result.checked_sektionen} sektionen  "
          f"flags: {len(result.flags)}")
    if not result.is_valid:
        for flag in result.flags[:20]:
            print(f"  [{flag.defect_type.value}] {flag.satz_id}: {flag.message}", file=sys.stderr)
        if len(result.flags) > 20:
            print(f"  ... and {len(result.flags) - 20} more flags (see data/interim/flags.json)", file=sys.stderr)
        return 1
    return 0


def _render(args) -> int:
    from parfum.render import render_book

    translated_path = paths.INTERIM / "translated.json"
    if not translated_path.is_file():
        print(f"ERROR: {translated_path} does not exist. Run 'parfum translate' first.", file=sys.stderr)
        return 1

    book = _read_book()
    with open(translated_path, encoding="utf-8") as handle:
        translated = json.load(handle)

    summary = render_book(book, translated, paths.OUTPUT, scope=args.scope, force=args.force)

    print(f"emitted: {summary.emitted}  skipped: {summary.skipped}  "
          f"conflicts: {len(summary.conflicts)}  total: {summary.total}")
    if summary.conflicts:
        for conflict in summary.conflicts:
            print(f"CONFLICT: {conflict} was hand-edited; wrote incoming to *.incoming.md", file=sys.stderr)
        return 1
    return 0


def _notion_client(api_key: str, parent_id: str):
    import httpx
    from parfum.notion import NotionClient

    client = httpx.Client(timeout=60.0)
    return NotionClient(
        api_key,
        parent_id,
        lambda method, url, **kw: client.request(method, url, **kw),
    )


def _publish(args) -> int:
    from parfum.publish import PublishedLedger, publish

    translated_path = paths.INTERIM / "translated.json"
    if not translated_path.is_file():
        print(f"ERROR: {translated_path} does not exist. Run 'parfum translate' first.", file=sys.stderr)
        return 1

    api_key = os.environ.get("NOTION_API_KEY")
    parent_id = os.environ.get("NOTION_PARENT_ID")
    if not api_key:
        print("ERROR: NOTION_API_KEY is not set", file=sys.stderr)
        return 1
    if not parent_id:
        print("ERROR: NOTION_PARENT_ID is not set", file=sys.stderr)
        return 1

    book = _read_book()
    with open(translated_path, encoding="utf-8") as handle:
        translated = json.load(handle)

    ledger_path = paths.OUTPUT / "published.json"
    ledger = PublishedLedger.load(ledger_path)
    client = _notion_client(api_key, parent_id)

    summary = publish(
        book,
        translated,
        client,
        ledger,
        scope=args.scope,
        force=args.force,
        dry_run=args.dry_run,
        ledger_path=ledger_path,
    )

    print(f"published: {summary.published}  updated: {summary.updated}  "
          f"skipped: {summary.skipped}  total: {summary.total}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="parfum")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("extract", help="PDF -> raw.txt + pagemap.json")
    sub.add_parser("segment", help="raw.txt -> book.json")
    sub.add_parser("check", help="verify book.json against raw.txt")
    se = sub.add_parser("senses", help="kaikki JSONL -> data/reference/senses.json")
    se.add_argument("--jsonl", required=True)
    se.add_argument("--min-count", type=int, default=8)
    cand = sub.add_parser("glossary-candidates",
                          help="book.json -> candidates.tsv for curation")
    cand.add_argument("--min-count", type=int, default=8)
    sub.add_parser("glossary-validate", help="check config/glossary.tsv")
    sub.add_parser("glossary-upload", help="create the DeepL glossary")
    ab = sub.add_parser("glossary-ab", help="translate a sample with and without")
    ab.add_argument("--scope", default="T1.K01")
    tr = sub.add_parser("translate", help="book.json -> translated.json")
    tr.add_argument("--scope", default=None)
    tr.add_argument("--force", action="store_true")
    tr.add_argument("--dry-run", action="store_true")
    ve = sub.add_parser("verify", help="check translated.json against book.json")
    ve.add_argument("--scope", default=None)
    rn = sub.add_parser("render", help="book.json + translated.json -> data/output/ markdown")
    rn.add_argument("--scope", default=None)
    rn.add_argument("--force", action="store_true")
    pb = sub.add_parser("publish", help="book.json + translated.json -> Notion child pages")
    pb.add_argument("--scope", default=None)
    pb.add_argument("--force", action="store_true")
    pb.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return {
        "extract": _extract,
        "segment": _segment,
        "check": _check,
        "senses": _senses,
        "glossary-candidates": _glossary_candidates,
        "glossary-validate": _glossary_validate,
        "glossary-upload": _glossary_upload,
        "glossary-ab": _glossary_ab,
        "translate": _translate,
        "verify": _verify,
        "render": _render,
        "publish": _publish,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
