CSV_COLUMNS = ("person_id", "photo_id", "lighting", "device", "self_undertone", "gold_or_silver", "vein_colour", "annotator1", "annotator2", "annotator3", "final_label", "skin_group")


def empty_annotation():
    return {column: "" for column in CSV_COLUMNS}


def escape_csv(value):
    text = str(value or "")
    return '"' + text.replace('"', '""') + '"' if any(ch in text for ch in ',"\r\n') else text


def make_csv(rows):
    return "\r\n".join([",".join(CSV_COLUMNS), *(",".join(escape_csv(row.get(column, "")) for column in CSV_COLUMNS) for row in rows)]) + "\r\n"
