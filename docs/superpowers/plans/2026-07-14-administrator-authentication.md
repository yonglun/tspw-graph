# Administrator Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent administrator accounts and secure server-side sessions, then require an authenticated administrator for the administrator, build, review, and “add to review” capabilities while keeping graph learning pages public.

**Architecture:** FastAPI owns Argon2id password verification, opaque HttpOnly session cookies, CSRF validation, login throttling, administrator lifecycle rules, and audit events in the existing SQLite database. React restores the session through `/api/auth/session`, keeps the CSRF value only in memory, guards protected routes, and conditionally renders protected navigation and graph actions. Existing Worker jobs remain unchanged because authorization is completed before API operations enqueue or control jobs.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2, SQLite, argon2-cffi, Pydantic Settings, React 19, TypeScript 5.8, React Router 7, Vitest, Testing Library, Playwright, Docker Compose.

## Global Constraints

- Default administrator username is `admin` and default initial password is `Pass@word1` only when the administrator table is empty.
- Every newly created or reset administrator must change the temporary password at next login.
- Passwords require at least 10 characters and at least one uppercase letter, lowercase letter, digit, and special character.
- Administrator usernames are trimmed, case-insensitively unique, and 3–64 characters long.
- All administrators have equal authority; no roles or project-level permissions are introduced.
- Administrators cannot disable themselves or the last enabled administrator, and accounts are never permanently deleted.
- Sessions use opaque HttpOnly cookies, persist across browser restarts, and expire after 8 hours of inactivity.
- Five failed login attempts for the same normalized username and source IP lock that combination for 15 minutes.
- Unsafe authenticated requests require an in-memory CSRF value in `X-CSRF-Token`.
- Password reset or account disable revokes every target session; changing one's own password revokes other sessions but keeps the current session.
- Public guide, ontology, graph read, story, QA, project list, and graph evidence APIs remain anonymous.
- Administrator, build, review, model profile, job control, project mutation, and “add to review” APIs require a ready administrator session.
- The browser must not store passwords, session tokens, or CSRF values in `localStorage` or `sessionStorage`.
- Audit events must never contain plaintext passwords, password hashes, cookies, opaque session tokens, or CSRF values.

---

## File Structure

### Backend files to create

- `apps/api/src/app/auth/__init__.py` — package boundary.
- `apps/api/src/app/auth/models.py` — SQLAlchemy administrator, session, throttle, and audit tables.
- `apps/api/src/app/auth/schemas.py` — API request/response contracts and `AuthContext`.
- `apps/api/src/app/auth/security.py` — password policy, Argon2id, token generation, SHA-256 session-token hashing, constant-time CSRF comparison.
- `apps/api/src/app/auth/repository.py` — transaction-safe persistence and queries.
- `apps/api/src/app/auth/service.py` — login, session, password, administrator lifecycle, throttling, and audit rules.
- `apps/api/src/app/auth/dependencies.py` — FastAPI service/context/CSRF dependencies.
- `apps/api/src/app/auth/router.py` — `/api/auth/*` routes.
- `apps/api/src/app/auth/admin_router.py` — `/api/admins` and `/api/admin-audit-events` routes.
- `apps/api/src/app/auth/recover.py` — container CLI for one-time password recovery of an existing administrator.
- `apps/api/tests/auth/test_security.py` — password and token primitive tests.
- `apps/api/tests/auth/test_repository.py` — schema, uniqueness, transaction, and persistence tests.
- `apps/api/tests/auth/test_service.py` — bootstrap, login, throttle, session, lifecycle, and audit tests.
- `apps/api/tests/auth/test_router.py` — Cookie, CSRF, error-code, and endpoint integration tests.
- `apps/api/tests/auth/test_protected_routes.py` — anonymous/forced-change/ready-session route matrix.

### Frontend files to create

- `apps/web/src/app/AuthContext.tsx` — session restoration, authentication actions, CSRF wiring, and cross-tab synchronization.
- `apps/web/src/app/ProtectedRoute.tsx` — ready-session route guard with safe `returnTo` handling.
- `apps/web/src/features/auth/LoginPage.tsx` — administrator login.
- `apps/web/src/features/auth/ChangePasswordPage.tsx` — forced and voluntary password change.
- `apps/web/src/features/auth/AuthPages.test.tsx` — login, forced change, and safe redirect tests.
- `apps/web/src/features/admin/AdminPage.tsx` — administrator list and audit surface.
- `apps/web/src/features/admin/AdminDialog.tsx` — create, edit, reset, enable, and disable dialogs.
- `apps/web/src/features/admin/AdminPage.test.tsx` — administrator maintenance interaction tests.
- `tests/e2e/auth.setup.ts` — repeatable admin login/forced-change setup and storage-state generation.
- `tests/e2e/admin-auth.spec.ts` — anonymous visibility, protected navigation, and administrator lifecycle browser tests.

### Existing files to modify

- `apps/api/pyproject.toml` — add `argon2-cffi`.
- `apps/api/src/app/settings.py` — authentication configuration.
- `apps/api/src/app/main.py` — bootstrap tables/admin and mount auth/admin routers.
- `apps/api/src/app/projects/router.py` — protect upload, attribute jobs, and deletion while leaving reads public.
- `apps/api/src/app/jobs/router.py` — protect all job reads and controls.
- `apps/api/src/app/extraction/router.py` — protect model-profile discovery.
- `apps/api/src/app/review/router.py` — protect every review route and use the authenticated username for actions.
- Existing backend router tests — inject a ready administrator dependency and add anonymous assertions.
- `apps/web/src/api/client.ts` — typed API errors, CSRF header injection, and authentication callbacks.
- `apps/web/src/App.tsx` — provider, conditional navigation, account menu, and login entry.
- `apps/web/src/app/router.tsx` — login/change-password/admin routes and protected wrappers.
- `apps/web/src/features/graph/GraphPage.tsx` and `EntityPanel.tsx` — hide and disable “加入审核” when anonymous.
- Existing frontend tests — provide explicit anonymous or ready-auth fixtures.
- `apps/web/src/styles/base.css` and `apps/web/src/styles/vercel.css` — auth/admin layout using the existing Vercel-style tokens.
- `compose.yaml`, `.env.example`, `README.md`, and `docs/deployment-docker-azure-openai.md` — runtime settings and recovery instructions.
- `apps/web/nginx.conf` — preserve external host/protocol and overwrite the trusted client-IP header.
- `tests/e2e/playwright.config.ts`, `tests/e2e/online-build.spec.ts`, and `tests/e2e/review.spec.ts` — authenticated storage state for protected flows.

