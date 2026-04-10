# Qnty / QuantBot

Cleanroom quantitative trading framework (paper mode only).

## Structure

```
Qnty/
├── quantbot/
│   ├── core/       # Bus, determinism, receipts
│   ├── protocols/  # Interface protocols
│   └── exec/       # Routing, constraints
├── configs/        # JSON configs
└── tests/          # Smoke tests
```

## Determinism

Use `canonical_json_dumps` and `sha256_file` from `quantbot.core.determinism` for consistent serialization and hashing.

## Quickstart

```bash
# Developer install
pip install -e .

# Run replay
qnty-replay --manifest <path> --csv <path> --out <path>

# Alternative (module syntax also works)
python -m quantbot.cli --manifest <path> --csv <path> --out <path>
```

## Testing

```bash
pytest tests/
```
