# Game Theory Directive Workflow

This folder is the canonical workflow surface for `renaissance_v4/game_theory`.

## Rule

When a directive exists in this folder, the file is the source of truth.

Do not rely on chat copy/paste as canonical when the directive file exists.

## Workflow

1. Architect creates a numbered directive file in this folder.
2. Engineer reads that directive file and performs the work.
3. Engineer appends an update to the same directive file under the engineer response section.
4. Operator tells Architect to read the directive folder.
5. Architect reviews the same directive file and appends:
   - acceptance
   - rejection with rework directive

## Numbering

Directive files should use stable ids such as:

- `GT_DIRECTIVE_001_*`
- `GT_DIRECTIVE_002_*`
- `GT_DIRECTIVE_003_*` … `GT_DIRECTIVE_008_*` (see files in this folder)
- **`GT_DIRECTIVE_015_*` … `GT_DIRECTIVE_017_*`** — Student / run exam contract stack (**015:** baseline skip + **declared Student LLM modes** / per-run persistence; **016** L1 A\|B road data; **017** L3 `data_gap` closure); tracked in `docs/STUDENT_PATH_EXAM_HIGH_LEVEL_ARCHITECTURE_v1.md` **§18.4**.

## Required sections in each directive

- header with directive id
- fault
- directive / required implementation
- proof required
- deficiencies log update requirement
- engineer update section
- architect review section

## Engineer response rule

Engineer responses must be appended to the same directive file that issued the work.

At minimum the engineer response must include:

- status
- work performed
- files changed
- proof produced
- remaining gaps
- explicit request for architect acceptance

## Architect review rule

Architect review must also be written into the same directive file.

If work is rejected, Architect appends the rework directive there so the operator can point the
engineer back to one canonical record.
