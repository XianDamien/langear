import pytest


@pytest.mark.parametrize("key", ["vocabulary_english_to_chinese", "vocabulary_chinese_to_english"])
def test_mnemonic_persists_and_only_appears_on_the_answer(client, account, key):
    fields = {"word": "reluctant", "meaning": "不情愿的", "note": "搭配：be reluctant to do", "mnemonic": "联想一个不愿出门的人"}
    response = client.post("/api/v1/notes", json={
        "deck_id": account["deck_id"], "note_type_key": "vocabulary",
        "card_template_key": key, "fields": fields,
    })
    assert response.status_code == 201, response.text
    note = response.json()
    assert client.get(f"/api/v1/notes/{note['id']}").json()["fields"] == fields
    card = client.get(f"/api/v1/cards/{note['cards'][0]['id']}").json()
    assert "mnemonic" not in card["front"]
    assert card["back"]["mnemonic"] == fields["mnemonic"]
    assert card["back"]["note"] == fields["note"]
    fields["mnemonic"] = "更新后的助记"
    response = client.put(f"/api/v1/notes/{note['id']}", json={"revision": 1, "fields": fields})
    assert response.status_code == 200
    assert response.json()["cards"][0]["back"]["mnemonic"] == "更新后的助记"
    del fields["mnemonic"]
    response = client.put(f"/api/v1/notes/{note['id']}", json={"revision": 2, "fields": fields})
    assert response.status_code == 200
    assert "mnemonic" not in response.json()["cards"][0]["back"]


def test_mnemonic_is_optional_and_only_on_vocabulary(client, account):
    types = {row["key"]: row for row in client.get("/api/v1/note-types").json()["note_types"]}
    field = next(f for f in types["vocabulary"]["fields"] if f["key"] == "mnemonic")
    assert field["required"] is False
    assert field["kind"] == "text"
    assert all(f["key"] != "mnemonic" for f in types["sentence"]["fields"])
