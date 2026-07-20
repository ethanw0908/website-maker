# Queue diagnostics

The Codex generation worker must consume only the `generation` queue. The audit worker consumes the default `celery` queue.

Verify the effective Compose commands:

```bash
docker compose config | sed -n '/worker:/,/audit-worker:/p'
```

Verify active queues:

```bash
docker compose exec worker celery -A app.tasks.celery_app inspect active_queues
```

The `worker` service must report `generation`. If it reports `celery`, recreate it from the current Compose configuration:

```bash
docker compose rm -sf worker audit-worker
docker compose up -d --build --force-recreate worker audit-worker
```
