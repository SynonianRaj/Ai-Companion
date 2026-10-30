import pytest


@pytest.mark.asyncio
async def test_frontend_pwa_files_served(client):
    # Test index.html
    res_index = await client.get("/")
    assert res_index.status_code == 200
    assert "Aanya — AI Companion" in res_index.text
    assert 'rel="manifest"' in res_index.text

    # Test manifest.json
    res_manifest = await client.get("/public/manifest.json")
    assert res_manifest.status_code == 200
    manifest_data = res_manifest.json()
    assert manifest_data["short_name"] == "Aanya"
    assert manifest_data["display"] == "standalone"

    # Test sw.js
    res_sw = await client.get("/public/sw.js")
    assert res_sw.status_code == 200
    assert "CACHE_NAME" in res_sw.text

    # Test api.js
    res_api = await client.get("/js/api.js")
    assert res_api.status_code == 200
    assert "ai_disclosure_accepted: aiAccepted" in res_api.text
    assert "aiDisclosureAccepted" not in res_api.text

    # Test app.js
    res_app = await client.get("/js/app.js")
    assert res_app.status_code == 200
    assert "resetSessionToOnboarding" in res_app.text

    # Test PWA Icons
    res_icon_192 = await client.get("/icons/icon-192.png")
    assert res_icon_192.status_code == 200
    assert res_icon_192.headers.get("content-type") == "image/png"

    res_icon_512 = await client.get("/icons/icon-512.png")
    assert res_icon_512.status_code == 200
    assert res_icon_512.headers.get("content-type") == "image/png"

    # Test root manifest
    res_root_manifest = await client.get("/manifest.json")
    assert res_root_manifest.status_code == 200

    # Test PWA install modal in index.html
    assert 'id="install-pwa-btn"' in res_index.text
    assert 'id="pwa-install-modal"' in res_index.text
    # Verify developer log elements are NOT exposed in user-facing index.html
    assert 'id="llm-logs-modal"' not in res_index.text
    assert 'id="dev-logs-btn"' not in res_index.text


@pytest.mark.asyncio
async def test_frontend_js_syntax_validity():
    import subprocess
    import shutil
    from pathlib import Path

    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node.js binary not installed on test host")

    project_root = Path(__file__).resolve().parent.parent.parent
    js_files = [
        project_root / "frontend" / "js" / "app.js",
        project_root / "frontend" / "js" / "api.js"
    ]

    for js_path in js_files:
        assert js_path.exists(), f"File {js_path} does not exist"
        proc = subprocess.run([node_bin, "-c", str(js_path)], capture_output=True, text=True)
        assert proc.returncode == 0, f"Syntax error in {js_path.name}:\n{proc.stderr}"


@pytest.mark.asyncio
async def test_dev_llm_logs_endpoint(client):
    from backend.app.engine.adapter import record_llm_interaction

    # Record sample interaction
    record_llm_interaction(
        provider="mock",
        model="test-model",
        system_prompt="Test system prompt",
        consumed_input="Hello world",
        raw_response="Hi there",
        parsed_chunks=["Hi there"],
        latency_ms=12.5,
        status="success"
    )

    res = await client.get("/api/dev/llm-logs")
    assert res.status_code == 200
    data = res.json()
    assert "logs" in data
    assert isinstance(data["logs"], list)
    assert len(data["logs"]) >= 1
    latest = data["logs"][0]
    assert latest["provider"] == "mock"
    assert latest["model"] == "test-model"
    assert latest["system_prompt"] == "Test system prompt"
    assert latest["consumed_input"] == "Hello world"
    assert latest["parsed_chunks"] == ["Hi there"]
