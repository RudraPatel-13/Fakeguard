"""Test isolation: keep the generated ML artifact and network mode out of the repo/environment."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="fakeguard_models_")
os.environ.setdefault("FAKEGUARD_MODEL_PATH", os.path.join(_tmp, "credibility_model.joblib"))
os.environ.pop("FAKEGUARD_ONLINE", None)
os.environ.pop("GOOGLE_FACTCHECK_API_KEY", None)


import pytest


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """Tests never touch the internet; individual tests override _http_get with canned feeds."""
    import web_search_service

    def _blocked(url):
        raise ConnectionError("network disabled in tests")
    monkeypatch.setattr(web_search_service, "_http_get", _blocked)
    web_search_service.clear_cache()