---

### Task 1: Authentication persistence and security primitives

**Files:**
- Create: `apps/api/src/app/auth/__init__.py`
- Create: `apps/api/src/app/auth/models.py`
- Create: `apps/api/src/app/auth/security.py`
- Create: `apps/api/src/app/auth/repository.py`
- Test: `apps/api/tests/auth/test_security.py`
- Test: `apps/api/tests/auth/test_repository.py`
- Modify: `apps/api/pyproject.toml`
- Modify: `apps/api/src/app/settings.py`

**Interfaces:**
- Produces: `PasswordPolicy.validate(password: str) -> list[str]`.
- Produces: `PasswordSecurity.hash(password: str) -> str` and `PasswordSecurity.verify(hash_value: str, password: str) -> bool`.
- Produces: `new_token() -> str`, `hash_session_token(token: str) -> str`, and `csrf_matches(expected: str, presented: str) -> bool`.
- Produces: SQLAlchemy `AdminAccount`, `AdminSession`, `AdminLoginThrottle`, and `AdminAuditEvent` models.
- Produces: `AuthRepository(engine: Engine, clock: Callable[[], datetime] | None = None)` with focused CRUD/transaction methods used by Tasks 2–4.

- [ ] **Step 1: Add failing password and token tests**

Create tests that define the exact rule codes and prove session tokens are never persisted directly:

```python
def test_password_policy_reports_each_missing_requirement():
    assert PasswordPolicy.validate("short") == [
        "MIN_LENGTH",
        "UPPERCASE_REQUIRED",
        "DIGIT_REQUIRED",
        "SPECIAL_REQUIRED",
    ]
    assert PasswordPolicy.validate("Pass@word1") == []


def test_hash_and_verify_password_without_plaintext_storage():
    encoded = PasswordSecurity().hash("Pass@word1")
    assert "Pass@word1" not in encoded
    assert PasswordSecurity().verify(encoded, "Pass@word1") is True
    assert PasswordSecurity().verify(encoded, "wrong-password") is False


def test_session_token_hash_is_stable_and_csrf_compare_is_exact():
    token = new_token()
    assert token != hash_session_token(token)
    assert hash_session_token(token) == hash_session_token(token)
    assert csrf_matches("csrf-value", "csrf-value") is True
    assert csrf_matches("csrf-value", "different") is False
```

- [ ] **Step 2: Run the security tests and verify the import failure**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/auth/test_security.py -v
```

Expected: FAIL because `app.auth.security` does not exist.

- [ ] **Step 3: Add Argon2id and implement the security primitives**

Add `argon2-cffi>=23.1,<26` to `apps/api/pyproject.toml`. Implement explicit rule ordering so API clients receive stable codes:

```python
class PasswordPolicy:
    @staticmethod
    def validate(password: str) -> list[str]:
        failures: list[str] = []
        if len(password) < 10:
            failures.append("MIN_LENGTH")
        if not any(character.isupper() for character in password):
            failures.append("UPPERCASE_REQUIRED")
        if not any(character.islower() for character in password):
            failures.append("LOWERCASE_REQUIRED")
        if not any(character.isdigit() for character in password):
            failures.append("DIGIT_REQUIRED")
        if not any(not character.isalnum() for character in password):
            failures.append("SPECIAL_REQUIRED")
        return failures


