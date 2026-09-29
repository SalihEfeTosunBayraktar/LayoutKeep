"""OpenRouter attribution headers name the real project.

OpenRouter'a giden isteklerdeki tanıtım başlıkları gerçek proje adresini taşır.
"""

from layoutkeep import __app_name__, __homepage__
from layoutkeep.providers._http_compat import OpenAIHTTPTransport


def test_openrouter_requests_carry_the_project_address_and_name():
    # OpenRouter adresi başlıkları ekler / an OpenRouter address adds the headers
    headers = OpenAIHTTPTransport("https://openrouter.ai/api/v1", "key").headers()
    assert headers["HTTP-Referer"] == __homepage__
    assert headers["X-Title"] == __app_name__


def test_the_project_address_matches_the_package_metadata():
    # pyproject ile paket aynı adresi söyler / pyproject and the package agree on the address
    from importlib.metadata import metadata

    urls = metadata("layoutkeep").get_all("Project-URL") or []
    assert f"Homepage, {__homepage__}" in urls


def test_a_local_server_gets_no_attribution_headers():
    # Yerel sunucuya tanıtım başlığı gitmez / a local server gets no attribution headers
    headers = OpenAIHTTPTransport("http://127.0.0.1:1234/v1", None).headers()
    assert "HTTP-Referer" not in headers
    assert "X-Title" not in headers
