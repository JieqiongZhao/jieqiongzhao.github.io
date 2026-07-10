import json
from datetime import datetime, timedelta
from collections import defaultdict

EVENT_PATH = "./MC2 data_with_datetime.json"
ORG_PATH = "./org_chart.json"

OUT_LEVEL1 = "level1_department_pairs.json"
OUT_LEVEL2 = "level2_receiver_sets.json"
OUT_EVENTS = "events_for_trace.json"
OUT_EVENTS_PART1 = "events_for_trace_part1.json"
OUT_EVENTS_PART2 = "events_for_trace_part2.json"
OUT_EVENTS_PART3 = "events_for_trace_part3.json"

BIN_MINUTES = 10


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def save_json_split_into_3(path1, path2, path3, data):
    n = len(data)
    one_third = n // 3
    two_third = (n * 2) // 3

    part1 = data[:one_third]
    part2 = data[one_third:two_third]
    part3 = data[two_third:]

    save_json(path1, part1)
    save_json(path2, part2)
    save_json(path3, part3)

    print(f"Saved {path1}: {len(part1)} rows")
    print(f"Saved {path2}: {len(part2)} rows")
    print(f"Saved {path3}: {len(part3)} rows")


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

    s = str(x).strip()
    sl = s.lower()

    if sl.startswith("agent/person:") or sl.startswith("agent:person:"):
        return "agent"

    if sl.startswith("person:"):
        return "person"

    if sl.startswith("system:"):
        return "system"

    if sl.startswith("world:"):
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

FILE_ACTIONS = {
    "access_files",
    "create_file",
    "delete_file",
    "list_files",
    "read_file",
}

EMAIL_ACTIONS = {
    "access_email",
    "check_email",
    "send_email",
    "sent",
    "received",
}

SOCIAL_ACTIONS = {
    "flex_post",
    "post_flex",
    "post_saidit",
    "saidit_post",
    "saidit_post_check",
}

TASK_ACTIONS = {
    "assign_agent_task",
    "queue_subordinate_task",
}

ADVICE_ACTIONS = {
    "ask_agent",
    "give_advice",
    "suggest_contacts",
}

MEETING_ACTIONS = {
    "propose_meeting",
}

ACCESS_ACTIONS = {
    "check_access",
    "check_in",
    "enter_room",
}


def as_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def safe_details(e):
    d = e.get("details")
    return d if isinstance(d, dict) else {}


def normalize_party_id(x, label_to_id=None):
    return normalize_id(x, label_to_id)


def is_person_id(x, label_to_id=None):
    xid = normalize_id(x, label_to_id)
    return bool(xid and xid.startswith("person:"))


def is_agent_person_id(x, label_to_id=None):
    if not x:
        return False
    s = str(x)
    xid = normalize_id(x, label_to_id)
    return (
        "Agent/person:" in s
        or "agent:person:" in s
        or bool(xid and xid.startswith("person:"))
    )


def get_participant_summary(e, label_to_id=None):
    parties = e.get("parties") or []

    person_participants = []
    system_participants = []
    world_participants = []
    other_participants = []

    for p in parties:
        pid = normalize_id(p, label_to_id)
        if not pid:
            continue

        if pid.startswith("person:"):
            person_participants.append(pid)
        elif pid.startswith("system:"):
            system_participants.append(pid)
        elif pid.startswith("world:"):
            world_participants.append(pid)
        else:
            other_participants.append(pid)

    person_participants = sorted(set(person_participants))
    system_participants = sorted(set(system_participants))
    world_participants = sorted(set(world_participants))
    other_participants = sorted(set(other_participants))

    return {
        "party_ids": sorted(set(
            person_participants
            + system_participants
            + world_participants
            + other_participants
        )),
        "person_participants": person_participants,
        "system_participants": system_participants,
        "world_participants": world_participants,
        "other_participants": other_participants,
        "participant_count": len(person_participants),
        "entity_participant_count": (
            len(person_participants)
            + len(system_participants)
            + len(world_participants)
            + len(other_participants)
        )
    }


def supplement_receivers_from_parties(sender, receivers, participant_summary):
    sender_id = normalize_id(sender)
    receiver_ids = {
        normalize_id(r)
        for r in receivers
        if normalize_id(r)
    }

    result = list(receivers)

    for p in participant_summary["person_participants"]:
        if sender_id and p == sender_id:
            continue
        if p in receiver_ids:
            continue

        result.append(p)
        receiver_ids.add(p)

    return result


