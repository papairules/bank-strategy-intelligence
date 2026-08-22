# Supervisor Agent

The Supervisor validates and combines completed Strategy and Hiring Agent JSON outputs. It supports
Q&A and full reports with evidence-backed priorities, opportunities, and 30/60/90/180/360-day
sales-action horizons. It does not run specialist agents or perform web research.

## Run

```powershell
python supervisor-agent/supervisor.py `
  --company-id "BARCLAYS" `
  --company-name "Barclays PLC" `
  --company-alias "Barclays" `
  --question "Where can we grow the Barclays account?" `
  --mode report `
  --strategy-output strategy-output.json `
  --hiring-output hiring-agent/output/barclays_integration_fixture.json
```

`--company-alias`, `--allowed-subsidiary`, and `--excluded-entity` can be repeated. Mode can be
`auto`, `report`, or `qa`. The public Python API is `run_supervisor(SupervisorRequest(...))`.

The Supervisor rejects nested cross-company data, deduplicates evidence, preserves provenance,
removes unsupported model claims, applies deterministic scoring, and always returns five horizon
sections.

## Test

```powershell
cd supervisor-agent
python -m unittest discover -s tests -v
```

Tests are offline and use a fake OpenAI client.
