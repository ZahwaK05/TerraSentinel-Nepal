# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| main (pre-release) | Yes |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report security problems privately using one of the following methods:

1. **GitHub Private Security Advisory** (preferred): Go to the Security tab of this repository and select "Report a vulnerability".
2. **Email**: Send details to the project security contact listed in the private project wiki.

### What to include

- A description of the vulnerability and its potential impact.
- Steps to reproduce or a proof-of-concept (do not include real credentials or PII).
- Affected components, versions, or configurations.
- Any suggested mitigations you are aware of.

We will acknowledge receipt within **48 hours** and aim to provide an assessment within **7 days**.

## Sensitive Data Guidelines

The following must **never** be committed to this repository:

- AWS access keys, secret keys, or session tokens
- Mapbox or third-party API tokens
- Personal information (names, phone numbers, emails) of real citizens
- Unrestricted or proprietary satellite datasets
- Passwords or private keys of any kind

Use `.env` (never committed) for local secrets. Use GitHub Secrets for CI/CD secrets.

## Dependency Security

- Dependabot alerts are enabled on this repository.
- Dependencies are reviewed on every pull request.
- Run `pip audit` and `npm audit` locally before opening a PR.
