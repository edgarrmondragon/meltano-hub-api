"""Test schema validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hub_api.schemas import meltano


def test_supported_python_versions_valid() -> None:
    """Test that valid Python version patterns are accepted."""
    valid_versions = [
        ["3.8", "3.9", "3.10"],
        ["3.11", "3.12"],
        ["3.8"],
        ["3.10", "3.11", "3.12", "3.13"],
    ]

    for versions in valid_versions:
        plugin = meltano.Plugin.model_validate({
            "name": "test-plugin",
            "namespace": "test_namespace",
            "variant": "test",
            "repo": "https://github.com/test/test",
            "supported_python_versions": versions,
        })
        assert plugin.supported_python_versions == versions


def test_supported_python_versions_invalid_python2() -> None:
    """Test that Python 2.x versions are rejected."""
    with pytest.raises(ValidationError, match=r"String should match pattern"):
        meltano.Plugin.model_validate({
            "name": "test-plugin",
            "namespace": "test_namespace",
            "variant": "test",
            "repo": "https://github.com/test/test",
            "supported_python_versions": ["2.7"],
        })


def test_supported_python_versions_invalid_no_minor() -> None:
    """Test that versions without minor version are rejected."""
    with pytest.raises(ValidationError, match=r"String should match pattern"):
        meltano.Plugin.model_validate({
            "name": "test-plugin",
            "namespace": "test_namespace",
            "variant": "test",
            "repo": "https://github.com/test/test",
            "supported_python_versions": ["3"],
        })


def test_supported_python_versions_invalid_text() -> None:
    """Test that text versions are rejected."""
    with pytest.raises(ValidationError, match=r"String should match pattern"):
        meltano.Plugin.model_validate({
            "name": "test-plugin",
            "namespace": "test_namespace",
            "variant": "test",
            "repo": "https://github.com/test/test",
            "supported_python_versions": ["python3.9"],
        })


def test_supported_python_versions_invalid_placeholder() -> None:
    """Test that placeholder patterns like '3.x' are rejected."""
    with pytest.raises(ValidationError, match=r"String should match pattern"):
        meltano.Plugin.model_validate({
            "name": "test-plugin",
            "namespace": "test_namespace",
            "variant": "test",
            "repo": "https://github.com/test/test",
            "supported_python_versions": ["3.x"],
        })


def test_supported_python_versions_mixed_valid_invalid() -> None:
    """Test that a list with any invalid version is rejected."""
    with pytest.raises(ValidationError, match=r"String should match pattern"):
        meltano.Plugin.model_validate({
            "name": "test-plugin",
            "namespace": "test_namespace",
            "variant": "test",
            "repo": "https://github.com/test/test",
            "supported_python_versions": ["3.8", "3.9", "2.7"],
        })


def test_supported_python_versions_none() -> None:
    """Test that None is accepted for optional field."""
    plugin = meltano.Plugin.model_validate({
        "name": "test-plugin",
        "namespace": "test_namespace",
        "variant": "test",
        "repo": "https://github.com/test/test",
        "supported_python_versions": None,
    })
    assert plugin.supported_python_versions is None


def test_supported_python_versions_empty_list() -> None:
    """Test that an empty list is accepted."""
    plugin = meltano.Plugin.model_validate({
        "name": "test-plugin",
        "namespace": "test_namespace",
        "variant": "test",
        "repo": "https://github.com/test/test",
        "supported_python_versions": [],
    })
    assert plugin.supported_python_versions == []


def test_supported_python_versions_on_extractor_subclass() -> None:
    """Test that validation works on Plugin subclasses."""
    # Valid case
    extractor = meltano.Extractor.model_validate({
        "name": "tap-test",
        "namespace": "tap_test",
        "variant": "test",
        "repo": "https://github.com/test/tap-test",
        "capabilities": [],
        "supported_python_versions": ["3.9", "3.10", "3.11"],
    })
    assert extractor.supported_python_versions == ["3.9", "3.10", "3.11"]

    # Invalid case
    with pytest.raises(ValidationError, match=r"String should match pattern"):
        meltano.Extractor.model_validate({
            "name": "tap-test",
            "namespace": "tap_test",
            "variant": "test",
            "repo": "https://github.com/test/tap-test",
            "capabilities": [],
            "supported_python_versions": ["3.x"],
        })
