# Query Set Comma Parser

Date: 2026-05-07

## Goal

Prevent clinical paragraphs with commas from being truncated when loaded into the query-set evaluator.

## Change

- Replaced the query-set line parser that split every comma with a safer parser:
  - tab still separates query from expected CUI(s)
  - a comma only separates expected CUI(s) when the line ends with valid CUI tokens
  - ordinary commas inside clinical text are preserved as part of the query
- Added support for multiple expected CUIs using `|`, `;`, or comma separators after the query.
- Updated the query-set label to say expected CUI(s) can be added after a tab or final comma.

## Measurement

Measured against `docs/search_quality/paragraphs.json`.

- Paragraph tests: 80
- Paragraphs containing commas: 64
- Lines the old parser would truncate at the first comma: 64
- Lines preserved by the new parser unless they end in valid expected CUI tokens: 64

Example:

- Before parser query: `Patient with heart failure with reduced ejection fraction reported worsening orthopnea and leg edema after missing several doses of furosemide. Exam showed bibasilar crackles`
- After parser query: `Patient with heart failure with reduced ejection fraction reported worsening orthopnea and leg edema after missing several doses of furosemide. Exam showed bibasilar crackles, and echocardiogram demonstrated reduced ejection fraction.`

## Verification

- `node --check docs/search_quality/app.js`
- Parser spot checks:
  - `Fever, cough, myalgia` -> query preserved, no expected CUI
  - `appendectomy surgical procedure,C0003611` -> query plus expected `C0003611`
  - `migraine\tC0149931|C0075632` -> query plus two expected CUIs
  - `query, C0000001; NEW1234567` -> query plus two expected CUIs
- Paragraph corpus check:
  - `80` paragraph tests
  - `64` comma-containing paragraph tests protected from old first-comma truncation

## Scope

- No ranking, label, relation, or vector data changes.
- No paragraph benchmark rerun was needed because this fixes browser-side batch query parsing only.
