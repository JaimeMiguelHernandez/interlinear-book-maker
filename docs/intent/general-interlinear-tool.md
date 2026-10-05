# Intent: general interlinear-edition tool

Confirmed with the user on 2026-10-05 (interview-me).

- **Outcome:** a general interlinear study-edition tool. On first run it asks for a PDF, detects the book's language, asks for the translation language and the output format (Notion page in the user's own account, EPUB, or local PDF), then produces the edition.
- **User:** anyone who clones the repo, studying any book in any language pair.
- **Why now:** the pipeline works end to end for *Das Parfum* (German→English); the next step is opening it to other books, languages, and readers.
- **First milestone:** render the existing Parfum `translated.json` as EPUB and as PDF to judge the layout. No new translation, no generalizing yet.
- **Layout decision (2026-10-05):** after the prototype run, the user chose the side-by-side table layout for both EPUB and PDF.
- **Success:** a new person with their own PDF and Claude subscription answers the first-run questions and gets a readable edition in the format they chose. The current Parfum→English workflow keeps working.
- **Constraint:** translation stays `claude -p` on the person's own Claude subscription; first run checks that `claude` is installed. The concatenation invariant holds for every book. Copyrighted text and generated editions stay under gitignored `data/`.
- **Out of scope:** API keys or other translation engines (DeepL, Gemini), scanned PDFs without a text layer (OCR), a GUI or web upload. "Upload" means giving a file path at a CLI prompt.