class PasswordSecurity:
    def __init__(self) -> None:
        self._hasher = PasswordHasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, hash_value: str, password: str) -> bool:
        try:
            return self._hasher.verify(hash_value, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def csrf_matches(expected: str, presented: str) -> bool:
    return bool(presented) and secrets.compare_digest(expected, presented)
```

- [ ] **Step 4: Add failing persistence tests**

Use an in-memory SQLite engine with `StaticPool`. Test case-insensitive uniqueness, session token hashing, audit metadata, and clock-controlled expiry:

```python
def test_admin_username_is_case_insensitively_unique(repository):
    repository.create_admin("Admin", "hash-1", must_change_password=True)
    with pytest.raises(IntegrityError):
        repository.create_admin("admin", "hash-2", must_change_password=True)


def test_repository_never_saves_raw_session_token(repository):
    admin = repository.create_admin("admin", "hash", must_change_password=True)
    repository.create_session(
        admin.id,
        token_hash=hash_session_token("raw-token"),
        csrf_token="csrf-value",
        ip_address="127.0.0.1",
        user_agent="pytest",
        expires_at=repository.now() + timedelta(hours=8),
    )
    session = repository.find_session(hash_session_token("raw-token"))
    assert session is not None
    assert session.token_hash != "raw-token"
    assert session.csrf_token == "csrf-value"
```

- [ ] **Step 5: Run persistence tests and verify model/repository failures**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/auth/test_repository.py -v
```

Expected: FAIL because the auth models and repository are not implemented.

- [ ] **Step 6: Implement models, repository, and settings**

Use the shared `app.projects.models.Base`. Add database uniqueness on `normalized_username`, stable string IDs, timezone-aware timestamps, indexed session token hashes, and a composite unique throttle key. Add these exact settings:

```python
auth_bootstrap_username: str = "admin"
auth_bootstrap_password: str = "Pass@word1"
auth_cookie_name: str = "tspw_admin_session"
auth_cookie_secure: bool = False
auth_session_idle_seconds: int = 8 * 60 * 60
auth_login_max_failures: int = 5
auth_login_lock_seconds: int = 15 * 60
auth_trust_forwarded_ip: bool = False
```

The repository must expose these transaction-safe methods and exact return types:

- `normalize_username(value: str) -> str`: trim and apply Unicode-safe `casefold()`.
- `create_admin(username: str, password_hash: str, *, must_change_password: bool) -> AdminAccount`: insert and return a detached account.
- `get_admin(admin_id: str) -> AdminAccount | None` and `find_admin_by_username(username: str) -> AdminAccount | None`: return detached accounts.
- `list_admins() -> list[AdminAccount]`: return accounts ordered by normalized username.
- `create_session(admin_id: str, *, token_hash: str, csrf_token: str, ip_address: str | None, user_agent: str | None, expires_at: datetime) -> AdminSession`: persist and return a detached session.
- `find_session(token_hash: str) -> AdminSession | None`: return the matching detached session.
- `touch_session(session_id: str, *, expires_at: datetime) -> AdminSession`: update `last_seen_at` and expiry.
- `revoke_session(session_id: str) -> None` and `revoke_admin_sessions(admin_id: str, *, except_session_id: str | None = None) -> None`: delete matching sessions.
- `record_login_failure(normalized_username: str, ip_address: str) -> AdminLoginThrottle`: increment atomically and set `locked_until` on the fifth failure.
- `clear_login_failures(normalized_username: str, ip_address: str) -> None`: remove the combination row.
- `add_audit_event(*, actor: AdminAccount | None, target: AdminAccount | None, action: str, result: str, ip_address: str | None, metadata: dict[str, object]) -> AdminAuditEvent`: persist only sanitized metadata.

Use `session.execute(text("BEGIN IMMEDIATE"))` for SQLite lifecycle mutations that require count-and-update consistency.

- [ ] **Step 7: Reinstall the editable API package and run Task 1 tests**

Run:

```bash
.venv/bin/python -m pip install -e 'apps/api[dev]'
.venv/bin/python -m pytest apps/api/tests/auth/test_security.py apps/api/tests/auth/test_repository.py -v
```

Expected: all Task 1 tests PASS.

- [ ] **Step 8: Commit Task 1**

```bash
git add apps/api/pyproject.toml apps/api/src/app/settings.py apps/api/src/app/auth apps/api/tests/auth/test_security.py apps/api/tests/auth/test_repository.py
git commit -m "feat: add administrator security persistence"
```

---

### Task 2: Bootstrap, login, sessions, CSRF, and password change

**Files:**
- Create: `apps/api/src/app/auth/schemas.py`
- Create: `apps/api/src/app/auth/service.py`
- Create: `apps/api/src/app/auth/dependencies.py`
- Create: `apps/api/src/app/auth/router.py`
- Test: `apps/api/tests/auth/test_service.py`
- Test: `apps/api/tests/auth/test_router.py`
- Modify: `apps/api/src/app/main.py`

**Interfaces:**
- Consumes: Task 1 `AuthRepository`, password/token helpers, and auth settings.
- Produces: `AuthContext(admin: AdminAccount, session: AdminSession)`.
- Produces: `AuthService.bootstrap_default_admin()`, `login()`, `authenticate()`, `verify_csrf()`, `logout()`, and `change_password()`.
- Produces: FastAPI `get_auth_service`, `require_session`, `require_ready_context`, and `require_ready_admin` dependencies.

- [ ] **Step 1: Write failing service tests for bootstrap, login, throttling, and session expiry**

Cover the accepted rules with a fixed clock:

```python
def test_bootstrap_is_idempotent_and_requires_password_change(service, repository):
    first = service.bootstrap_default_admin()
    second = service.bootstrap_default_admin()
    assert first.id == second.id
    assert repository.list_admins() == [first]
    assert first.must_change_password is True


def test_fifth_failure_locks_username_and_ip_for_fifteen_minutes(service):
    for _ in range(4):
        with pytest.raises(AuthError, match="INVALID_CREDENTIALS"):
            service.login("admin", "wrong", "10.0.0.1", "pytest")
    with pytest.raises(AuthError, match="ACCOUNT_LOCKED") as locked:
        service.login("admin", "wrong", "10.0.0.1", "pytest")
    assert locked.value.retry_after_seconds == 900


def test_session_expires_after_eight_idle_hours(service, clock):
    login = service.login("admin", "Pass@word1", "127.0.0.1", "pytest")
    clock.advance(timedelta(hours=8, seconds=1))
    with pytest.raises(AuthError, match="AUTHENTICATION_REQUIRED"):
        service.authenticate(login.session_token)
```

- [ ] **Step 2: Run service tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/auth/test_service.py -v
```

Expected: FAIL because `AuthService` and its contracts do not exist.

- [ ] **Step 3: Implement auth contracts and service rules**

Define these Pydantic/dataclass contracts without exposing ORM objects directly:

```python
@dataclass(frozen=True)
class AuthContext:
    admin: AdminAccount
    session: AdminSession


class SessionResponse(BaseModel):
    admin: AdminSummary
    must_change_password: bool
    csrf_token: str


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)
```

`AuthService.login()` must perform dummy Argon2 verification when the username is missing, check the throttle before validation, record failed attempts, create an 8-hour rolling session, clear failures on success, and return both the raw session token and `SessionResponse`. `authenticate()` hashes the Cookie token, rejects missing/expired/disabled sessions, touches valid sessions, and returns `AuthContext`. `change_password()` validates current password and policy, updates the hash, clears `must_change_password`, revokes other sessions, and records an audit event.

- [ ] **Step 4: Add failing router tests for Cookie, forced change, CSRF, and error shapes**

```python
def test_login_sets_http_only_cookie_and_returns_csrf(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "Pass@word1"})
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert response.json()["must_change_password"] is True
    assert response.json()["csrf_token"]


def test_change_password_requires_matching_csrf(client):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "Pass@word1"})
    missing = client.post(
        "/api/auth/change-password",
        json={"current_password": "Pass@word1", "new_password": "Better@Pass2"},
    )
    assert missing.status_code == 403
    assert missing.json()["detail"]["code"] == "CSRF_VALIDATION_FAILED"
    changed = client.post(
        "/api/auth/change-password",
        headers={"X-CSRF-Token": login.json()["csrf_token"]},
        json={"current_password": "Pass@word1", "new_password": "Better@Pass2"},
    )
    assert changed.status_code == 200
    assert changed.json()["must_change_password"] is False
```

- [ ] **Step 5: Run router tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/auth/test_router.py -v
```

Expected: FAIL because the router and dependencies are not mounted.

- [ ] **Step 6: Implement dependencies, router, and lifespan bootstrap**

Use one service dependency per request and these explicit dependency semantics:

