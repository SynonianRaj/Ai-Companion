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
