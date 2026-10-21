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
