# Security Rules - TDD Orchestrator

These rules are ALWAYS enforced when developing the TDD Orchestrator.

## Database Security

- **NEVER** use f-strings or string formatting to build SQL queries
- **ALWAYS** use parameterized queries with `?` placeholders for SQLite
- **NEVER** expose raw database errors to users (wrap with safe messages)
- **ALWAYS** validate table/column names against schema before dynamic queries

## Credential & Secret Protection

- **NEVER** hardcode API keys, tokens, or credentials in source code
- **NEVER** commit `.env` files, API keys, or authentication tokens
- **ALWAYS** load credentials from environment variables
- **ALWAYS** use placeholder patterns in documentation (e.g., `$ANTHROPIC_API_KEY`)

## Process Execution Safety

- **NEVER** use `shell=True` in subprocess calls
- **NEVER** pass unsanitized user input to subprocess arguments
- **ALWAYS** validate and sanitize task names used in file paths or git branch names
- **ALWAYS** use list-form arguments for subprocess.run/Popen

## Dependency Management

- **NEVER** add dependencies without checking for known CVEs
- **ALWAYS** keep optional dependencies optional (graceful degradation)
- **ALWAYS** pin minimum versions in pyproject.toml

## Data Handling

- **NEVER** store sensitive data (API responses, credentials) in the SQLite database
- **NEVER** log full API responses that may contain tokens or keys
- **ALWAYS** sanitize error messages before displaying to users
- **ALWAYS** use safe serialization (JSON only, no unsafe formats for untrusted data)
