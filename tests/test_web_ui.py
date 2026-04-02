import web_ui


def test_home_route():
    client = web_ui.app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    text = resp.data.decode("utf-8")
    assert "Research Hub 本地工具" in text


def test_search_route_monkeypatched(monkeypatch):
    def fake_search(query: str, docs_dir: str = "./docs", limit: int = 10):
        return [{"arxiv_id": "x", "title": "t", "filename": "f", "hit_count": 1, "snippet": "s"}]

    monkeypatch.setattr(web_ui, "run_pdf_search", fake_search)

    client = web_ui.app.test_client()
    resp = client.post("/search", data={"query": "world model", "limit": "3", "docs_dir": "./docs"})
    assert resp.status_code == 200
    assert "world model" in resp.data.decode("utf-8")

