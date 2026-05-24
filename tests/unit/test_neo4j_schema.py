from unittest.mock import AsyncMock, MagicMock, patch


async def test_init_schema_runs_constraint_query() -> None:
    from core.db.neo4j import init_schema

    mock_session = AsyncMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("core.db.neo4j._driver", mock_driver):
        await init_schema()

    mock_session.run.assert_called_once()
    cypher = mock_session.run.call_args[0][0]
    assert "CREATE CONSTRAINT" in cypher
    assert "FailureSignature" in cypher


async def test_init_schema_idempotent() -> None:
    from core.db.neo4j import init_schema

    mock_session = AsyncMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("core.db.neo4j._driver", mock_driver):
        await init_schema()
        await init_schema()

    assert mock_session.run.call_count == 2