```python
def require_session(
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> AuthContext:
    token = request.cookies.get(service.settings.auth_cookie_name)
    context = service.authenticate(token)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        service.verify_csrf(context, request.headers.get("X-CSRF-Token", ""))
    return context


def require_ready_context(context: AuthContext = Depends(require_session)) -> AuthContext:
    if context.admin.must_change_password:
        raise auth_http_error("PASSWORD_CHANGE_REQUIRED", 403)
    return context


def require_ready_admin(context: AuthContext = Depends(require_ready_context)) -> AdminAccount:
    return context.admin
```

`POST /api/auth/login` is the only unauthenticated mutation and must reject cross-origin `Origin` headers. Resolve the client IP from `request.client.host` by default; only when `auth_trust_forwarded_ip=true` may the API use the Nginx-overwritten `X-Real-IP` value. `GET /api/auth/session` uses `require_session`; `POST /api/auth/logout` and `POST /api/auth/change-password` require session plus CSRF but allow a forced-change session. Mount the router in `main.py`. During lifespan, build the auth engine/repository/service, create tables, run `bootstrap_default_admin()`, and clean expired sessions/throttle rows.

- [ ] **Step 7: Run auth service/router tests and health regression**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/auth/test_service.py apps/api/tests/auth/test_router.py apps/api/tests/test_health.py -v
```

Expected: all selected tests PASS.

- [ ] **Step 8: Commit Task 2**

```bash
git add apps/api/src/app/auth apps/api/src/app/main.py apps/api/tests/auth/test_service.py apps/api/tests/auth/test_router.py
git commit -m "feat: add administrator login sessions"
```

---

### Task 3: Administrator management, audit, and recovery CLI

**Files:**
- Create: `apps/api/src/app/auth/admin_router.py`
- Create: `apps/api/src/app/auth/recover.py`
- Modify: `apps/api/src/app/auth/schemas.py`
- Modify: `apps/api/src/app/auth/service.py`
- Modify: `apps/api/src/app/main.py`
- Test: `apps/api/tests/auth/test_service.py`
- Test: `apps/api/tests/auth/test_router.py`

**Interfaces:**
- Consumes: Task 2 `require_ready_context`, `require_ready_admin`, and `AuthContext`.
- Produces: administrator list/create/update/enable/disable/reset endpoints and audit listing.
- Produces: `PYTHONPATH=apps/api/src python -m app.auth.recover USERNAME` recovery entry point.

- [ ] **Step 1: Add failing lifecycle tests**

```python
def test_cannot_disable_self_or_last_enabled_admin(service, ready_context):
    with pytest.raises(AuthError, match="CANNOT_DISABLE_SELF"):
        service.disable_admin(ready_context, ready_context.admin.id, "127.0.0.1")
    second = service.create_admin(ready_context, "second", "Second@Pass2", "127.0.0.1")
    service.disable_admin(ready_context, second.id, "127.0.0.1")
    assert service.repository.get_admin(second.id).is_enabled is False


def test_reset_password_revokes_sessions_and_forces_change(service, ready_context):
    target = service.create_admin(ready_context, "second", "Second@Pass2", "127.0.0.1")
    target_login = service.login("second", "Second@Pass2", "127.0.0.2", "pytest")
    service.reset_password(ready_context, target.id, "Temporary@3", "127.0.0.1")
    with pytest.raises(AuthError, match="AUTHENTICATION_REQUIRED"):
        service.authenticate(target_login.session_token)
    assert service.repository.get_admin(target.id).must_change_password is True
```

- [ ] **Step 2: Run lifecycle tests and verify missing methods**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/auth/test_service.py -k 'disable or reset or create_admin' -v
```

Expected: FAIL because lifecycle methods are missing.

- [ ] **Step 3: Implement lifecycle service methods and API schemas**

Add these exact service methods:

- `list_admins(actor: AuthContext) -> list[AdminSummary]`: return all accounts without password fields.
- `create_admin(actor: AuthContext, username: str, temporary_password: str, ip_address: str | None) -> AdminSummary`: validate username/password, create an enabled forced-change account, and audit it.
- `rename_admin(actor: AuthContext, admin_id: str, username: str, ip_address: str | None) -> AdminSummary`: enforce normalized uniqueness and audit old/new usernames without secrets.
- `enable_admin(actor: AuthContext, admin_id: str, ip_address: str | None) -> AdminSummary`: enable an existing account and audit it.
- `disable_admin(actor: AuthContext, admin_id: str, ip_address: str | None) -> AdminSummary`: reject self/last-active targets, disable atomically, revoke sessions, and audit it.
- `reset_password(actor: AuthContext, admin_id: str, temporary_password: str, ip_address: str | None) -> AdminSummary`: validate/hash the temporary password, force change, revoke sessions, and audit it.
- `list_audit_events(actor: AuthContext, limit: int, cursor: str | None) -> AuditPage`: return newest-first cursor pagination.
- `recover_existing_admin(username: str, temporary_password: str) -> None`: reset only an existing account, enable it, force change, revoke sessions, and add a `system_recovery` audit event.

Every mutation records success and rejected attempts. Convert uniqueness, self-disable, last-admin, missing-admin, and password-policy failures into `USERNAME_ALREADY_EXISTS`, `CANNOT_DISABLE_SELF`, `LAST_ACTIVE_ADMIN`, `ADMIN_NOT_FOUND`, and `PASSWORD_POLICY_VIOLATION` respectively.

- [ ] **Step 4: Add failing administrator API tests**

Test `GET /api/admins`, `POST /api/admins`, `PATCH /api/admins/{id}`, enable, disable, reset, and audit. Use login + forced-change completion before calling management APIs. Assert all unsafe calls fail without `X-CSRF-Token`, and assert audit payloads do not contain submitted passwords.

- [ ] **Step 5: Implement and mount `admin_router`**

Use `Depends(require_ready_context)` so management operations retain both actor and session IDs after the ready-state check. Return `AdminSummary` without password hashes. Use request bodies:

```python
class AdminCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    temporary_password: str = Field(min_length=1, max_length=1024)


class AdminUpdateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)


class AdminResetPasswordRequest(BaseModel):
    temporary_password: str = Field(min_length=1, max_length=1024)
```

- [ ] **Step 6: Implement the controlled recovery command**

The module accepts only an existing username, prompts twice with `getpass`, validates policy, and calls `recover_existing_admin`. It must not print the password or hash:

```python
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("username")
    args = parser.parse_args()
    first = getpass.getpass("Temporary password: ")
    second = getpass.getpass("Repeat temporary password: ")
    if first != second:
        raise SystemExit("Passwords do not match")
    build_auth_service(get_settings()).recover_existing_admin(args.username, first)
    print(f"Password reset for existing administrator {args.username}; change required at next login.")
    return 0
```

- [ ] **Step 7: Run management tests**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/auth/test_service.py apps/api/tests/auth/test_router.py -v
```

Expected: all auth tests PASS.

- [ ] **Step 8: Commit Task 3**

```bash
git add apps/api/src/app/auth apps/api/src/app/main.py apps/api/tests/auth
git commit -m "feat: add administrator account management"
```

---

### Task 4: Protect build and review backend boundaries

**Files:**
- Modify: `apps/api/src/app/projects/router.py`
- Modify: `apps/api/src/app/jobs/router.py`
- Modify: `apps/api/src/app/extraction/router.py`
- Modify: `apps/api/src/app/review/router.py`
- Modify: `apps/api/src/app/review/service.py`
- Modify: `apps/api/tests/projects/test_router.py`
- Modify: `apps/api/tests/jobs/test_router.py`
- Modify: `apps/api/tests/review/test_router.py`
- Create: `apps/api/tests/auth/test_protected_routes.py`

**Interfaces:**
- Consumes: Task 2 `require_ready_admin` and Task 3 ready administrator fixtures.
- Produces: backend-enforced anonymous/forced-change/ready-session access matrix.
- Produces: review actions whose `reviewer` is the authenticated administrator username.

- [ ] **Step 1: Write the failing protected-route matrix**

Parameterize representative endpoints and expected anonymous status:

```python
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/projects/upload"),
        ("post", "/api/projects/p-1/attribute-jobs"),
        ("delete", "/api/projects/p-1"),
        ("get", "/api/model-profiles"),
        ("get", "/api/jobs/job-1"),
        ("post", "/api/jobs/job-1/cancel"),
        ("get", "/api/projects/p-1/review/items"),
        ("post", "/api/projects/p-1/review/items"),
    ],
)
def test_anonymous_management_routes_are_rejected(client, method, path):
    response = getattr(client, method)(path)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"
```

Add a second matrix proving `/api/projects`, `/api/projects/{id}`, `/api/ontology`, graph search/detail/evidence, story timeline, and `/api/ask` are not changed to `401`.

- [ ] **Step 2: Run the matrix and verify protected endpoints are still public**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/auth/test_protected_routes.py -v
```

Expected: FAIL for every management endpoint that has not yet declared the auth dependency.

- [ ] **Step 3: Add dependencies at the correct route granularity**

- Add `Depends(require_ready_admin)` to project upload, attribute-job creation, and project deletion only; keep list/get public.
- Add router-level `dependencies=[Depends(require_ready_admin)]` to jobs, model-profile, and review routers.
- Ensure unsafe routes also pass through `require_session` CSRF validation. Implement `require_ready_admin` as a dependency of `require_session`, so declaring it once enforces both rules.
- Do not add authorization checks to the Worker or Neo4j repositories.

- [ ] **Step 4: Bind review actions to the authenticated username**

Change both `ReviewService.apply_action` and `ReviewService.merge_entities` to accept `reviewer: str` and persist it in `ReviewAction`. `merge_entities` passes the reviewer through to its internal `apply_action` call. Route usage must be explicit:

```python
def apply_action(
    project_id: str,
    item_id: str,
    request: ReviewActionRequest,
    admin: AdminAccount = Depends(require_ready_admin),
):
    return service().apply_action(
        project_id,
        item_id,
        request,
        reviewer=admin.username,
    )
```

- [ ] **Step 5: Update existing router unit tests with explicit ready-admin overrides**

For isolated `FastAPI()` tests, override `require_ready_admin` with a fake enabled account and provide a CSRF-aware authenticated dependency. Do not make the production dependency permissive for tests. Add one anonymous assertion per router before applying overrides.

- [ ] **Step 6: Run all backend route tests**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/projects/test_router.py apps/api/tests/jobs/test_router.py apps/api/tests/review/test_router.py apps/api/tests/auth/test_protected_routes.py -v
```

Expected: all selected tests PASS.

- [ ] **Step 7: Commit Task 4**

```bash
git add apps/api/src/app/projects/router.py apps/api/src/app/jobs/router.py apps/api/src/app/extraction/router.py apps/api/src/app/review/router.py apps/api/src/app/review/service.py apps/api/tests
git commit -m "feat: protect build and review APIs"
```

---

### Task 5: Frontend API authentication infrastructure

**Files:**
- Create: `apps/web/src/app/AuthContext.tsx`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/App.tsx`
- Test: `apps/web/src/app/AuthContext.test.tsx`
- Modify: `apps/web/src/test/setup.ts`

**Interfaces:**
- Produces: `ApiError(status: number, code: string, detail: unknown)`.
- Produces: `setApiAuthHooks({ getCsrfToken, onAuthenticationRequired, onPasswordChangeRequired })`.
- Produces: `useAuth()` with `status`, `admin`, `mustChangePassword`, `login`, `logout`, `changePassword`, and `refreshSession`.

- [ ] **Step 1: Write failing API client tests**

Assert that unsafe requests receive CSRF, FormData does not receive JSON content type, and structured failures become `ApiError`:

```typescript
it('adds csrf only to unsafe requests and preserves structured API errors', async () => {
  setApiAuthHooks({ getCsrfToken: () => 'csrf-1' })
  const fetchMock = vi.fn(async () => new Response(
    JSON.stringify({ detail: { code: 'PASSWORD_CHANGE_REQUIRED' } }),
    { status: 403, headers: { 'Content-Type': 'application/json' } },
  ))
  vi.stubGlobal('fetch', fetchMock)
  await expect(apiFetch('/api/admins', { method: 'POST', body: '{}' })).rejects.toMatchObject({
    status: 403,
    code: 'PASSWORD_CHANGE_REQUIRED',
  })
  expect(fetchMock).toHaveBeenCalledWith('/api/admins', expect.objectContaining({
    credentials: 'same-origin',
    headers: expect.any(Headers),
  }))
  expect((fetchMock.mock.calls[0][1]?.headers as Headers).get('X-CSRF-Token')).toBe('csrf-1')
})
```

- [ ] **Step 2: Run the client/context tests and verify missing APIs**

Run:

```bash
npm --prefix apps/web test -- --run src/app/AuthContext.test.tsx
```

Expected: FAIL because the context and auth hooks do not exist.

- [ ] **Step 3: Implement typed errors and auth hooks in `api/client.ts`**

Parse `{ detail: { code: string } }` plus additional detail fields safely, preserve AbortError, always set `credentials: 'same-origin'`, and attach `X-CSRF-Token` only for `POST`, `PUT`, `PATCH`, and `DELETE`. On `401`, notify `onAuthenticationRequired`; on `403 PASSWORD_CHANGE_REQUIRED`, notify `onPasswordChangeRequired`. Never automatically replay unsafe requests.

- [ ] **Step 4: Implement `AuthProvider` and cross-tab synchronization**

Use this state contract:

```typescript
export type AuthStatus = 'loading' | 'anonymous' | 'password-change-required' | 'ready'

export type AdminSummary = {
  id: string
  username: string
  is_enabled: boolean
  must_change_password: boolean
  created_at: string
  updated_at: string
}

export type AuthValue = {
  status: AuthStatus
  admin?: AdminSummary
  mustChangePassword: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>
  refreshSession: () => Promise<void>
}
```

On mount, call `/api/auth/session`; treat `401` as anonymous without showing a global error. Keep CSRF in a `useRef`, configure API hooks, and clear it on logout/401. Publish `login`, `logout`, and `session-invalidated` messages through `BroadcastChannel('tspw-auth')`; receiving tabs call `refreshSession()`.

- [ ] **Step 5: Wrap the application in `AuthProvider`**

Provider order must keep routing available to auth redirects:

```tsx
<BrowserRouter>
  <AuthProvider>
    <ProjectProvider>
      <AppShell />
    </ProjectProvider>
  </AuthProvider>
</BrowserRouter>
```

Extract the current header/main markup into `AppShell` in the same file; do not change navigation visibility until Task 6.

- [ ] **Step 6: Run frontend auth tests, typecheck, and current App tests**

Run:

```bash
npm --prefix apps/web test -- --run src/app/AuthContext.test.tsx src/App.test.tsx
npm --prefix apps/web run typecheck
```

Expected: all selected tests and typecheck PASS.

- [ ] **Step 7: Commit Task 5**

```bash
git add apps/web/src/api/client.ts apps/web/src/app/AuthContext.tsx apps/web/src/app/AuthContext.test.tsx apps/web/src/App.tsx apps/web/src/test/setup.ts
git commit -m "feat: add frontend administrator session state"
```

---

### Task 6: Login, forced password change, protected routes, and navigation

**Files:**
- Create: `apps/web/src/app/ProtectedRoute.tsx`
- Create: `apps/web/src/features/auth/LoginPage.tsx`
- Create: `apps/web/src/features/auth/ChangePasswordPage.tsx`
- Create: `apps/web/src/features/auth/AuthPages.test.tsx`
- Modify: `apps/web/src/app/router.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/App.test.tsx`
- Modify: `apps/web/src/styles/vercel.css`

**Interfaces:**
- Consumes: Task 5 `useAuth()`.
- Produces: public `/login`, session-only `/change-password`, and ready-admin `/admin`, `/build`, `/review` route behavior.
- Produces: conditional header links and administrator account menu.

- [ ] **Step 1: Write failing route and navigation tests**

Cover three explicit states:

```typescript
it('hides management navigation for anonymous visitors', async () => {
  renderAppWithSession(anonymousSession())
  expect(await screen.findByRole('link', { name: '管理员登录' })).toBeVisible()
  expect(screen.queryByRole('link', { name: '管理员' })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: '构建' })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: '审核' })).not.toBeInTheDocument()
})


it('redirects a direct build visit to login and returns after authentication', async () => {
  window.history.pushState({}, '', '/build?project=project-1')
  const user = userEvent.setup()
  renderAppWithSession(anonymousSession())
  await screen.findByRole('heading', { name: '管理员登录' })
  await user.type(screen.getByLabelText('管理员账号'), 'admin')
  await user.type(screen.getByLabelText('密码'), 'Better@Pass2')
  await user.click(screen.getByRole('button', { name: '登录' }))
  await screen.findByRole('heading', { name: '从文本，生长出图谱' })
  expect(window.location.pathname).toBe('/build')
  expect(window.location.search).toBe('?project=project-1')
})
```

Also test that `returnTo=https://evil.example` is discarded and a forced-change session always reaches `/change-password`.

- [ ] **Step 2: Run auth page tests and verify routes are missing**

Run:

```bash
npm --prefix apps/web test -- --run src/features/auth/AuthPages.test.tsx src/App.test.tsx
```

Expected: FAIL because login/change pages and guards are not implemented.

- [ ] **Step 3: Implement safe `returnTo` and `ProtectedRoute`**

Accept only strings beginning with one `/` and reject `//`, protocol-like values, and login/change-password loops:

```typescript
export function safeReturnTo(value: string | null): string | undefined {
  if (!value || !value.startsWith('/') || value.startsWith('//')) return undefined
  const parsed = new URL(value, window.location.origin)
  if (parsed.origin !== window.location.origin) return undefined
  if (parsed.pathname === '/login' || parsed.pathname === '/change-password') return undefined
  return `${parsed.pathname}${parsed.search}${parsed.hash}`
}
```

The guard renders a loading state while auth is loading. It redirects anonymous users to `/login?returnTo=${encodeURIComponent(pathname + search)}` and forced-change users to `/change-password?returnTo=${encodeURIComponent(pathname + search)}`. It renders children only for `ready`.

- [ ] **Step 4: Implement login and change-password pages**

Login uses labeled username/password inputs, a generic invalid-credential message, and lock countdown from `retry_after_seconds`. Change password shows all five password rules, requires matching confirmation, and submits current/new password. After success, navigate to safe `returnTo` or `/admin`.

- [ ] **Step 5: Update router and header**

Routes:

```tsx
<Route path="/login" element={<LoginPage />} />
<Route path="/change-password" element={<ChangePasswordPage />} />
<Route path="/admin" element={<ProtectedRoute><AdminPage /></ProtectedRoute>} />
<Route path="/build" element={<ProtectedRoute><BuildPage /></ProtectedRoute>} />
<Route path="/review" element={<ProtectedRoute><ReviewPage /></ProtectedRoute>} />
```

