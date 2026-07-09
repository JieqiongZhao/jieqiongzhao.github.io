"""
Extract a directed person-to-person communication matrix from the MC2 dataset,
grouped by department, for a drill-down (department <-> person) chord diagram.

Data quirks handled (discovered by inspecting "MC2 data.json" and org_chart.json):
  - "MC2 data.json" is a 70MB timeline of 185k events, most of which are single-party
    system/agent actions (check_email, read_file, assign_agent_task, ...) rather than
    communications between people.
  - The actual person-to-person message signal is the "sent" event type (7,407 events),
    each carrying a clean details.from / details.to person pair.
  - "received" (7,266 events) and "send_email" (45 events) are near-duplicate log
    entries of the same underlying emails as "sent" (same from/to/subject), logged
    from the recipient's mailbox / a different subsystem. Counting them too would
    double-count the same messages, so only "sent" is used.
  - org_chart.json nests people under departments via "contains" edges, except for
    the 5 department leads, who are attached via a "led_by" edge from the department
    instead. Both are folded together to get one department per person.

Output: mc2_connections.json, containing:
  - departments: ordered list of {id, label}
  - people: ordered list of {id, label, title, department}, grouped contiguously by
    department (in org_chart.json's original order) so the chord diagram can treat
    a department's people as one contiguous angular block.
  - person_matrix: NxN matrix (N = len(people)) where matrix[i][j] = number of
    "sent" messages from people[i] to people[j].

This file is intentionally small (people x people, not the full event log) so the
HTML page can fetch it at runtime instead of embedding the raw dataset.
"""

import json
from pathlib import Path

MC2_DIR = Path(__file__).parent.parent.parent / "VAST_Challenge_2026_MC2"
EVENTS_PATH = MC2_DIR / "MC2 data.json"
ORG_CHART_PATH = MC2_DIR / "org_chart.json"
OUTPUT_PATH = Path(__file__).parent / "mc2_connections.json"


def load_org_chart():
    with open(ORG_CHART_PATH) as f:
        return json.load(f)


def department_by_person(org):
    """Map each person id to their department id, via 'contains' and 'led_by' edges."""
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

    # Department leads are attached via "led_by" rather than "contains".
    for e in org["edges"]:
        if e["relation"] == "led_by":
            dept_of[e["target"]] = e["source"]

    return dept_of


def ordered_departments_and_people(org, dept_of):
    """Preserve org_chart.json's original node order for both departments and people."""
    departments = [
        {"id": n["id"], "label": n["label"]}
        for n in org["nodes"]
        if n["type"] == "department"
    ]
    people = [
        {
            "id": n["id"],
            "label": n["label"],
            "title": n.get("title", ""),
            "department": dept_of[n["id"]],
        }
        for n in org["nodes"]
        if n["type"] == "person"
    ]
    # Group people contiguously by department, preserving each group's internal order.
    dept_order = [d["id"] for d in departments]
    people.sort(key=lambda p: dept_order.index(p["department"]))
    return departments, people


def load_sent_events():
    with open(EVENTS_PATH) as f:
        data = json.load(f)
    return [e for e in data["events"] if e["short_name"] == "sent"]


def build_person_matrix(people, sent_events):
    index = {p["id"]: i for i, p in enumerate(people)}
    n = len(people)
    matrix = [[0] * n for _ in range(n)]
    for e in sent_events:
        d = e["details"]
        src, dst = index.get(d.get("from")), index.get(d.get("to"))
        if src is not None and dst is not None and src != dst:
            matrix[src][dst] += 1
    return matrix


def main():
    org = load_org_chart()
    dept_of = department_by_person(org)
    departments, people = ordered_departments_and_people(org, dept_of)

    sent_events = load_sent_events()
    matrix = build_person_matrix(people, sent_events)

    total_edges = sum(sum(row) for row in matrix)
    print(f"Departments: {len(departments)}, People: {len(people)}")
    print(f"'sent' events: {len(sent_events)}, resolved person-to-person edges: {total_edges}")

    output = {
        "departments": departments,
        "people": people,
        "person_matrix": matrix,
        "meta": {
            "total_sent_events": len(sent_events),
            "resolved_edges": total_edges,
        },
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
