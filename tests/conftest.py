"""
ALM Test Suite — pytest configuration and shared fixtures.

All tests use SQLite in-memory (aiosqlite) instead of PostgreSQL so the suite
runs in CI without any running services.  External services (Redis, RabbitMQ,
Java parser, LLM APIs) are fully mocked.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import JSON
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Patch PostgreSQL-only types → SQLite-compatible equivalents BEFORE any
# model imports so that create_all() works against an in-memory SQLite DB.
# ---------------------------------------------------------------------------
import sqlalchemy
from sqlalchemy.dialects import postgresql as _pg

class _ArrayAsJson(JSON):
    """Drop-in replacement for ARRAY that serialises as JSON in SQLite."""
    def __init__(self, item_type=None, *args, **kwargs):  # noqa: ARG002
        super().__init__()

_pg.ARRAY = _ArrayAsJson  # type: ignore[attr-defined]
sqlalchemy.ARRAY = _ArrayAsJson  # type: ignore[attr-defined]

# Also patch JSONB → JSON and UUID → String for full SQLite compat
from sqlalchemy import String
_pg.JSONB = JSON  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Test database URL (SQLite in-memory — no Postgres required)
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Database fixtures (session-scoped engine, function-scoped session)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create a shared in-memory SQLite engine for the entire test session."""
    engine = create_async_engine(TEST_DB_URL, echo=False)

    # Import Base so that all ORM metadata is registered before create_all.
    from app.core.database import Base  # noqa: PLC0415

    # Import every model module to ensure their tables are registered.
    from app.models import job, ucg, smell  # noqa: F401, PLC0415
    try:
        from app.models import plan  # noqa: F401, PLC0415
    except ImportError:
        pass
    try:
        from app.models import patch  # noqa: F401, PLC0415
    except ImportError:
        pass
    try:
        from app.models import api_key  # noqa: F401, PLC0415
    except ImportError:
        pass
    try:
        from app.models import vcs  # noqa: F401, PLC0415
    except ImportError:
        pass

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    """
    Provide a function-scoped async DB session that rolls back after each test.

    This keeps tests isolated even when they write to the database.
    """
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# FastAPI test client with dependency overrides
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(db_session):
    """
    AsyncClient wired to the FastAPI app with:
      - DB session overridden with the test SQLite session
      - API key authentication bypassed (returns a mock key with all scopes)
    """
    from app.main import app  # noqa: PLC0415

    # Import the dependency callables we want to override.
    try:
        from app.core.database import get_db  # noqa: PLC0415
    except ImportError:
        get_db = None

    try:
        from app.core.security import get_current_api_key  # noqa: PLC0415
    except ImportError:
        try:
            from app.api.deps import get_current_api_key  # noqa: PLC0415
        except ImportError:
            get_current_api_key = None

    async def override_db():
        yield db_session

    mock_key = MagicMock(scopes=["read", "write", "admin"])

    async def override_auth():
        return mock_key

    async def override_scope(_key=None):
        return mock_key

    if get_db:
        app.dependency_overrides[get_db] = override_db
    if get_current_api_key:
        app.dependency_overrides[get_current_api_key] = override_auth

    # Override require_scope factory — override each closure it returns
    try:
        from app.core.security import require_scope  # noqa: PLC0415
        for scope in ("read", "write", "admin"):
            dep = require_scope(scope)
            app.dependency_overrides[dep] = override_scope
    except (ImportError, AttributeError):
        pass

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# LLM mock fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm():
    """Return a fully mocked async LLM provider."""
    from app.services.llm.base import CompletionResult, EmbeddingResult  # noqa: PLC0415

    llm = AsyncMock()
    llm.complete.return_value = CompletionResult(
        content="Mock LLM response for testing",
        model="stub",
        input_tokens=10,
        output_tokens=20,
        stop_reason="end_turn",
    )
    llm.embed.return_value = EmbeddingResult(
        embeddings=[[0.1] * 1536],
        model="stub",
        total_tokens=5,
    )
    return llm


# ---------------------------------------------------------------------------
# Sample repository fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_java_repo(tmp_path):
    """Create a sample Java repository with a god-class and a controller."""
    src = tmp_path / "src" / "main" / "java" / "com" / "example"
    src.mkdir(parents=True)

    # OrderService: has 11 methods -> god class candidate
    (src / "OrderService.java").write_text(
        """
package com.example;

import java.sql.Connection;
import java.sql.PreparedStatement;

public class OrderService {
    private Connection conn;

    public void createOrder() {}
    public void updateOrder() {}
    public void deleteOrder() {}
    public void getOrder() {}
    public void listOrders() {}
    public void validateOrder() {}
    public void processPayment() {}
    public void sendNotification() {}
    public void updateInventory() {}
    public void generateReport() {}
    public void exportOrder() {}

    public void saveToDb(String sql) throws Exception {
        PreparedStatement ps = conn.prepareStatement(sql);
        ps.execute();
    }
}
"""
    )

    # UserController: simple controller, references OrderService
    (src / "UserController.java").write_text(
        """
package com.example;

public class UserController {
    private OrderService orderService;

    public UserController(OrderService os) {
        this.orderService = os;
    }

    public void handleRequest() {
        orderService.createOrder();
    }
}
"""
    )

    # pom.xml so the language detector can spot Spring
    (tmp_path / "pom.xml").write_text(
        """
<project>
  <groupId>com.example</groupId>
  <artifactId>demo</artifactId>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter</artifactId>
    </dependency>
  </dependencies>
</project>
"""
    )
    return tmp_path


@pytest.fixture
def sample_python_repo(tmp_path):
    """Create a sample Python repository with a User model and a service module."""
    # User class: many getters/setters -> anemic domain model candidate
    (tmp_path / "models.py").write_text(
        """
class User:
    def __init__(self, name, email):
        self.name = name
        self.email = email

    def get_name(self): return self.name
    def set_name(self, v): self.name = v
    def get_email(self): return self.email
    def set_email(self, v): self.email = v
    def is_active(self): return True
    def is_admin(self): return False


class BigClass:
    pass
"""
    )

    (tmp_path / "services.py").write_text(
        """
from models import User


def process_user(user: User):
    return user.get_name()


def validate_email(email: str) -> bool:
    return "@" in email
"""
    )
    return tmp_path


@pytest.fixture
def sample_mixed_repo(tmp_path):
    """Create a repo with both Python and TypeScript files."""
    (tmp_path / "app.py").write_text("def main(): pass\n")
    ts_src = tmp_path / "src"
    ts_src.mkdir()
    (ts_src / "index.ts").write_text("export const VERSION = '1.0.0';\n")
    (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {"strict": true}}')
    return tmp_path
