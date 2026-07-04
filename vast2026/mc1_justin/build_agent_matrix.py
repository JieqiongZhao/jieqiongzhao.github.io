"""
Extract a directed agent-to-agent communication matrix from the MC1 dataset.

Data quirks handled (discovered by inspecting MC1_final_00.json):
  - Each round has a top-level "communications" list (not nested under
    "agent_outputs" as the README sketch suggests).
  - Most messages carry an explicit "recipients" list, using role names
    ("legal", "platform_trust", "pr", "social_manager", "pr_intern",
    "intern", "judge") rather than agent_ids, plus the sentinel "ALL"
    meaning "broadcast to every other agent".
  - The sender's own role is called "social_media" in agent_role, but the
    *recipient* alias for that same agent is spelled "social_manager" in
    other messages' recipients lists. Both are mapped to social_media_agent.
  - Some one_on_one_chat messages have an empty "recipients" list but a
    "responding_to" field that references another message's message_id.
    For those, the recipient is inferred as the sender of the message being
    replied to.
  - Public posts (personal_post, official_post, anonymous_post) and a
    residual set of one_on_one_chat "conversation starters" have no
    resolvable agent recipient at all (they target the public, or the data
    simply never specifies a counterpart). These are counted but excluded
    from the agent-to-agent matrix, since a chord diagram needs a closed
    node set.

Output: agent_connections.json, containing the ordered agent list and the
directed weight matrix matrix[i][j] = number of messages sent from agent i
to agent j, plus a flat edge list for convenience.
"""

import json
from pathlib import Path

DATA_PATH = Path(__file__).parent.parent.parent / "VAST_Challenge_2026_MC1" / "MC1_final_00.json"
OUTPUT_PATH = Path(__file__).parent / "agent_connections.json"

AGENTS = [
    "legal_agent",
    "quality_agent",
    "pr_agent",
    "social_media_agent",
    "pr_intern_agent",
    "intern_agent",
    "judge_agent",
]

AGENT_LABELS = {
    "legal_agent": "Legal-Agent",
    "quality_agent": "Platform-Trust-Agent",
    "pr_agent": "PR-Agent",
    "social_media_agent": "Social-Manager-Agent",
    "pr_intern_agent": "PR-Intern-Agent",
    "intern_agent": "Intern-Agent",
    "judge_agent": "Judge-Agent",
}

# Maps recipient role strings (as they appear in the "recipients" field) to agent_ids.
ROLE_TO_AGENT = {
    "legal": "legal_agent",
    "platform_trust": "quality_agent",
    "pr": "pr_agent",
    "social_media": "social_media_agent",
    "social_manager": "social_media_agent",  # alias quirk, see module docstring
    "pr_intern": "pr_intern_agent",
    "intern": "intern_agent",
    "judge": "judge_agent",
}


def load_messages():
    with open(DATA_PATH) as f:
        data = json.load(f)
    messages = []
    for round_ in data["rounds"]:
        messages.extend(round_["communications"])
    return messages


def resolve_recipients(message, recipients_field):
    """Expand a raw recipients list (role strings / "ALL") into agent_ids."""
    sender = message["agent_id"]
    if "ALL" in recipients_field:
        return [a for a in AGENTS if a != sender]
    resolved = []
    for role in recipients_field:
        agent = ROLE_TO_AGENT.get(role)
        if agent and agent != sender:
            resolved.append(agent)
    return resolved


def extract_edges(messages):
    by_id = {m["message_id"]: m for m in messages}
    edges = []  # list of (sender, recipient, message_id)
    unresolved = 0

    for m in messages:
        sender = m["agent_id"]
        recipients_field = m.get("recipients") or []

        if recipients_field:
            for recipient in resolve_recipients(m, recipients_field):
                edges.append((sender, recipient, m["message_id"]))
            continue

        responding_to = m.get("responding_to")
        original = by_id.get(responding_to) if responding_to else None
        if original and original["agent_id"] != sender:
            edges.append((sender, original["agent_id"], m["message_id"]))
            continue

        unresolved += 1

    return edges, unresolved


def build_matrix(edges):
    index = {a: i for i, a in enumerate(AGENTS)}
    matrix = [[0] * len(AGENTS) for _ in AGENTS]
    for sender, recipient, _ in edges:
        matrix[index[sender]][index[recipient]] += 1
    return matrix


def main():
    messages = load_messages()
    edges, unresolved = extract_edges(messages)
    matrix = build_matrix(edges)

    print(f"Total messages in dataset: {len(messages)}")
    print(f"Resolved agent-to-agent edges: {len(edges)}")
    print(f"Unresolved (public posts / unaddressed DMs, excluded): {unresolved}")
    print()
    header = "".join(f"{AGENT_LABELS[a]:>24}" for a in AGENTS)
    row_label = "from / to"
    print(f"{row_label:>24}{header}")
    for i, a in enumerate(AGENTS):
        row = "".join(f"{matrix[i][j]:>24}" for j in range(len(AGENTS)))
        print(f"{AGENT_LABELS[a]:>24}{row}")

    output = {
        "agents": AGENTS,
        "labels": [AGENT_LABELS[a] for a in AGENTS],
        "matrix": matrix,
        "edges": [
            {"source": s, "target": t, "message_id": mid} for s, t, mid in edges
        ],
        "meta": {
            "total_messages": len(messages),
            "resolved_edges": len(edges),
            "unresolved_messages": unresolved,
        },
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
