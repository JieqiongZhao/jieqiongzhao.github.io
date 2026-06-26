import json
from datetime import datetime, timedelta
from collections import defaultdict

EVENT_PATH = "./MC2 data_with_datetime.json"
ORG_PATH = "./org_chart.json"

OUT_LEVEL1 = "level1_department_pairs.json"
OUT_LEVEL2 = "level2_receiver_sets.json"
OUT_EVENTS = "events_for_trace.json"

BIN_MINUTES = 10


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def normalize_id(x, label_to_id=None):
    if not x:
        return None

    x = str(x).strip()

    x = x.replace("Agent/person:", "person:")
    x = x.replace("agent:person:", "person:")

    if label_to_id and x.lower() in label_to_id:
        return label_to_id[x.lower()]

    if x.startswith("person:") or x.startswith("world:"):
        return x

    if " " in x:
        return "person:" + x.lower().replace(" ", "_")

    return x

def entity_type(x):
    if not x:
        return "unknown"
    s = str(x).lower()
    if "agent" in s:
        return "agent"
    if s.startswith("person:"):
        return "person"
    if s.startswith("world:"):
        return "world"
    return "unknown"

def parse_time(t):
    if not t:
        return None
    return datetime.strptime(t, "%Y-%m-%d %H:%M:%S")


def floor_time(dt, minutes):
    return dt - timedelta(
        minutes=dt.minute % minutes,
        seconds=dt.second,
        microseconds=dt.microsecond
    )


def get_links(org):
    return org.get("links") or org.get("edges") or []


def build_org(org):
    nodes = {n["id"]: n for n in org["nodes"]}
    parent = {}
    label_to_id = {}

    for n in org["nodes"]:
        if n.get("type") == "person":
            label = n.get("label")
            if label:
                label_to_id[label.lower()] = n["id"]

    for e in get_links(org):
        parent[e["target"]] = e["source"]

    return nodes, parent, label_to_id


def find_ancestor(node_id, parent, nodes, target_type):
    cur = normalize_id(node_id)

    while cur:
        n = nodes.get(cur)
        if n and n.get("type") == target_type:
            return n
        cur = parent.get(cur)

    return None


def get_group(entity_id, parent, nodes):
    base = normalize_id(entity_id)

    if not base:
        return "Unknown Department", "Unknown Team"

    if base.startswith("world:"):
        return "World", "World"

    team = find_ancestor(base, parent, nodes, "team")
    dept = find_ancestor(base, parent, nodes, "department")

    return (
        dept["label"] if dept else "Unknown Department",
        team["label"] if team else "Unknown Team"
    )


def get_label(entity_id, nodes):
    base = normalize_id(entity_id)

    if base in nodes:
        return nodes[base].get("label", base)

    if not base:
        return "Unknown"

    return (
        base.replace("person:", "")
        .replace("world:", "")
        .replace("_", " ")
        .title()
    )


def parse_sender_receivers(e):
    d = e.get("details") or {}
    parties = e.get("parties") or []

    if d.get("from") and d.get("to"):
        return d["from"], [d["to"]]

    a2a = d.get("a2a") or {}
    if a2a.get("from") and a2a.get("to"):
        return a2a["from"], [a2a["to"]]

    if d.get("person") and d.get("target"):
        return d["person"], [d["target"]]

    inner = d.get("details") or {}
    if d.get("person") and isinstance(inner, dict) and inner.get("person"):
        return d["person"], [inner["person"]]

    if d.get("person") and d.get("calendar_emails_sent"):
        return d["person"], d["calendar_emails_sent"]

    meeting = d.get("meeting") or {}
    if meeting:
        organizer = meeting.get("organizer") or d.get("person")
        participants = meeting.get("participants") or []
        if organizer and participants:
            return organizer, participants

    if d.get("person"):
        return d["person"], [d["person"]]

    if len(parties) >= 2:
        return parties[0], parties[1:]

    if len(parties) == 1:
        return parties[0], [parties[0]]

    return None, []


def build_events(event_data, org_data):
    nodes, parent, label_to_id = build_org(org_data)
    rows = []

    for e in event_data["events"]:
        dt = parse_time(e.get("event_datetime"))
        if dt is None:
            continue

        sender_raw, receiver_raws = parse_sender_receivers(e)

        # 如果没有 sender，才跳过
        if not sender_raw:
            continue

        # 如果是 file 相关事件但没有 receiver，就保留，用 file/system 做 receiver
        details_text = json.dumps(e.get("details", {}), ensure_ascii=False).lower()
        is_file_related = (
            "file" in details_text
            or "read_file" in details_text
            or "create_file" in details_text
            or "access_files" in details_text
            or "delete_file" in details_text
            or "list_files" in details_text
        )

        if not receiver_raws:
            if is_file_related:
                receiver_raws = ["system:file_system"]
            else:
                continue

        sender_id = normalize_id(sender_raw)
        sender_dept, sender_team = get_group(sender_raw, parent, nodes)
        
        receivers = []
        for rr in receiver_raws:
            rid = normalize_id(rr)
            if not rid:
                continue

            r_dept, r_team = get_group(rr, parent, nodes)

            receivers.append({
                "id": rid,
                "name": get_label(rr, nodes),
                "type": entity_type(rr),
                "department": r_dept,
                "team": r_team
            })

        if not receivers:
            continue

        rows.append({
            "id": e.get("id"),
            "time": e.get("event_datetime"),
            "time_bin": floor_time(dt, BIN_MINUTES).strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": e.get("when", 0),
            "action": e.get("short_name", "unknown"),

            # 新增：给前端 file trace 用
            "short_name": e.get("short_name", "unknown"),
            "details": e.get("details", {}),
            "parties": e.get("parties", []),

            "sender_id": sender_id,
            "sender_name": get_label(sender_raw, nodes),
            "sender_type": entity_type(sender_raw),
            "sender_department": sender_dept,
            "sender_team": sender_team,

            "receivers": receivers,
            "receiver_ids": sorted([r["id"] for r in receivers]),
            "receiver_departments": sorted(set(r["department"] for r in receivers)),
            "receiver_teams": sorted(set(r["team"] for r in receivers)),
        })

    return rows

