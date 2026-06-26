import json
from collections import Counter, defaultdict

EVENT_PATH = "/Users/yangqi/Downloads/VAST_Challenge_2026_MC2/MC2 data_with_datetime.json"
ORG_PATH = "/Users/yangqi/Downloads/VAST_Challenge_2026_MC2/org_chart.json"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    events_data = load_json(EVENT_PATH)
    org_data = load_json(ORG_PATH)

    # event type
    event_types = [e.get("short_name", "unknown") for e in events_data["events"]]
    event_counter = Counter(event_types)

    print("\n=== Event type count ===")
    print("Number of event types:", len(event_counter))

    print("\n=== Event types by frequency ===")
    for k, v in event_counter.most_common():
        print(f"{k}: {v}")

    # department
    departments = [
        n for n in org_data["nodes"]
        if n.get("type") == "department"
    ]

    print("\n=== Department count ===")
    print("Number of departments:", len(departments))

    print("\n=== Departments ===")
    for d in departments:
        print(f"{d['id']} | {d['label']}")

    # rough semantic grouping
    groups = defaultdict(list)

    for et in sorted(event_counter.keys()):
        name = et.lower()

        if any(x in name for x in ["email", "sent", "message", "post"]):
            groups["communication / messaging"].append(et)
        elif any(x in name for x in ["meeting", "calendar"]):
            groups["calendar / meeting"].append(et)
        elif any(x in name for x in ["file", "download", "upload", "read", "list"]):
            groups["file access"].append(et)
        elif any(x in name for x in ["task", "assign", "queue"]):
            groups["agent task / delegation"].append(et)
        elif any(x in name for x in ["login", "access", "auth"]):
            groups["system access"].append(et)
        else:
            groups["other"].append(et)

    print("\n=== Similar event type groups ===")
    for group, items in groups.items():
        print(f"\n[{group}]")
        for item in items:
            print("  -", item)


if __name__ == "__main__":
    main()