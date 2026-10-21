from app.domain import CSV_COLUMNS, make_csv


def test_csv_exact_header_and_escaping():
    output = make_csv([{"photo_id": "photo-1", "lighting": 'warm,"soft"'}])
    assert output.splitlines()[0] == "person_id,photo_id,lighting,device,self_undertone,gold_or_silver,vein_colour,annotator1,annotator2,annotator3,final_label,skin_group"
    assert len(CSV_COLUMNS) == 12
    assert '"warm,""soft"""' in output


def test_blank_unknown_annotations_stay_empty():
    output = make_csv([{"photo_id": "p1"}]).splitlines()[1]
    assert output.split(",")[0:3] == ["", "p1", ""]
