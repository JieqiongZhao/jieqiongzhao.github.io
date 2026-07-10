import json
from collections import Counter, defaultdict

EVENT_PATH = "/Users/yangqi/Downloads/VAST_Challenge_2026_MC2/mc2_qi/MC2 data_with_datetime.json"

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def collect_detail_fields(obj, prefix="details", counter=None):
    """
    收集 details 中所有字段路径。
    例如：
    details.person
    details.target
    details.a2a.from
    details.a2a.to
    details.meeting.organizer
    details.meeting.participants
    """
    if counter is None:
        counter = Counter()

    if not isinstance(obj, dict):
        return counter

    for k, v in obj.items():
        path = f"{prefix}.{k}"
        counter[path] += 1

        if isinstance(v, dict):
            collect_detail_fields(v, path, counter)

        elif isinstance(v, list):
            # 记录 list 字段本身
            counter[path + "[]"] += 1

            # 如果 list 里面是 dict，也继续扫描里面的字段
            for item in v:
                if isinstance(item, dict):
                    collect_detail_fields(item, path + "[]", counter)

    return counter

def main():
    data = load_json(EVENT_PATH)
    events = data.get("events", data)

    field_counter = Counter()
    top_level_counter = Counter()
    fields_by_action = defaultdict(Counter)

    for e in events:
        details = e.get("details") or {}
        action = e.get("short_name", "unknown")

        if not isinstance(details, dict):
            continue

        # 顶层字段名，比如 person / target / from / to
        for k in details.keys():
            top_level_counter[k] += 1

        # 完整字段路径，比如 details.a2a.from
        detail_fields = collect_detail_fields(details)

        for field, count in detail_fields.items():
            field_counter[field] += count
            fields_by_action[action][field] += count

    print("\n===== details 顶层字段名种类 =====")
    print("数量:", len(top_level_counter))
    for field, count in top_level_counter.most_common():
        print(f"{field}: {count}")

    print("\n===== details 所有字段路径种类 =====")
    print("数量:", len(field_counter))
    for field, count in field_counter.most_common():
        print(f"{field}: {count}")

    print("\n===== 每种 action 对应的 details 字段 =====")
    for action, counter in sorted(fields_by_action.items()):
        print(f"\n--- {action} ---")
        for field, count in counter.most_common():
            print(f"  {field}: {count}")

    # 保存成 json，方便你后面查
    out = {
        "details_top_level_fields": [
            {"field": k, "count": v}
            for k, v in top_level_counter.most_common()
        ],
        "details_all_field_paths": [
            {"field": k, "count": v}
            for k, v in field_counter.most_common()
        ],
        "fields_by_action": {
            action: [
                {"field": k, "count": v}
                for k, v in counter.most_common()
            ]
            for action, counter in fields_by_action.items()
        }
    }

    with open("details_fields_summary.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print("\nSaved: details_fields_summary.json")

if __name__ == "__main__":
    main()