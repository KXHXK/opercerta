# OperCerta Windows Native PostgreSQL 18 Environment Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task by task. On any unexpected installer, service, authentication, or test result, invoke `superpowers:systematic-debugging` before changing course. Before any completion claim, invoke `superpowers:verification-before-completion`.

**Goal:** Install and prove a local-only PostgreSQL 18.4 instance on this Windows workstation so OperCerta can resume the reliability-kernel plan at the PostgreSQL approval-race RED test without depending on WSL2 or Docker Desktop.

**Architecture:** Windows-native `uv` and pytest connect through SQLAlchemy/Psycopg to a PostgreSQL 18.4 Windows service listening only on `127.0.0.1:55432`. A dedicated `opercerta` role owns only `opercerta_test`. The connection URL lives only in ignored `.env.local`; repository documentation records non-secret verification evidence and keeps the release gate closed.

**Tech Stack:** Windows PowerShell 5.1, EDB-certified PostgreSQL 18.4 Windows x86-64 interactive installer, PostgreSQL command-line tools, SQLAlchemy 2.0.51, Psycopg 3.3.4, uv 0.11.28, pytest 9.1.1.

**Official version check (2026-07-15):** PostgreSQL's versioning policy identifies 18.4 as the current supported minor release for major 18. The PostgreSQL Windows download page directs users to the EDB-certified interactive installer, and EDB lists PostgreSQL 18.4 for Windows x86-64. Use only these primary sources:

- https://www.postgresql.org/support/versioning/
- https://www.postgresql.org/download/windows/
- https://www.enterprisedb.com/software-downloads-postgres
- https://www.enterprisedb.com/docs/supported-open-source/postgresql/installing/windows/

---

## Scope and stop conditions

- Work only in `D:\CODEX\agent-portfolio\opercerta` plus the local PostgreSQL installation/data directories.
- Do not repair WSL2 again, install Docker Desktop, start Redis, create another project, or make a release/deployment claim.
- The PostgreSQL installer password and OperCerta database password are entered only in local interactive prompts and `.env.local`. Never echo, paste into chat, place in a command literal, add to docs, or commit either secret.
- Stop before business database code if the installer signature is invalid, PostgreSQL is not exactly 18.4, the service cannot bind only to loopback, SCRAM authentication cannot be proved, or the database connectivity probe fails.
- Passing this plan changes only the local Task 3 precondition. The OperCerta release gate remains **CLOSED** until the full reliability plan and later Linux/Docker release validation pass.

### Task 1: Prove the baseline and acquire the official installer

**Files:**

- Verify: `.gitignore`
- No repository write in this task

- [ ] **Step 1: Confirm repository and secret-file safety**

Run from the repository root:

```powershell
git status --short --branch
git check-ignore -v .env.local
```

Expected: the worktree is clean before execution, and `git check-ignore` points to the `.env.*` rule in `.gitignore`. If the file is not ignored, fix `.gitignore` and commit that isolated documentation/configuration change before continuing.

- [ ] **Step 2: Record the current failing environment precondition**

```powershell
$psql = Get-Command psql.exe -ErrorAction SilentlyContinue
$services = Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue
$portOpen = Test-NetConnection -ComputerName 127.0.0.1 -Port 55432 -InformationLevel Quiet
[pscustomobject]@{
    PsqlFound = [bool]$psql
    PostgreSQLServices = @($services).Count
    Port55432Open = $portOpen
}
```

Expected on the known baseline: `PsqlFound=False`, `PostgreSQLServices=0`, and `Port55432Open=False`. If any value differs, stop and audit the existing installation/service instead of installing a second cluster.

- [ ] **Step 3: Download PostgreSQL 18.4 from the official Windows path**

Open `https://www.postgresql.org/download/windows/`, follow the EDB interactive-installer link, select **PostgreSQL 18.4**, **Windows x86-64**, and download it to the current user's Downloads folder. Do not use a mirror, repack, prebuilt VM, or PostgreSQL 19 beta.

- [ ] **Step 4: Validate the downloaded artifact before elevation**