def extract_file_refs(e):
    d = safe_details(e)
    refs = []

    for key in [
        "file",
        "file_saved",
        "target",
        "source",
        "content_source",
    ]:
        value = d.get(key)
        if not value:
            continue

        for v in as_list(value):
            if isinstance(v, str):
                s = v.strip()
                if (
                    "." in s
                    or "/" in s
                    or "file" in s.lower()
                    or s.endswith(".json")
                    or s.endswith(".md")
                    or s.endswith(".txt")
                ):
                    refs.append(s)

    args = d.get("args") or {}
    if isinstance(args, dict):
        path = args.get("path")
        if path:
            refs.append(str(path))

    inner = d.get("details") or {}
    if isinstance(inner, dict):
        for key in ["file", "path", "target", "source"]:
            value = inner.get(key)
            if value:
                refs.extend([str(v) for v in as_list(value)])

    return sorted(set(refs))


def extract_content_fields(e):
    d = safe_details(e)

    fields = {}

    for key in [
        "subject",
        "content",
        "question",
        "response",
        "topic",
        "advice",
        "forum",
        "status",
        "access_type",
        "room",
        "name",
        "granted",
        "virus",
        "spread",
        "size_hint",
        "word_count",
        "content_length",
        "combo",
        "source",
    ]:
        if key in d:
            fields[key] = d.get(key)

    inner = d.get("details") or {}
    if isinstance(inner, dict):
        for key in ["subject", "time", "participants"]:
            if key in inner:
                fields[f"details.{key}"] = inner.get(key)

    return fields


def extract_referenced_people(e, label_to_id=None):
    d = safe_details(e)
    refs = []

    reference_fields = [
        "meeting_proposed_with",
        "reply_sent_to",
        "sent_to",
        "target_agent",
        "contacts",
        "calendar_emails_sent",
    ]

    for key in reference_fields:
        value = d.get(key)
        if not value:
            continue

        for v in as_list(value):
            vid = normalize_id(v, label_to_id)
            if vid and vid.startswith("person:"):
                refs.append(vid)

    inner = d.get("details") or {}
    if isinstance(inner, dict):
        for v in as_list(inner.get("participants")):
            vid = normalize_id(v, label_to_id)
            if vid and vid.startswith("person:"):
                refs.append(vid)

    target = d.get("target")
    tid = normalize_id(target, label_to_id)
    if tid and tid.startswith("person:"):
        refs.append(tid)

    return sorted(set(refs))


def classify_event_category(short_name):
    if short_name in FILE_ACTIONS:
        return "file_activity"
    if short_name in EMAIL_ACTIONS:
        return "email"
    if short_name in SOCIAL_ACTIONS:
        return "social_post"
    if short_name in TASK_ACTIONS:
        return "task_delegation"
    if short_name in ADVICE_ACTIONS:
        return "agent_advice"
    if short_name in MEETING_ACTIONS:
        return "meeting"
    if short_name in ACCESS_ACTIONS:
        return "access_room"
    return "other"

def get_first_person_party_raw(e):
    parties = e.get("parties") or []

    for p in parties:
        if entity_type(p) in {"agent", "person"}:
            return p

    return None
    
