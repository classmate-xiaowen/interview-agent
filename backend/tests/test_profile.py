def test_profile_roundtrip(test_app):
    r = test_app.put("/api/profile", json={"skills": "Python", "target_role": "后端", "years": 3})
    assert r.status_code == 200 and r.json()["target_role"] == "后端"
    g = test_app.get("/api/profile")
    assert g.status_code == 200 and g.json()["skills"] == "Python"