```powershell
$installer = Get-ChildItem -LiteralPath "$env:USERPROFILE\Downloads" -Filter 'postgresql-18.4-*-windows-x64.exe' |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $installer) { throw 'PostgreSQL 18.4 Windows x64 installer was not found.' }

$signature = Get-AuthenticodeSignature -LiteralPath $installer.FullName
$hash = Get-FileHash -Algorithm SHA256 -LiteralPath $installer.FullName
[pscustomobject]@{
    File = $installer.Name
    SignatureStatus = $signature.Status
    Signer = $signature.SignerCertificate.Subject
    SHA256 = $hash.Hash
}
if ($signature.Status -ne 'Valid') { throw "Installer signature is $($signature.Status)." }
```

Expected: an exact `postgresql-18.4-*-windows-x64.exe` match and `SignatureStatus=Valid`. Preserve the displayed filename, signer, and SHA-256 for Task 4 evidence; they are artifact facts, not performance metrics.

### Task 2: Install PostgreSQL interactively with no secret disclosure

**Files:**

- System create: `C:\Program Files\PostgreSQL\18\`
- System create: `D:\PostgreSQL\18\data\`
- System create: Windows service `postgresql-x64-18`

- [ ] **Step 1: Launch the signed installer visibly with elevation**

```powershell
Start-Process -FilePath $installer.FullName -Verb RunAs -Wait
```

This visible window is intentional because the user must handle the UAC prompt and enter the superuser password locally. Use these wizard choices:

- Installation directory: `C:\Program Files\PostgreSQL\18`
- Components: PostgreSQL Server and Command Line Tools; pgAdmin is optional; clear Stack Builder
- Data directory: `D:\PostgreSQL\18\data`
- Superuser password: user-created and entered only in the installer UI
- Port: `55432`
- Locale: operating-system default
- Final page: do not launch Stack Builder

Expected: the installer completes without changing the repository.

- [ ] **Step 2: Verify installed binaries, service, and server readiness**

Open a fresh PowerShell session, then run:

```powershell
$pgBin = 'C:\Program Files\PostgreSQL\18\bin'
$serviceName = 'postgresql-x64-18'
& "$pgBin\postgres.exe" --version
Get-Service -Name $serviceName | Format-List Name,Status,StartType
& "$pgBin\pg_isready.exe" -h 127.0.0.1 -p 55432
```

Expected: `postgres (PostgreSQL) 18.4`, service status `Running`, start type `Automatic`, and `accepting connections`. A different patch version or missing service is a stop condition, not permission to weaken the version lock.

- [ ] **Step 3: Capture installer failures without speculative fixes**

If Step 1 or Step 2 fails, record the exact installer message, Windows Event Viewer service error, service state, and the most recent PostgreSQL log under `D:\PostgreSQL\18\data\log\`. Redact secrets. Invoke `superpowers:systematic-debugging`; do not proceed to Task 3 or write OperCerta database production code.

### Task 3: Restrict the cluster, provision the test database, and prove connectivity

**Files:**

- System modify: `D:\PostgreSQL\18\data\postgresql.conf`
- System modify: `D:\PostgreSQL\18\data\pg_hba.conf`
- Local ignored create: `.env.local`

- [ ] **Step 1: Restrict the server to IPv4 loopback and SCRAM**

Inspect the existing configuration first. Stop `postgresql-x64-18`, then use `apply_patch` to make the effective settings exactly:

```conf
listen_addresses = '127.0.0.1'
port = 55432
password_encryption = 'scram-sha-256'
```

Ensure `pg_hba.conf` has these host rules before any broader host rule:

```conf
host    all    all    127.0.0.1/32    scram-sha-256
host    all    all    ::1/128         reject
```

Restart the service from an elevated PowerShell window:

```powershell
Restart-Service -Name postgresql-x64-18
```

Expected: the service returns to `Running`. Keep the installer's original configuration files/backups; do not delete the cluster if restart fails.

- [ ] **Step 2: Prove there is no non-loopback listener**

```powershell
$listeners = Get-NetTCPConnection -State Listen -LocalPort 55432
$listeners | Select-Object LocalAddress,LocalPort,OwningProcess
if (@($listeners).Count -ne 1 -or $listeners.LocalAddress -ne '127.0.0.1') {
    throw 'PostgreSQL is not restricted to exactly 127.0.0.1:55432.'
}
& 'C:\Program Files\PostgreSQL\18\bin\pg_isready.exe' -h 127.0.0.1 -p 55432
```

Expected: exactly one listener, `127.0.0.1:55432`, followed by `accepting connections`.

- [ ] **Step 3: Create the dedicated role and database through an interactive prompt**

Run `psql` without putting a password in the command. Enter the installer-created `postgres` password only when prompted:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -h 127.0.0.1 -p 55432 -U postgres -d postgres -W
```

