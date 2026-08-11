# Security Policy

## Supported Versions

OperCerta is a pre-1.0 project. Security fixes are applied to the latest `main`
branch only. Historical tags and preview deployments are not maintained as
supported production releases.

## Reporting a Vulnerability

Do not disclose credentials, exploitable details, private endpoints, customer
data, or a working exploit in a public issue or pull request.

1. Prefer GitHub's **Security → Report a vulnerability** flow when it is
   available for this repository.
2. Include the affected revision, impact, prerequisites, and the smallest safe
   reproduction. Redact secrets and personal or business data.
3. If private vulnerability reporting is not available, open a public issue
   that contains only the title `Security contact requested`. Do not include
   technical details; wait for the maintainer to establish a private channel.

The maintainer will acknowledge a valid private report, assess severity, and
coordinate a fix and disclosure. No response-time SLA is promised for this
non-production project.

## Security Boundary

The public Netlify site is a read-only static showcase. The complete Agent MVP
runs locally and uses demo JWT identities and synthetic data. It must not be
treated as a production identity, public API, or repository for confidential
information. Production deployment requires a separate security review for
identity, secrets, ingress, rate limiting, backups, monitoring, and incident
response.