def aggregate_level1(rows):
    """
    Level 1:
    multi-receiver event is split by receiver department.
    key = time_bin + sender_department + receiver_department + action

    x position:
    use first_time / first_timestamp from the earliest raw event in this aggregated group.
    """
    agg = {}

    for r in rows:
        receiver_departments = r.get("receiver_departments", [])

        if not receiver_departments:
            receiver_departments = ["Unknown Receiver Department"]

        for receiver_dept in receiver_departments:
            key = (
                r["time_bin"],
                r["sender_department"],
                receiver_dept,
                r["action"]
            )

            if key not in agg:
                agg[key] = {
                    "time_bin": r["time_bin"],

                    # original event time for x coordinate
                    "first_time": r["time"],
                    "first_timestamp": r["timestamp"],

                    "sender_department": r["sender_department"],
                    "receiver_department": receiver_dept,
                    "pair": f"{r['sender_department']} → {receiver_dept}",
                    "action": r["action"],

                    "sender_id": r["sender_id"],
                    "sender_name": r["sender_name"],
                    "sender_type": r["sender_type"],
                    "receiver_ids": list(r.get("receiver_ids", [])),
                    "receivers": r.get("receivers", []),

                    "count": 0
                }

            agg[key]["count"] += 1

            # keep earliest raw event time inside this bin/group
            if r["timestamp"] < agg[key]["first_timestamp"]:
                agg[key]["first_time"] = r["time"]
                agg[key]["first_timestamp"] = r["timestamp"]

    return list(agg.values())

def aggregate_level2(rows):
    """
    Level 2:
    preserve receiver set.
    key = time_bin + sender + action + exact receiver_id_set

    x position:
    use first_time / first_timestamp from the earliest raw event in this aggregated group.
    """
    agg = {}

    for r in rows:
        receiver_id_set = tuple(sorted(r.get("receiver_ids", [])))
        receiver_dept_set = tuple(sorted(r.get("receiver_departments", [])))

        if not receiver_id_set:
            receiver_id_set = ("unknown_receiver",)

        if not receiver_dept_set:
            receiver_dept_set = ("Unknown Receiver Department",)

        key = (
            r["time_bin"],
            r["sender_id"],
            r["action"],
            receiver_id_set
        )

        if key not in agg:
            agg[key] = {
                "time_bin": r["time_bin"],

                # original event time for x coordinate
                "first_time": r["time"],
                "first_timestamp": r["timestamp"],

                "sender_id": r["sender_id"],
                "sender_name": r["sender_name"],
                "sender_type": r["sender_type"],
                "sender_department": r["sender_department"],
                "sender_team": r["sender_team"],

                "action": r["action"],

                "receiver_ids": list(receiver_id_set),
                "receiver_departments": list(receiver_dept_set),
                "receiver_count": len(receiver_id_set),

                # keep full receiver info for trace / tooltip
                "receivers": r.get("receivers", []),

                "count": 0,
                "segment_units": 0
            }

        agg[key]["count"] += 1
        agg[key]["segment_units"] += 1

        # keep earliest raw event time inside this bin/group
        if r["timestamp"] < agg[key]["first_timestamp"]:
            agg[key]["first_time"] = r["time"]
            agg[key]["first_timestamp"] = r["timestamp"]

    return list(agg.values())

def debug_john_sender(rows):
    print("\n===== JOHN AS SENDER DEBUG =====")

    found = 0

    for r in rows:
        text = f"{r.get('sender_id', '')} {r.get('sender_name', '')}".lower()

        if "john" in text or "winward" in text or "windward" in text:
            found += 1
            print(
                "sender_id =", r["sender_id"],
                "| sender_name =", r["sender_name"],
                "| sender_department =", r["sender_department"],
                "| sender_team =", r["sender_team"],
                "| action =", r["action"],
                "| time =", r["time"],
                "| event_id =", r["id"]
            )

    print("TOTAL JOHN SENDER ROWS =", found)

def main():
    event_data = load_json(EVENT_PATH)
    org_data = load_json(ORG_PATH)

    rows = build_events(event_data, org_data)

    level1 = aggregate_level1(rows)
    level2 = aggregate_level2(rows)

    save_json(OUT_LEVEL1, level1)
    save_json(OUT_LEVEL2, level2)
    save_json(OUT_EVENTS, rows)

    print("raw parsed events:", len(rows))
    print("level1 points:", len(level1))
    print("level2 glyphs:", len(level2))
    print("saved:", OUT_LEVEL1, OUT_LEVEL2, OUT_EVENTS)


if __name__ == "__main__":
    main()