At the `psql` prompt, run:

```sql
SELECT format('CREATE ROLE %I LOGIN', 'opercerta')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'opercerta')
\gexec
\password opercerta
SELECT format('CREATE DATABASE %I OWNER %I', 'opercerta_test', 'opercerta')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'opercerta_test')
\gexec
REVOKE ALL ON DATABASE opercerta_test FROM PUBLIC;
\q
```

Choose and re-enter the OperCerta role password only in the hidden `\password` prompts. The SQL is rerunnable without duplicating the role or database; `\password` deliberately rotates the local test credential on a rerun.

- [ ] **Step 4: Create the ignored local connection configuration**

Create `.env.local` in the repository root with one line named `OPERCERTA_DATABASE_URL` whose value uses the `opercerta` role, its locally entered URL-encoded password, `127.0.0.1`, port `55432`, and database `opercerta_test`. Do this in a local editor; do not paste the value into chat or a committed patch.

Verify secrecy without displaying the file:

```powershell
git check-ignore -v .env.local
git status --short --untracked-files=all
```

Expected: `.env.local` is ignored and absent from `git status`.

- [ ] **Step 5: Load the local URL without echoing it and run a real SQL probe**

```powershell
$line = Get-Content -LiteralPath .env.local |
    Where-Object { $_.StartsWith('OPERCERTA_DATABASE_URL=') } |
    Select-Object -First 1
if (-not $line) { throw 'OPERCERTA_DATABASE_URL is missing from .env.local.' }
$env:OPERCERTA_DATABASE_URL = $line.Substring('OPERCERTA_DATABASE_URL='.Length)

uv run python -c "import os; from sqlalchemy import create_engine, text; e=create_engine(os.environ['OPERCERTA_DATABASE_URL']); c=e.connect(); print(c.execute(text('select version(), current_database(), current_user, inet_server_addr()::text, inet_server_port()')).one()); c.close(); e.dispose()"
```

Expected tuple: version begins `PostgreSQL 18.4`, database is `opercerta_test`, user is `opercerta`, address is `127.0.0.1`, and port is `55432`. The command must not print the connection URL or password.

- [ ] **Step 6: Prove the effective HBA authentication method**

Use the same interactive `postgres` connection as Step 3 and run:

```sql
SELECT rule_number, type, database, user_name, address, auth_method, error
FROM pg_hba_file_rules
ORDER BY rule_number;
```

Expected: the applicable IPv4 loopback rule reports `scram-sha-256`, the IPv6 loopback rule reports `reject`, and no parse error is present.

### Task 4: Align the reliability plan and record non-secret evidence

**Files:**

- Modify: `docs/superpowers/plans/2026-07-14-opercerta-reliability-kernel.md`
- Create: `docs/release-evidence/native-postgres-environment.md`
- Modify: `IMPLEMENTATION_HANDOFF.md`

- [ ] **Step 1: Remove the stale Docker prerequisite and committed credential literals**

Update the reliability plan so it states:

- PostgreSQL 18.4 Windows service at `127.0.0.1:55432` is the current Task 3 development prerequisite.
- Docker/Redis are deferred to later release validation and are not started in Task 3.
- Task 3 creates `.env.example`, Alembic files, schema, repository, and integration tests, but does not create `compose.yaml` on this workstation.
- Task 3 loads `OPERCERTA_DATABASE_URL` from ignored `.env.local` using the non-echoing PowerShell sequence in Task 3 Step 5 above.
- No actual database or Redis password literal remains anywhere in the plan.
- The Task 3 migration step must run `uv run alembic upgrade head` and `uv run alembic current` successfully before the approval-race GREEN implementation.

Also replace the plan self-review statement that Docker is the immediate prerequisite with the native PostgreSQL evidence gate, while preserving Linux/Docker as a later release gate.

- [ ] **Step 2: Write factual setup evidence without secrets or release claims**

Create `docs/release-evidence/native-postgres-environment.md` with:

- UTC and Asia/Shanghai timestamps
- Git commit at verification time
- Windows edition/build
- installer filename, valid Authenticode signer, and SHA-256
- `postgres --version`, service name/status/start type
- non-secret install/data/config paths
- listener address/port and effective HBA auth method
- database/user names, but no password or connection URL
- exact verification commands, exit codes, and observed outputs
- `uv run pytest tests/unit -q` result
- explicit statement: “Local Task 3 prerequisite satisfied; OperCerta release gate remains CLOSED.”

Do not invent a speed, accuracy, reliability, cost, or coverage metric.

- [ ] **Step 3: Update the handoff only after fresh verification**

Update `IMPLEMENTATION_HANDOFF.md` to point to the native PostgreSQL evidence file and state that the next action is still OperCerta reliability-kernel Task 3, beginning with the migration and approval-race RED test. Do not describe Task 3 as implemented.

- [ ] **Step 4: Run the environment gate and regression checks**

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\postgres.exe' --version
Get-Service -Name postgresql-x64-18 | Format-List Name,Status,StartType
Get-NetTCPConnection -State Listen -LocalPort 55432 | Select-Object LocalAddress,LocalPort
& 'C:\Program Files\PostgreSQL\18\bin\pg_isready.exe' -h 127.0.0.1 -p 55432
uv run pytest tests/unit -q
git diff --check
$forbidden = @(
    ('opercerta-' + 'local-only'),
    ('POSTGRES_' + 'PASSWORD'),
    ('REDIS_' + 'PASSWORD'),
    'docker version must',
    'approved-port'
)
rg -n ($forbidden -join '|') docs/superpowers/plans/2026-07-14-opercerta-reliability-kernel.md README.md IMPLEMENTATION_HANDOFF.md
if ($LASTEXITCODE -eq 0) { throw 'A stale prerequisite or credential literal remains.' }
if ($LASTEXITCODE -gt 1) { exit $LASTEXITCODE }
git status --short --branch
```

Expected: PostgreSQL 18.4; running automatic service; only `127.0.0.1:55432`; ready; unit tests exit 0; no whitespace errors; the secret/stale-placeholder search returns no matches; only the intended documentation files are modified/untracked.

- [ ] **Step 5: Commit the verified environment handoff**

```powershell
git add docs/superpowers/plans/2026-07-14-opercerta-reliability-kernel.md docs/release-evidence/native-postgres-environment.md IMPLEMENTATION_HANDOFF.md
git diff --cached --check
git diff --cached
git commit -m "docs: record native postgres readiness"
git status --short --branch
```

Expected: clean worktree on `main`. `.env.local`, PostgreSQL data, installer artifacts, logs, and passwords must not be staged.

### Task 5: Resume the approved reliability plan at the TDD boundary

**Files:** Follow `docs/superpowers/plans/2026-07-14-opercerta-reliability-kernel.md` Task 3 exactly after its environment rewrite.

- [ ] **Step 1: Re-read the updated Task 3 before touching database production code**

Confirm the sequence remains:

1. migration and schema definition,
2. `alembic upgrade head` proof,
3. approval-race test RED because the repository is missing,
4. minimum transactional repository GREEN,
5. repeated independent-connection verification,
6. isolated commit.

- [ ] **Step 2: Stop this environment plan at the handoff boundary**

Do not implement approval or idempotency behavior as part of the environment commit. Begin that work only under the reliability plan with `superpowers:test-driven-development`. Do not start another project, and do not open the release gate.

## Plan self-review

- **Spec coverage:** selects Windows-native PostgreSQL 18.4, loopback-only port 55432, dedicated test database, local ignored credentials, real connectivity proof, and deferred Docker/Linux release validation.
- **Secret safety:** all password entry is interactive; no real secret appears in commands, docs, chat, evidence, or Git; `.env.local` is verified ignored before use.
- **Truthfulness:** evidence is written only after fresh commands succeed; version/hash/test observations are facts, not invented product metrics.
- **TDD boundary:** environment work ends before database behavior code; approval concurrency resumes with a failing test in the already approved reliability plan.
- **Scope:** only OperCerta and its local PostgreSQL dependency are touched; Redis, WSL2, Docker Desktop, deployment, and other projects remain out of scope.
