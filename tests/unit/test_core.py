import logging

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.constants import AgentAction, Environment
from app.core.exceptions import RetrievalError, RAGApplicationError
from app.core.logging import configure_logging, get_logger


def test_settings_reject_invalid_chunk_relationship():
    with pytest.raises(ValidationError):
        Settings(chunk_size=100, chunk_overlap=100)


def test_enums_are_string_like():
    assert Environment.TESTING == 'testing'
    assert AgentAction.VERIFY == 'verify'


def test_exception_hierarchy():
    assert issubclass(RetrievalError, RAGApplicationError)


def test_logging_configuration(caplog):
    configure_logging(debug=True)
    logger = get_logger('test.core')
    with caplog.at_level(logging.DEBUG):
        logger.debug('debug-message')
    assert 'debug-message' in caplog.text
