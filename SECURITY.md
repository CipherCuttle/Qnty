# Security

## No exchange or API keys required

Qnty's public-data workflows do not require exchange credentials or API keys. If you add live integrations, store credentials outside this repo using environment variables or a secrets manager.

## Do not put secrets in the repo

Do not commit:

- API keys or secrets
- Passwords or tokens
- Private keys (SSH, TLS, etc.)
- `.env` files containing sensitive values

## Reporting issues

If you suspect a secret has been committed or discover a security vulnerability:

1. **If a secret was committed:** rotate it immediately before opening any issue or pull request.
2. **If you find a vulnerability:** open an issue with a clear description. Do not include exploit details in public issues until a fix is agreed upon.
