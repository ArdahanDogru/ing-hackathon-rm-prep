# RM action log — design

Date: 2026-10-15. Status: design approved in chat by the user on 2026-10-15
(scope option a; approach 1). Milestone **L1** (lead).

## 1. Purpose

Record every decision and edit of the RM on the preparation and meeting-text
screens, in order and with time, as the data for a later eval / optimization loop
(better options in the preparation and card panes, better Exa prompts). The loop
itself is out of scope.

## 2. Scope (the user: option a)

- Only actions that change something, recorded on the server when the API call
  comes in. No screen interactions (opened pop-ups, views, clicks), no `GET`
  request.
- The chips "Görüşmede konuşulacak" live in the browser until the approval; the
  log records the final choice at the approval.

## 3. Approach (approach 1)

A small module `src/rmprep/api/action_log.py` in the API layer: every RM action
passes through the API, so the API records it with a clear action name; this also
covers API-only actions (research questions, card downloads).

## 4. Storage and record

- Append-only JSON lines, one file per Turkish day:
  `data/logs/rm-actions/<YYYY-MM-DD>.jsonl` (`data/` is not in git).
- Record: `ts` (ISO, Europe/Istanbul), `action`, `run_id`, `new_run_id` (when the
  action made a new run, else omitted), `persona_id`, `snapshot_id`, `lang`
  (when the action has one), `details` (per action, below). One JSON object per
  line, UTF-8, keys in a fixed order.
- Nothing from the log goes to an LLM or an outside service.

## 5. Actions

| Action | Endpoint | details |
|---|---|---|
| `run_opened` | `POST /api/runs` | `test_run`, `persona_changes`, `excluded_sources`, `state` |
| `question_answered` | `POST /api/runs/{id}/answers` | `question_id`, `answer` |
| `holdings_set` | `POST /api/runs/{id}/holdings` (shares) | `shares`, `origin` |
| `holdings_reset` | `POST /api/runs/{id}/holdings` (null) | — |
| `decision_approved` / `decision_rejected` | `POST /api/runs/{id}/approval` | `engine_top3`, `agent_top3`, `agent_state`, `selected`, `note` |
| `notes_saved` | `PUT /api/runs/{id}/notes` | `note`, `option_notes` |
| `text_block_edited` / `text_block_deleted` / `text_block_restored` | `PUT /api/runs/{id}/narrative/{lang}/blocks/{block}` | `block_id`, `before`, `after`, `findings` |
| `card_downloaded` | `GET /api/runs/{id}/card.md` | `format` (md), `has_text` |
| `research_question` | `POST /api/runs/{id}/research/questions` | `question`, `refused`, `findings` (count) |

- `card_downloaded` is the one logged `GET`: it is a deliberate RM action (a file
  download), not a page view. A refused card (open rule finding, 422) is logged
  with `details.refused: true`.
- `text_block_*`: `before` is the block text before the call (the original or the
  last edit), `after` the text after it (`""` for a deletion, the original for a
  restore).
- A refused action (4xx) is logged only for `card_downloaded` and
  `research_question` (the refusal is part of the signal); other 4xx calls change
  nothing and are not logged.

- The PDF is the browser's print of the print page: the server cannot tell it
  from a page view, so it is not logged without a web change (the user,
  2026-10-15: no frontend change in L1).

## 6. Safety

- A failed write never stops or changes the RM's action: the error goes to the
  server log (stderr) only.
- Writes are serialised with a lock (the API runs threads).
- Records can contain the RM's notes and edited text. With the synthetic personas
  this is acceptable; with real client data a KVKK review is required before the
  log is kept or used (stated in `docs/web-ui.md`).

## 7. Tests

- Each action of section 5 writes exactly one record with the right fields.
- `new_run_id` for the actions that make a new run.
- No record for a `GET` other than the card, or for a refused action other than
  the two in section 5.
- A failed write (read-only folder) does not break the action.
- Records of one day append to one file in call order.

## 8. Out of scope

The optimization loop; screen interactions; a reading or export tool; rotation or
size limits.
