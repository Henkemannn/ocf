import rotation

def test_template_and_slot_generation(tmp_db_path):
    # Skapa template: vardagar dagpass, helg nattpass
    tmpl_id = rotation.create_template(
        name="Std",
        rig_id=1,
        pattern={
            "weekly": [
                {"weekday": 0, "start": "07:00", "end": "19:00", "role": "dag"},
                {"weekday": 1, "start": "07:00", "end": "19:00", "role": "dag"},
                {"weekday": 2, "start": "07:00", "end": "19:00", "role": "dag"},
                {"weekday": 3, "start": "07:00", "end": "19:00", "role": "dag"},
                {"weekday": 4, "start": "07:00", "end": "19:00", "role": "dag"},
                {"weekday": 5, "start": "19:00", "end": "07:00", "role": "natt"},
                {"weekday": 6, "start": "19:00", "end": "07:00", "role": "natt"},
            ]
        }
    )
    assert tmpl_id > 0

    created = rotation.generate_slots_from_template(tmpl_id, "2025-09-08", "2025-09-14", rig_id_override=1)
    # En vecka → 7 slots
    assert created == 7

    # Preview ska ge 7 rader (alla status)
    rows = rotation.preview(rig_id=1, start_ts="2025-09-08T00:00", end_ts="2025-09-15T00:00")
    assert len(rows) == 7
    # Ingen publicerad ännu
    view_rows = rotation.view(rig_id=1, start_ts="2025-09-08T00:00", end_ts="2025-09-15T00:00")
    assert len(view_rows) == 0

def test_publish_and_view(tmp_db_path):
    tmpl_id = rotation.create_template(
        name="Std", rig_id=1,
        pattern={"weekly":[{"weekday":0,"start":"07:00","end":"19:00","role":"dag"}]}
    )
    rotation.generate_slots_from_template(tmpl_id, "2025-09-08", "2025-09-08", rig_id_override=1)
    slot_ids = [s["id"] for s in rotation.list_slots(rig_id=1)]
    assert slot_ids, "Inga slots genererade"

    n = rotation.publish_slots(slot_ids)
    assert n == len(slot_ids)

    view_rows = rotation.view(rig_id=1, start_ts="2025-09-08T00:00", end_ts="2025-09-08T23:59")
    assert len(view_rows) == len(slot_ids)
