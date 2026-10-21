# JAMRIG sports catalog and competition engine

## Existing architecture

JAMRIG is a Flask application using SQLAlchemy and the configured MySQL or SQLite database. `Sport` lives in the existing `sports` table. Events retain both `events.sport_id` and the legacy `event_sports` association; tournaments may link an event and must use a sport linked to it when event sport relationships are present. Existing auction event, team, and player workflows remain intact.

## Catalog

`backend/sports_catalog.py` upgrades old `sports` tables additively and repeatably. The catalog currently has 159 entries, 125 traditional sports and 34 esports. Sport metadata advertises generic competition formats and scoring templates where configured. Catalog presence does not certify official scoring rules or full support.

## Competition data model

- `Tournament` references the existing sport, optional event, and creator. It stores format, participant type, scoring template, lifecycle state, capacity, draw policy, configurable standings points, and a version column used for optimistic concurrency checks.
- `TournamentParticipant` relates a tournament to exactly one existing player or team. Database unique constraints prevent duplicate player/team registration; active state preserves withdrawal history.
- `CompetitionMatch` stores round and bracket position, lifecycle and result-confirmation states, schedule/venue, normalized winner/draw references, and validated sport-specific score JSON.
- `CompetitionMatchSide` relates match slots to tournament entrants. Knockout and round-robin formats create two-slot matches; `multi_entrant` placement matches use one row per entrant, so the shared model does not require every match to be a two-player match.
- `MatchResultAudit` records submissions, corrections, rejections, and confirmations. `TournamentAudit` records tournament creation, edits, lifecycle changes, registration/withdrawal, and fixture generation.

## Formats and lifecycle

The engine supports:

- `single_elimination`: deterministic entrant order, next-power-of-two bracket, explicit byes, and winner advancement after result confirmation. Ties are rejected.
- `round_robin`: circle-method pair schedule. Odd fields get one recorded bye per entrant. Confirmed results feed standings, with configurable win/draw/loss points (defaults 3/1/0).
- `multi_entrant`: one multi-participant placement match for catalog entries configured with the generic placement template. This does not calculate sport-specific performance rules.

Tournament states are `draft → registration → ready → in_progress → completed`, with cancellation permitted before completion. The organizer can start from registration or ready once minimum entrants are registered. Brackets cannot be generated twice. Round-robin and multi-entrant fields are limited to 128 entrants in this phase; knockout fields are limited to 512.

Matches use `pending`, `scheduled`, `in_progress`, `completed`, `postponed`, and `cancelled`. Results are separate (`none`, `pending`, `confirmed`, `rejected`). A player/team entrant or tournament organizer can submit a result. Only the organizer or admin can confirm/reject it. Only confirmed results progress a knockout bracket or appear in standings. Organizers can correct a pending score; a confirmed knockout result can be corrected only before its next match progresses, and a completed final can be corrected without reopening the bracket. Every correction requires a reason and is audited. Conflicting or repeated finalization is rejected.

## Scoring contract and limits

`backend/competition_rules.py` supplies shape validation for points, placement, series/maps, sets-shaped series, win/draw/loss, and timed/distance data. The tournament fixes its scoring template from the selected sport configuration. The result API validates scores against the actual match entrant IDs and rejects unsupported or mismatched templates. Generic validators do not implement official Football, Cricket, Carrom, Chess, Tennis, or esports rules. No sport has fully tested official rules in this phase.

Tournament creation is rejected if the sport is inactive, the requested format is not enabled for that sport, the participation type does not match, or a supported scoring template is not configured. Players must be active; teams must be active. When an event is linked, teams must belong to it and individuals must already be linked through the existing event registration association.

## API

All mutation endpoints require a valid existing JAMRIG session. The creator or admin manages tournament configuration, lifecycle, schedule, and confirmation. Entrants can register/withdraw themselves or their own team; the organizer/admin can register or withdraw on their behalf. Tournament, fixture, score, standings, and history reads are public, matching the current public event-read pattern.

| Endpoint | Purpose |
|---|---|
| `GET/POST /api/tournaments` | List/filter tournaments; create one |
| `GET/PUT /api/tournaments/<id>` | Tournament details; update draft/registration settings |
| `POST /api/tournaments/<id>/open` | Open registration |
| `POST /api/tournaments/<id>/ready` | Close registration after minimum entrants |
| `POST /api/tournaments/<id>/start` | Generate fixtures and start |
| `POST /api/tournaments/<id>/cancel` | Cancel before completion |
| `GET/POST /api/tournaments/<id>/participants` | List/register entrants |
| `POST /api/tournaments/<id>/participants/<participant_id>/withdraw` | Withdraw an entrant during registration |
| `GET /api/tournaments/<id>/matches` | Read fixtures; supports `limit` and `offset` |
| `GET/PUT /api/matches/<id>` | Read or schedule a match |
| `POST /api/matches/<id>/transition` | Start, postpone, resume, or cancel a match |
| `POST/PUT /api/matches/<id>/results` | Submit a result or correct an unconfirmed/eligible confirmed result |
| `POST /api/matches/<id>/confirm` | Confirm a pending result and progress the tournament |
| `POST /api/matches/<id>/reject` | Reject a pending result with a reason |
| `GET /api/tournaments/<id>/standings` | Round-robin standings |
| `GET /api/tournaments/<id>/history` | Tournament and match-result audit history |

For example, submit a points result with `{"score":{"<entrant_id_1>":2,"<entrant_id_2>":1}}`. Multi-entrant placement scores include every entrant ID: `{"score":{"<entrant_id_1>":1,"<entrant_id_2>":2,"<entrant_id_3>":3}}`. For templates needing additional fields, include them beside `score`, such as `winner_participant_id`, `measurement_type`, `unit`, or `ranking`.

## Admin frontend

The existing admin dashboard has a Tournaments tab. It loads sports/formats from the backend, creates tournaments, opens registration, registers player/team IDs, generates fixtures, displays results, and submits/confirms scores. Match scheduling, corrections, standings, and history remain available through the APIs but do not yet have dedicated dashboard controls.

## Migration and tests

The app already calls SQLAlchemy `Base.metadata.create_all`, so startup creates the new tables without altering or dropping existing tables. A manual idempotent table-only upgrade is also available from `backend/`:

```powershell
python add_tournament_tables.py
```

Run focused tests from `backend/`:

```powershell
python -m unittest test_competition_rules test_tournament_engine -v
```

The tournament tests use a fresh in-memory SQLite database and do not touch the configured application database.

## Support status

- **Catalogued:** 159 entries.
- **Executable generic formats:** single elimination, round robin, and configured multi-entrant placement.
- **Implemented:** tournament lifecycle and registration, fixture generation/byes, match scheduling/state, validated result submission/confirmation/correction, knockout advancement, round-robin standings, and audit history.
- **Official sport-specific rules:** none implemented or fully tested.
- **Not included in this phase:** double elimination, groups/playoffs, participant disqualification, ranking across tournaments, dispute workflow, sport-specific officials, complete scheduling conflict detection, or dedicated UI for schedule/correction/standings/history.
