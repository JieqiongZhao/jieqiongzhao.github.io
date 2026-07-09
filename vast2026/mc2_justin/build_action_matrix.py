"""
Extract a directed person -> action-type count matrix from the MC2 dataset,
for a two-layer Sankey diagram (departments/people on the left, action types
on the right).

The MC2 event log covers far more than messaging: 24 distinct `short_name`
action types were found (check_email, read_file, propose_meeting, give_advice,
post_flex, ...), confirming agents/people perform many kinds of actions besides
sending messages.

Data quirks handled (discovered by inspecting "MC2 data.json"):
  - There is no single consistent field for "who performed this action" across
    types. The actor is, in priority order: details.person, else details.from,
    else details.poster_id, else parties[0] -- each of those may itself be
    written as "person:x", "Agent/person:x", or "agent:person:x" (three
    different prefix conventions for "this person's AI agent did it"), or, for
    check_access/enter_room specifically, a plain "First Last" display name
    instead of an id. All four forms are normalized and, for the plain-name
    case, resolved via org_chart.json's person labels. This resolves all
    185,147 events with zero unattributed.
  - Four of the 24 short_names are duplicate log entries of another action,
    written by a second subsystem, and are dropped to avoid double-counting:
      - "received" duplicates "sent" (same from/to/subject, logged from the
        recipient's mailbox) -- same dedup already applied in
        build_org_matrix.py for the chord diagram.
      - "send_email" also duplicates "sent".
      - "flex_post" duplicates "post_flex" (same person + content, logged by
        the platform after "post_flex" is the person's initiating action).
      - "saidit_post" duplicates "post_saidit" for the same reason.
    This leaves 20 clean, non-overlapping action categories.

Output: mc2_actions.json, containing:
  - departments / people: same shape and order as mc2_connections.json, so
    both diagrams treat departments/people identically.
  - actions: ordered list of {id, label}.
  - person_action_matrix: len(people) x len(actions) matrix of counts.
"""

import json
import re
from pathlib import Path

MC2_DIR = Path(__file__).parent.parent.parent / "VAST_Challenge_2026_MC2"
EVENTS_PATH = MC2_DIR / "MC2 data.json"
ORG_CHART_PATH = MC2_DIR / "org_chart.json"
OUTPUT_PATH = Path(__file__).parent / "mc2_actions.json"

# short_names dropped as duplicate logs of another action (see docstring).
DROPPED_ACTIONS = {"received", "send_email", "flex_post", "saidit_post"}

ACTION_LABELS = {
    "check_email": "Check Email",
    "assign_agent_task": "Assign Agent Task",
    "read_file": "Read File",
    "queue_subordinate_task": "Queue Subordinate Task",
    "create_file": "Create File",
    "delete_file": "Delete File",
    "check_in": "Check In",
    "sent": "Send Message",
    "access_email": "Access Email",
    "give_advice": "Give Advice",
    "check_access": "Check Room Access",
    "enter_room": "Enter Room",
    "suggest_contacts": "Suggest Contacts",
    "propose_meeting": "Propose Meeting",
    "access_files": "Access Files",
    "list_files": "List Files",
    "ask_agent": "Ask Agent",
    "post_flex": "Post to Flex",
    "post_saidit": "Post to SaidIt",
    "saidit_post_check": "Check SaidIt Post",
}


def load_org_chart():
    with open(ORG_CHART_PATH) as f:
        return json.load(f)


def department_by_person(org):
    nodes = {n["id"]: n for n in org["nodes"]}
    children = {}
    for e in org["edges"]:
        if e["relation"] == "contains":
            children.setdefault(e["source"], []).append(e["target"])

    dept_of = {}

    def walk(node_id, dept):
        for child in children.get(node_id, []):
            child_type = nodes[child]["type"]
            new_dept = child if child_type == "department" else dept
            if child_type == "person":
                dept_of[child] = dept
            walk(child, new_dept)

    walk("company:tenant_thread", None)
    for e in org["edges"]:
        if e["relation"] == "led_by":
            dept_of[e["target"]] = e["source"]
    return dept_of


def ordered_departments_and_people(org, dept_of):
    departments = [
        {"id": n["id"], "label": n["label"]} for n in org["nodes"] if n["type"] == "department"
    ]
    people = [
        {"id": n["id"], "label": n["label"], "title": n.get("title", ""), "department": dept_of[n["id"]]}
        for n in org["nodes"]
        if n["type"] == "person"
    ]
    dept_order = [d["id"] for d in departments]
    people.sort(key=lambda p: dept_order.index(p["department"]))
    return departments, people


PREFIX_RE = re.compile(r"^(Agent/person:|agent:person:|person:)")


def normalize_actor(raw, label_to_id):
    if raw is None:
        return None
    m = PREFIX_RE.match(raw)
    if m:
        prefix = m.group(1)
        return "person:" + raw[len(prefix):]
    return label_to_id.get(raw)  # plain "First Last" display name fallback


def actor_for_event(event, label_to_id):
    d = event.get("details") or {}
    cand = d.get("person") or d.get("from") or d.get("poster_id")
    raw = cand if cand else (event.get("parties") or [None])[0]
    return normalize_actor(raw, label_to_id)


def load_events():
    with open(EVENTS_PATH) as f:
        data = json.load(f)
    return data["events"]


def build_person_action_matrix(people, actions, events, label_to_id):
    person_index = {p["id"]: i for i, p in enumerate(people)}
    action_index = {a: i for i, a in enumerate(actions)}
    n, k = len(people), len(actions)
    matrix = [[0] * k for _ in range(n)]

    unresolved = 0
    for e in events:
        short_name = e["short_name"]
        if short_name in DROPPED_ACTIONS or short_name not in action_index:
            continue
        actor = actor_for_event(e, label_to_id)
        if actor is None or actor not in person_index:
            unresolved += 1
            continue
        matrix[person_index[actor]][action_index[short_name]] += 1

    return matrix, unresolved


def main():
    org = load_org_chart()
    dept_of = department_by_person(org)
    departments, people = ordered_departments_and_people(org, dept_of)
    label_to_id = {n["label"]: n["id"] for n in org["nodes"] if n["type"] == "person"}

    events = load_events()
    actions = [a for a in ACTION_LABELS if a not in DROPPED_ACTIONS]
    matrix, unresolved = build_person_action_matrix(people, actions, events, label_to_id)

    total = sum(sum(row) for row in matrix)
    print(f"Departments: {len(departments)}, People: {len(people)}, Action types: {len(actions)}")
    print(f"Total events: {len(events)}, resolved person-action counts: {total}, unresolved: {unresolved}")

    output = {
        "departments": departments,
        "people": people,
        "actions": [{"id": a, "label": ACTION_LABELS[a]} for a in actions],
        "person_action_matrix": matrix,
        "meta": {
            "total_events": len(events),
            "resolved_counts": total,
            "dropped_duplicate_types": sorted(DROPPED_ACTIONS),
        },
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
