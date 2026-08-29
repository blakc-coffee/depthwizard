# DepthWizard API

Canonical contract: the Master PRD, §9 (Backend Module) — endpoints, schemas,
status/stage/error values, and artifact semantics are defined there, not
here. This file is a quick-reference index, not a second source of truth;
if it and the PRD ever disagree, the PRD wins (§0).

## Endpoints live so far (B1–B3)

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/health` | none | liveness only |
| POST | `/api/v1/jobs` | required | multipart `file`; `202` + `{job_id, status}` |
| GET | `/api/v1/jobs/{job_id}` | required | status/stage/progress/error |
| GET | `/api/v1/jobs/{job_id}/result` | required | `JOB_NOT_COMPLETE` until `completed` |
| GET | `/api/v1/jobs` | required | caller's own jobs, newest first |
| DELETE | `/api/v1/jobs/{job_id}` | required | purges storage, cascades comparisons |

`/api/v1/compare/*` is not implemented yet — stretch, gated on B6 (PRD §9.10 B7).

## Known current limitation

`ml/pipeline.py` is still a partial implementation — Depth Anything V2
integration and calibration land in ML Phase 4/5. Until then, every job's
pipeline run fails strict contract validation (`heightmap_path` and full
`metadata` aren't produced yet) and jobs take the
`queued → processing → failed` path with `ML_INFERENCE_FAILED`, not
`completed`. This is expected, not a bug — see
`integration/contracts.py::PipelineResult.validate`. The happy path
(`completed`, with a real heightmap) starts working the moment ML's output
satisfies the frozen contract, with no backend changes required.

## Local dev

```bash
docker compose up
```

Brings up Postgres, Redis, the API, and the worker. `alembic upgrade head`
runs automatically on API startup. API on `http://localhost:8000`.

```bash
cd backend && pytest
```

Runs the test suite — `test_health.py`/`test_errors.py` need no infra;
`test_job_isolation.py` needs a reachable Postgres (`TEST_DATABASE_URL`,
defaults to a `depthwizard_test` DB alongside the docker-compose Postgres)
and skips cleanly if it isn't there.
