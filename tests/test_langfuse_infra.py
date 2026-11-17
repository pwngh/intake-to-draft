"""Local stack configuration checks; these tests do not start Docker or use keys."""

import json
from pathlib import Path
import runpy
import stat

import yaml

ROOT = Path(__file__).parents[1]


def test_local_credentials_are_generated_privately_and_reused(tmp_path, monkeypatch):
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "unrelated-environment-key")
    launcher = runpy.run_path(str(ROOT / "scripts/langfuse"))
    values, client = launcher["configuration"](tmp_path)
    assert launcher["configuration"](tmp_path) == (values, client)
    assert client["secret_key"] != "unrelated-environment-key"
    assert client["base_url"] == "http://127.0.0.1:13000"
    assert client["project_id"] == "intake-demo"
    assert json.loads((tmp_path / "langfuse-client.json").read_text()) == client
    for name in ("langfuse.env", "langfuse-client.json"):
        assert stat.S_IMODE((tmp_path / name).stat().st_mode) == 0o600


def test_stack_exposes_only_loopback_ui_and_pins_every_image():
    compose = yaml.safe_load((ROOT / "infra/langfuse.compose.yml").read_text())
    assert compose["networks"]["default"]["internal"] is True
    services = compose["services"]
    ports = [(name, port) for name, service in services.items() for port in service.get("ports", [])]
    assert ports == [("web", "127.0.0.1:13000:3000")]
    assert all("@sha256:" in service["image"] for service in services.values())
    for name in ("web", "worker"):
        assert services[name]["environment"]["TELEMETRY_ENABLED"] == "false"
    assert services["web"]["environment"]["AUTH_DISABLE_SIGNUP"] == "true"


def test_project_verification_rejects_redirects_without_forwarding_credentials():
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread
    from urllib.error import HTTPError
    import pytest

    paths = []
    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            self.send_response(302)
            self.send_header("Location", "/redirected")
            self.end_headers()
        def log_message(self, *args):
            pass
    server = HTTPServer(("127.0.0.1", 0), Redirect)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        launcher = runpy.run_path(str(ROOT / "scripts/langfuse"))
        verify = launcher["verify_project"]
        verify.__globals__["BASE_URL"] = f"http://127.0.0.1:{server.server_port}"
        with pytest.raises(HTTPError) as error:
            verify({"public_key": "demo-public", "secret_key": "demo-secret"})
        assert error.value.code == 302
        assert paths == ["/api/public/projects"]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