def parse_event_semantics(e, label_to_id=None):
    d = safe_details(e)
    short_name = e.get("short_name", "unknown")

    participant_summary = get_participant_summary(e, label_to_id)
    event_category = classify_event_category(short_name)

    task_type = d.get("task")
    detail_action = d.get("action")

    sender = None
    receivers = []
    relation_type = "unknown"
    parse_rule = "unparsed"

    # --------------------------------------------------
    # 1. Explicit from/to: strongest direction
    # --------------------------------------------------
    if d.get("from") and d.get("to"):
        sender = d.get("from")
        receivers = as_list(d.get("to"))
        relation_type = "direct_transfer"
        parse_rule = "details_from_to"

    else:
        a2a = d.get("a2a") or {}

        if isinstance(a2a, dict) and a2a.get("from") and a2a.get("to"):
            sender = a2a.get("from")
            receivers = as_list(a2a.get("to"))
            relation_type = "agent_to_agent"
            parse_rule = "details_a2a_from_to"

    # --------------------------------------------------
    # 2. Task delegation
    # --------------------------------------------------
    if sender is None and short_name in TASK_ACTIONS:
        sender = d.get("person")
        receiver = d.get("target_agent") or d.get("target")

        # queue_subordinate_task 样例里没有 person，但 parties 是 [target, assigner]
        # 例如 [Agent/person:victoria, Agent/person:evelyn], target_agent=evelyn
        # 这种可推断 sender = parties 中非 target_agent 的另一个人
        if not sender and receiver:
            receiver_id = normalize_id(receiver, label_to_id)
            possible_senders = [
                p for p in (e.get("parties") or [])
                if (
                    entity_type(p) in {"agent", "person"}
                    and normalize_id(p, label_to_id) != receiver_id
                    )]

            if possible_senders:
                sender = possible_senders[0]

        if sender and receiver and is_person_id(receiver, label_to_id):
            receivers = [receiver]
            relation_type = "task_delegation"
            parse_rule = "task_person_to_target"
        elif sender:
            receivers = supplement_receivers_from_parties(
                sender,
                [],
                participant_summary
            )
            if receivers:
                relation_type = "task_delegation_inferred_from_parties"
                parse_rule = "task_sender_parties_receivers"
            else:
                receivers = [sender]
                relation_type = "self_activity"
                parse_rule = "task_self_no_target"

    # --------------------------------------------------
    # 3. Meeting
    # --------------------------------------------------
    if sender is None and short_name == "propose_meeting":
        inner = d.get("details") or {}

        if isinstance(inner, dict):
            sender = d.get("person")

            if not sender:
                # propose_meeting 样例中 parties 只有发起人
                sender = get_first_person_party_raw(e)

            receivers = as_list(inner.get("participants"))

            if sender and receivers:
                relation_type = "meeting_proposal"
                parse_rule = "meeting_inner_participants"

        if sender is None and d.get("person") and d.get("meeting_proposed_with"):
            sender = d.get("person")
            receivers = as_list(d.get("meeting_proposed_with"))
            relation_type = "meeting_proposal"
            parse_rule = "meeting_proposed_with"

        if sender is None and d.get("person") and d.get("calendar_emails_sent"):
            sender = d.get("person")
            receivers = as_list(d.get("calendar_emails_sent"))
            relation_type = "calendar_email"
            parse_rule = "calendar_emails_sent"

    # --------------------------------------------------
    # 4. Email
    # --------------------------------------------------
    if sender is None and short_name in {"send_email", "sent", "received"}:
        if d.get("from") and d.get("to"):
            sender = d.get("from")
            receivers = as_list(d.get("to"))
            relation_type = "email_message"
            parse_rule = "email_from_to"
        elif d.get("person") and d.get("sent_to"):
            sender = d.get("person")
            receivers = as_list(d.get("sent_to"))
            relation_type = "email_message"
            parse_rule = "email_sent_to"
        elif d.get("person") and d.get("reply_sent_to"):
            sender = d.get("person")
            receivers = as_list(d.get("reply_sent_to"))
            relation_type = "email_reply"
            parse_rule = "email_reply_sent_to"

    # access_email / check_email 是 self activity。
    # reply_sent_to / meeting_proposed_with 在这里是 referenced_people，不是 receiver。
    if sender is None and short_name in {"access_email", "check_email"}:
        sender = d.get("person")

        if not sender:
            sender = get_first_person_party_raw(e)

        if sender:
            receivers = [sender]
            relation_type = "self_activity"
            parse_rule = f"{short_name}_self"

    # --------------------------------------------------
    # 5. File activity
    # --------------------------------------------------
    if sender is None and short_name in FILE_ACTIONS:
        sender = d.get("person")

    # 关键：delete_file / create_file / read_file 很多没有 details.person
    # 这时必须从 parties 里拿 raw value，例如 Agent/person:gabriel_sonar
        if not sender:
            sender = get_first_person_party_raw(e)

        if sender:
            receivers = [sender]
            relation_type = "file_self_activity"
            parse_rule = f"{short_name}_self"

    # --------------------------------------------------
    # 6. Advice / suggest contacts
    # --------------------------------------------------
    if sender is None and short_name in {"ask_agent", "give_advice"}:
        sender = d.get("person")

        if not sender:
            sender = get_first_person_party_raw(e)

        if sender:
            receivers = [sender]
            relation_type = "self_activity"
            parse_rule = f"{short_name}_self"

    if sender is None and short_name == "suggest_contacts":
        sender = d.get("person")

        if not sender:
            sender = get_first_person_party_raw(e)

        if sender:
            receivers = [sender]
            relation_type = "suggest_contacts_reference"
            parse_rule = "suggest_contacts_self_with_references"

    # --------------------------------------------------
    # 7. Social post
    # --------------------------------------------------
    if sender is None and short_name in SOCIAL_ACTIONS:
        sender = d.get("person") or d.get("poster_id")

        if not sender:
            sender = get_first_person_party_raw(e)

        if sender:
            if "saidit" in short_name:
                receivers = ["system:saidit"]
                relation_type = "social_post"
                parse_rule = "social_post_saidit"
            elif "flex" in short_name:
                receivers = ["system:flex"]
                relation_type = "social_post"
                parse_rule = "social_post_flex"
            else:
                receivers = [sender]
                relation_type = "social_check"
                parse_rule = "social_self_check"

    # --------------------------------------------------
    # 8. Room / access
    # --------------------------------------------------
    if sender is None and short_name in ACCESS_ACTIONS:
        sender = d.get("person") or d.get("name")

        if not sender:
            sender = get_first_person_party_raw(e)

        room = d.get("room") or d.get("name")

        if sender and short_name in {"check_access", "enter_room"}:
            if room:
                room_id = "world:room_" + str(room).lower().replace(" ", "_")
                receivers = [room_id]
            else:
                receivers = [sender]

            relation_type = "room_access"
            parse_rule = f"{short_name}_room"

        elif sender and short_name == "check_in":
            receivers = [sender]
            relation_type = "self_activity"
            parse_rule = "check_in_self"

    # --------------------------------------------------
    # 9. Generic person-target fallback
    # --------------------------------------------------
    if sender is None and d.get("person") and d.get("target"):
        sender = d.get("person")
        target = d.get("target")

        if is_person_id(target, label_to_id):
            receivers = [target]
            relation_type = "person_to_person"
            parse_rule = "generic_person_target_person"
        else:
            receivers = [sender]
            relation_type = "self_activity"
            parse_rule = "generic_person_target_nonperson_self"

    # --------------------------------------------------
    # 10. Generic person fallback
    # --------------------------------------------------
    if sender is None and d.get("person"):
        sender = d.get("person")
        receivers = supplement_receivers_from_parties(
            sender,
            [],
            participant_summary
        )

        if receivers:
            relation_type = "interaction_inferred_from_parties"
            parse_rule = "generic_person_parties"
        else:
            receivers = [sender]
            relation_type = "self_activity"
            parse_rule = "generic_person_self"

    # --------------------------------------------------
    # 11. Final parties fallback
    # --------------------------------------------------