Anonymous nav shows guide/ontology/graph/story/ask plus “管理员登录”. Ready nav additionally shows admin/build/review and replaces login with an account menu containing “修改密码” and “退出登录”. Forced-change state shows only the account identity and logout, not management links.

- [ ] **Step 6: Style auth pages and account menu with existing tokens**

Use a centered `max-width: 440px` elevated white card, `var(--ds-shadow-medium)`, 12px card radius, 24px/32px spacing, existing 40px controls, and existing focus rings. Do not introduce gradients, large status fills, or font weights above 600.

- [ ] **Step 7: Run frontend tests and build**

Run:

```bash
npm --prefix apps/web test -- --run src/features/auth/AuthPages.test.tsx src/App.test.tsx
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

Expected: tests, typecheck, and production build PASS.

- [ ] **Step 8: Commit Task 6**

```bash
git add apps/web/src/app/ProtectedRoute.tsx apps/web/src/features/auth apps/web/src/app/router.tsx apps/web/src/App.tsx apps/web/src/App.test.tsx apps/web/src/styles/vercel.css
git commit -m "feat: add protected administrator navigation"
```

---

### Task 7: Administrator management UI and graph review visibility

**Files:**
- Create: `apps/web/src/features/admin/AdminPage.tsx`
- Create: `apps/web/src/features/admin/AdminDialog.tsx`
- Create: `apps/web/src/features/admin/AdminPage.test.tsx`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/features/graph/GraphPage.tsx`
- Modify: `apps/web/src/features/graph/EntityPanel.tsx`
- Modify: `apps/web/src/features/graph/GraphPage.test.tsx`
- Modify: `apps/web/src/styles/base.css`
- Modify: `apps/web/src/styles/vercel.css`

**Interfaces:**
- Consumes: ready session and Task 3 administrator APIs.
- Produces: administrator list, audit table, create/rename/reset/enable/disable dialogs.
- Produces: anonymous graph entity details with no “加入审核” button.

- [ ] **Step 1: Add administrator API types and failing page tests**

Add `AdminSummary`, `AdminAuditEvent`, and paged audit response types to `api/client.ts`. Tests must assert list rendering, disabled self/last-active controls, temporary password validation, confirmation text, and refresh after mutation:

```typescript
it('explains why the current and last active administrator cannot be disabled', async () => {
  renderAdminPage({
    currentAdminId: 'admin-1',
    admins: [{ id: 'admin-1', username: 'admin', is_enabled: true, must_change_password: false, created_at: '', updated_at: '' }],
  })
  const disable = await screen.findByRole('button', { name: '停用 admin' })
  expect(disable).toBeDisabled()
  expect(screen.getByText('不能停用当前账号；系统必须保留至少一个启用管理员')).toBeVisible()
})
```

- [ ] **Step 2: Run admin UI tests and verify missing components**

Run:

```bash
npm --prefix apps/web test -- --run src/features/admin/AdminPage.test.tsx
```

Expected: FAIL because the administrator components do not exist.

- [ ] **Step 3: Implement `AdminPage` data flow**

Load `/api/admins` and `/api/admin-audit-events?limit=50` in parallel. Render username, enabled status dot, forced-change status, and updated timestamp. Provide actions to create, rename, reset password, enable, and disable. Keep errors local to the management workspace and refetch both administrators and audit after successful mutation.

- [ ] **Step 4: Implement focused dialogs and destructive confirmations**

`AdminDialog` supports one mode at a time. Create/reset requires the same five visible password rules and confirmation. Disable confirmation says that all target sessions will end. Reset confirmation says the temporary password forces a change and revokes sessions. The dialog sends only the API body for its mode and never renders submitted passwords after success.

- [ ] **Step 5: Add failing graph visibility tests**

Update Graph tests with explicit auth state:

```typescript
it('does not render add-to-review for anonymous graph visitors', async () => {
  renderGraphWithAuth('anonymous')
  await openEntityWithEvidence()
  expect(screen.queryByRole('button', { name: '加入审核' })).not.toBeInTheDocument()
})


it('renders add-to-review for ready administrators', async () => {
  renderGraphWithAuth('ready')
  await openEntityWithEvidence()
  expect(screen.getByRole('button', { name: '加入审核' })).toBeVisible()
})
```

- [ ] **Step 6: Gate graph review actions in both parent and child**

`GraphPage` reads `useAuth()` and passes `onReviewFact={status === 'ready' ? reviewFact : undefined}`. `EntityPanel` must conditionally render the button itself:

```tsx
{onReviewFact && (
  <button type="button" onClick={() => onReviewFact(fact.id)}>加入审核</button>
)}
```

This prevents an anonymous no-op button and keeps the backend as the final enforcement layer.

- [ ] **Step 7: Style administrator tables and dialogs**

Use the existing 1200px page width, white elevated surfaces, shadow-as-border, 6px controls, 12px cards, 4px spacing multiples, monochrome content, blue focus, and 10px status dots. On widths below 768px, stack the list and audit surface and make dialogs fit `calc(100vw - 32px)`.

- [ ] **Step 8: Run admin and graph tests plus frontend verification**

Run:

