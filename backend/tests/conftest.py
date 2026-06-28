import pytest
import os
import sys
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Setup python path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import Base, get_db
from app.main import app
from app.core.cache import cache_manager
from app.models.user import User
from app.models.user_profile import UserProfile

# Use SQLite in-memory database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False)

# Keep a single connection alive for the entire test session to preserve the in-memory SQLite database
connection = engine.connect()

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    # Create all tables in the SQLite database using the shared connection
    Base.metadata.create_all(bind=connection)
    yield
    Base.metadata.drop_all(bind=connection)
    connection.close()

@pytest.fixture
def db() -> Generator[Session, None, None]:
    # Bind session to the shared connection
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    
    # Clean all tables to ensure test isolation
    for table in reversed(Base.metadata.sorted_tables):
        connection.execute(table.delete())
    connection.commit()

@pytest.fixture(autouse=True)
def override_db_dependency(db: Session):
    # Dependency override get_db
    def _get_db_override():
        try:
            yield db
        finally:
            pass
    app.dependency_overrides[get_db] = _get_db_override
    yield
    app.dependency_overrides.pop(get_db, None)

@pytest.fixture(autouse=True)
def reset_cache():
    # Ensure cache manager doesn't hit Redis during tests and starts clean
    cache_manager.redis_client = None
    cache_manager.in_memory_db.clear()
    yield
    cache_manager.in_memory_db.clear()

@pytest.fixture
def test_user(db: Session) -> User:
    # Pre-seed a test user
    user = User(
        id="test-user-uuid",
        email="testuser@niveshiq.com",
        is_active=True,
        is_verified=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    profile = UserProfile(
        user_id=user.id,
        full_name="Test User",
        risk_appetite="MODERATE",
        time_horizon="MEDIUM_TERM",
        investment_goal="BALANCED"
    )
    db.add(profile)
    db.commit()
    return user

@pytest.fixture
def guest_user(db: Session) -> User:
    # Pre-seed a guest user
    user = User(
        id="guest-user-uuid",
        email="guest_user@niveshiq.guest",
        is_active=True,
        is_verified=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    profile = UserProfile(
        user_id=user.id,
        full_name="Guest User",
        risk_appetite="LOW",
        time_horizon="SHORT_TERM",
        investment_goal="BALANCED"
    )
    db.add(profile)
    db.commit()
    return user

@pytest.fixture
def auth_headers(test_user: User) -> dict[str, str]:
    # We pass user email as token since get_current_user queries by token value as email
    return {"Authorization": f"Bearer {test_user.email}"}

@pytest.fixture
def guest_auth_headers(guest_user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {guest_user.email}"}

@pytest.fixture
def client() -> TestClient:
    return TestClient(app)

@pytest.fixture(autouse=True)
def mock_llm_models(mocker):
    # Mock LLM calls inside core.llm to prevent network dependency
    mock_response = mocker.MagicMock()
    mock_response.content = '{"answer": "Standard direct response", "evidence": [], "next_steps": [], "plan_draft": null}'
    
    # Mock ChatGoogleGenerativeAI invoke methods
    mock_flash_lite = mocker.patch("app.core.llm.flash_lite_model")
    mock_flash_lite.invoke.return_value = mock_response
    
    mock_flash = mocker.patch("app.core.llm.flash_model")
    mock_flash.invoke.return_value = mock_response
    
    mock_pro = mocker.patch("app.core.llm.pro_model")
    mock_pro.invoke.return_value = mock_response
    
    return {
        "flash_lite": mock_flash_lite,
        "flash": mock_flash,
        "pro": mock_pro
    }