# --------------------------------------------------
# 11. Final parties fallback
# --------------------------------------------------
    if sender is None:
        raw_persons = [
        p for p in (e.get("parties") or [])
        if entity_type(p) in {"agent", "person"}
    ]

        if len(raw_persons) >= 2:
            sender = raw_persons[0]
            receivers = raw_persons[1:]
            relation_type = "interaction_from_parties_fallback"
            parse_rule = "parties_order_fallback"

        elif len(raw_persons) == 1:
            sender = raw_persons[0]
            receivers = [raw_persons[0]]
            relation_type = "self_activity"
            parse_rule = "single_party_self"

    if sender:
        receivers = [r for r in receivers if r]

    # 不要把 sender 自己重复加成 receiver list 里的多个项
    receiver_ids_norm = []
    seen = set()
    for r in receivers:
        rid = normalize_id(r, label_to_id)
        if not rid or rid in seen:
            continue
        receiver_ids_norm.append(r)
        seen.add(rid)

    receivers = receiver_ids_norm

    return {
        "sender_raw": sender,
        "receiver_raws": receivers,
        "event_category": event_category,
        "relation_type": relation_type,
        "parse_rule": parse_rule,
        "task_type": task_type,
        "detail_action": detail_action,
        "file_refs": extract_file_refs(e),
        "content_fields": extract_content_fields(e),
        "referenced_people": extract_referenced_people(e, label_to_id),
        **participant_summary
    }

def build_events(event_data, org_data):
    nodes, parent, label_to_id = build_org(org_data)
    rows = []

    for e in event_data["events"]:
        dt = parse_time(e.get("event_datetime"))
        if dt is None:
            continue

        sem = parse_event_semantics(e, label_to_id)
        sender_raw = sem["sender_raw"]
        receiver_raws = sem["receiver_raws"]

        if not sender_raw:
            continue
        
        if not receiver_raws:
            receiver_raws = [sender_raw]

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

    # 保持原输出结构
    "action": e.get("short_name", "unknown"),
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

    # 新增：规范化事件语义
    "event_category": sem["event_category"],
    "relation_type": sem["relation_type"],
    "parse_rule": sem["parse_rule"],

    # 新增：short_name 之外的 details action/task
    "task_type": sem["task_type"],
    "detail_action": sem["detail_action"],

    # 新增：文件/内容/引用对象
    "file_refs": sem["file_refs"],
    "content_fields": sem["content_fields"],
    "referenced_people": sem["referenced_people"],

    # 新增：participants 分类
    "party_ids": sem["party_ids"],
    "person_participants": sem["person_participants"],
    "system_participants": sem["system_participants"],
    "world_participants": sem["world_participants"],
    "other_participants": sem["other_participants"],
    "participant_count": sem["participant_count"],
    "entity_participant_count": sem["entity_participant_count"],
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
    save_json_split_into_3(
    OUT_EVENTS_PART1,
    OUT_EVENTS_PART2,
    OUT_EVENTS_PART3,
    rows
)

    print("raw parsed events:", len(rows))
    print("level1 points:", len(level1))
    print("level2 glyphs:", len(level2))
    print("saved:", OUT_LEVEL1, OUT_LEVEL2, OUT_EVENTS)


if __name__ == "__main__":
    main()