```bash
npm --prefix apps/web test -- --run src/features/admin/AdminPage.test.tsx src/features/graph/GraphPage.test.tsx
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

Expected: tests, typecheck, and build PASS.

- [ ] **Step 9: Commit Task 7**

```bash
git add apps/web/src/features/admin apps/web/src/features/graph apps/web/src/api/client.ts apps/web/src/styles
git commit -m "feat: add administrator management workspace"
```

---

### Task 8: Deployment configuration, recovery documentation, and end-to-end verification

**Files:**
- Modify: `compose.yaml`
- Modify: `.env.example`
- Modify: `apps/web/nginx.conf`
- Modify: `README.md`
- Modify: `docs/deployment-docker-azure-openai.md`
- Create: `tests/e2e/auth.setup.ts`
- Create: `tests/e2e/admin-auth.spec.ts`
- Modify: `tests/e2e/playwright.config.ts`
- Modify: `tests/e2e/online-build.spec.ts`
- Modify: `tests/e2e/review.spec.ts`

**Interfaces:**
- Consumes: all backend and frontend authentication behavior.
- Produces: repeatable Docker settings, documented recovery, authenticated browser state, and release-quality verification evidence.

- [ ] **Step 1: Add authentication environment variables without exposing them to Worker**

Keep the existing shared `app-env` for SQLite, Neo4j, uploads, and model profiles. Add these only to the `api.environment` block:

```yaml
AUTH_BOOTSTRAP_USERNAME: ${AUTH_BOOTSTRAP_USERNAME:-admin}
AUTH_BOOTSTRAP_PASSWORD: ${AUTH_BOOTSTRAP_PASSWORD:-Pass@word1}
AUTH_COOKIE_SECURE: ${AUTH_COOKIE_SECURE:-false}
AUTH_SESSION_IDLE_SECONDS: ${AUTH_SESSION_IDLE_SECONDS:-28800}
AUTH_LOGIN_MAX_FAILURES: ${AUTH_LOGIN_MAX_FAILURES:-5}
AUTH_LOGIN_LOCK_SECONDS: ${AUTH_LOGIN_LOCK_SECONDS:-900}
AUTH_TRUST_FORWARDED_IP: ${AUTH_TRUST_FORWARDED_IP:-true}
```

Do not add bootstrap credentials to `worker.environment`.

In `apps/web/nginx.conf`, overwrite rather than append forwarded identity headers:

```nginx
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Real-IP $remote_addr;
```

The Compose API is not published directly, so it can trust this Nginx-overwritten value. Local direct API development keeps `AUTH_TRUST_FORWARDED_IP=false`.

- [ ] **Step 2: Document first login, HTTPS, lockout, and recovery**

Update `.env.example` with non-secret explanations. In the deployment manual include:

```bash
sudo docker compose exec api python -m app.auth.recover admin
sudo docker compose restart api
```

Explain that recovery prompts interactively, only resets an existing account, revokes its sessions, and forces password change. State that `AUTH_COOKIE_SECURE=true` is required behind HTTPS and must remain `false` only for intentional HTTP development deployments.

- [ ] **Step 3: Add repeatable Playwright authentication setup**

The setup tries `E2E_ADMIN_PASSWORD` first and `E2E_ADMIN_INITIAL_PASSWORD` second, handles `/change-password`, then writes `.auth/admin.json`. Use environment defaults only for local Docker verification:

```typescript
const username = process.env.E2E_ADMIN_USERNAME ?? 'admin'
const currentPassword = process.env.E2E_ADMIN_PASSWORD ?? 'E2eAdmin@2'
const initialPassword = process.env.E2E_ADMIN_INITIAL_PASSWORD ?? 'Pass@word1'

export default async function globalSetup(config: FullConfig) {
  const browser = await chromium.launch()
  const page = await browser.newPage({ baseURL: config.projects[0].use.baseURL as string })
  for (const password of [currentPassword, initialPassword]) {
    await page.goto('/login')
    await page.getByLabel('管理员账号').fill(username)
    await page.getByLabel('密码').fill(password)
    await page.getByRole('button', { name: '登录' }).click()
    if (!page.url().includes('/login')) break
  }
  if (page.url().includes('/change-password')) {
    await page.getByLabel('当前密码').fill(initialPassword)
    await page.getByLabel('新密码', { exact: true }).fill(currentPassword)
    await page.getByLabel('确认新密码').fill(currentPassword)
    await page.getByRole('button', { name: '修改密码' }).click()
  }
  await page.context().storageState({ path: '.auth/admin.json' })
  await browser.close()
}
```

Configure `globalSetup` and use the storage state only in protected build/review/admin specs. Keep the public visitor spec anonymous.

- [ ] **Step 4: Add end-to-end assertions**

`admin-auth.spec.ts` must prove:

- anonymous header hides administrator/build/review;
- direct `/build` redirects to login with a safe return target;
- authenticated header shows protected links and account menu;
- an administrator can create a temporary account and the row shows “需要改密”;
- graph “加入审核” is absent in an anonymous context and visible with admin storage state;
- logout in one page makes a second page anonymous after the broadcast/session refresh.

- [ ] **Step 5: Run focused backend and frontend suites**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/auth apps/api/tests/projects/test_router.py apps/api/tests/jobs/test_router.py apps/api/tests/review/test_router.py -v
npm --prefix apps/web test -- --run
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

Expected: all backend tests, frontend tests, typecheck, and build PASS.

- [ ] **Step 6: Run the complete repository verification gate**

Run:

```bash
make verify
```

Expected: Docker Compose becomes healthy; Neo4j-backed API tests, all frontend tests, typecheck, production build, graph source validation, and Playwright tests PASS. If the local novel source is elsewhere, run `SOURCE_PATH=/absolute/path/to/笑傲江湖.txt make verify`.

- [ ] **Step 7: Perform manual security smoke checks against Docker**

Run:

```bash
curl -i http://127.0.0.1:5173/api/admins
curl -i http://127.0.0.1:5173/api/projects
sudo docker compose exec worker printenv AUTH_BOOTSTRAP_PASSWORD
sudo docker compose exec api printenv AUTH_SESSION_IDLE_SECONDS
```

Expected:

- `/api/admins` returns `401 AUTHENTICATION_REQUIRED` without a Cookie.
- `/api/projects` returns `200` anonymously.
- Worker prints no bootstrap password value.
- API prints `28800` unless explicitly overridden.

- [ ] **Step 8: Commit Task 8**

```bash
git add compose.yaml .env.example apps/web/nginx.conf README.md docs/deployment-docker-azure-openai.md tests/e2e
git commit -m "docs: add administrator deployment workflow"
```

---

## Final Review Checklist

- [ ] Confirm `git diff origin/master..HEAD --check` reports no whitespace errors.
- [ ] Confirm `rg -n "Pass@word1|AUTH_BOOTSTRAP_PASSWORD" apps/api/src apps/web/src` finds only the intentional settings default and tests, never a rendered frontend credential.
- [ ] Confirm `rg -n "localStorage|sessionStorage" apps/web/src` finds no authentication credential storage.
- [ ] Confirm every unsafe protected request carries `X-CSRF-Token` and no unsafe request is automatically retried.
- [ ] Confirm anonymous users can still open guide, ontology, graph, story, and QA.
- [ ] Confirm build, review, admin, project mutation, job, model profile, and add-to-review APIs reject anonymous requests.
- [ ] Confirm the final branch contains frequent task commits and no unrelated files.
