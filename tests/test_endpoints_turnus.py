def test_preview_endpoint_ok(app_client, tmp_db_path):
    # Skapa data via rotation (direkt)
    import rotation
    tmpl_id = rotation.create_template(
        name="Std", rig_id=1,
        pattern={"weekly":[{"weekday":0,"start":"07:00","end":"19:00","role":"dag"}]}
    )
    rotation.generate_slots_from_template(tmpl_id, "2025-09-08", "2025-09-08", rig_id_override=1)

    resp = app_client.get("/turnus/preview?rig_id=1&start=2025-09-08&end=2025-09-08")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["count"] >= 1
    assert isinstance(data["items"], list)

def test_view_endpoint_only_published(app_client, tmp_db_path):
    import rotation
    tmpl_id = rotation.create_template(
        name="Std", rig_id=1,
        pattern={"weekly":[{"weekday":0,"start":"07:00","end":"19:00","role":"dag"}]}
    )
    rotation.generate_slots_from_template(tmpl_id, "2025-09-08", "2025-09-08", rig_id_override=1)

    # Ej publicerad => view ska vara tom
    resp = app_client.get("/turnus/view?rig_id=1&start=2025-09-08&end=2025-09-08")
    assert resp.status_code == 200
    assert resp.get_json()["count"] == 0

    # Publicera och testa igen
    slot_ids = [s["id"] for s in rotation.list_slots(rig_id=1)]
    rotation.publish_slots(slot_ids)
    resp2 = app_client.get("/turnus/view?rig_id=1&start=2025-09-08&end=2025-09-08")
    assert resp2.status_code == 200
    assert resp2.get_json()["count"] == len(slot_ids)
