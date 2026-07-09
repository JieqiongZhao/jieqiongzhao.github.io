"""
Extract directed agent-to-agent communication matrices from the MC1 dataset.

Two distinct kinds of directed agent-to-agent links are extracted:

  1. Direct replies — resolved from the structured "recipients" /
     "responding_to" fields (who a message was actually addressed to).
  2. @ mentions — agents also reference each other inline in message
     "content" using short role tags (e.g. "@legal", "@pr_intern"), which
     may name agents beyond the formal recipients list. These are found by
     regex-scanning content for "@<role>" tokens and mapping them through
     the same ROLE_TO_AGENT table used for recipients.

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
    The same alias quirk shows up in @ mention tags too (content uses
    "@social_manager", never "@social_media").
  - Some one_on_one_chat messages have an empty "recipients" list but a
    "responding_to" field that references another message's message_id.
    For those, the recipient is inferred as the sender of the message being
    replied to.
  - Public posts (personal_post, official_post, anonymous_post) and a
    residual set of one_on_one_chat "conversation starters" have no
    resolvable agent recipient at all (they target the public, or the data
    simply never specifies a counterpart). These are counted but excluded
    from the reply matrix, since a chord diagram needs a closed node set.
  - Message content also mentions plenty of non-agent @handles (external
    orgs, journalists, personal accounts like "@PropTechWatcher" or
    "@ElenaMarquez"). Only tokens that match a known agent role are kept;
    everything else is ignored. A mention of an agent's own role within its
    own message (rare, but occurs when a sender re-quotes a tag) is dropped
    since it isn't a cross-agent edge. Repeated tags of the same agent
    within a single message are also collapsed to one edge, so a message
    that says "@pr ... following up, @pr" still only counts once — the
    matrix counts *messages that mention*, not raw tag occurrences.

Output: agent_connections.json, containing the ordered agent list and three
directed weight matrices — reply_matrix, mention_matrix, and combined_matrix
(their elementwise sum) — plus flat edge lists for each of the two kinds.
"""

import json
import re
from pathlib import Path

DATA_PATH = Path(__file__).parent / "MC1_final_00.json"
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

# Matches "@<token>" tags in free-text message content. Only tokens that
# resolve through ROLE_TO_AGENT are kept; unrelated @handles (external orgs,
# journalists, personal Flex accounts, etc.) are ignored.
MENTION_TAG_RE = re.compile(r"@(\w+)")


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


def extract_mentions(messages):
    """Find agent-to-agent @ mentions inside message content.

    Tags are deduped per message: a message that tags the same agent
    multiple times ("@pr ... @pr") still only produces one edge for that
    pair, since we're counting messages-that-mention, not raw tag counts.
    Self-mentions (an agent's own role tag appearing in its own message) are
    dropped since they aren't a cross-agent edge.
    """
    edges = []  # list of (sender, mentioned_agent, message_id)
    mentioning_messages = 0

    for m in messages:
        sender = m["agent_id"]
        content = m.get("content") or ""
        tagged_roles = MENTION_TAG_RE.findall(content)
        mentioned = {
            ROLE_TO_AGENT[role] for role in tagged_roles if role in ROLE_TO_AGENT
        }
        mentioned.discard(sender)
        if mentioned:
            mentioning_messages += 1
        for agent in mentioned:
            edges.append((sender, agent, m["message_id"]))

    return edges, mentioning_messages


def build_matrix(edges):
    index = {a: i for i, a in enumerate(AGENTS)}
    matrix = [[0] * len(AGENTS) for _ in AGENTS]
    for sender, recipient, _ in edges:
        matrix[index[sender]][index[recipient]] += 1
    return matrix


def add_matrices(a, b):
    return [[a[i][j] + b[i][j] for j in range(len(AGENTS))] for i in range(len(AGENTS))]


def print_matrix(title, matrix):
    print(title)
    header = "".join(f"{AGENT_LABELS[a]:>24}" for a in AGENTS)
    row_label = "from / to"
    print(f"{row_label:>24}{header}")
    for i, a in enumerate(AGENTS):
        row = "".join(f"{matrix[i][j]:>24}" for j in range(len(AGENTS)))
        print(f"{AGENT_LABELS[a]:>24}{row}")
    print()


def main():
    messages = load_messages()

    reply_edges, unresolved = extract_edges(messages)
    reply_matrix = build_matrix(reply_edges)

    mention_edges, mentioning_messages = extract_mentions(messages)
    mention_matrix = build_matrix(mention_edges)

    combined_matrix = add_matrices(reply_matrix, mention_matrix)

    print(f"Total messages in dataset: {len(messages)}")
    print(f"Resolved direct-reply edges: {len(reply_edges)}")
    print(f"Unresolved (public posts / unaddressed DMs, excluded): {unresolved}")
    print(f"Messages containing an @ mention of another agent: {mentioning_messages}")
    print(f"Resolved @ mention edges: {len(mention_edges)}")
    print()
    print_matrix("-- Direct replies --", reply_matrix)
    print_matrix("-- @ Mentions --", mention_matrix)
    print_matrix("-- Combined --", combined_matrix)

    output = {
        "agents": AGENTS,
        "labels": [AGENT_LABELS[a] for a in AGENTS],
        "reply_matrix": reply_matrix,
        "mention_matrix": mention_matrix,
        "combined_matrix": combined_matrix,
        "reply_edges": [
            {"source": s, "target": t, "message_id": mid} for s, t, mid in reply_edges
        ],
        "mention_edges": [
            {"source": s, "target": t, "message_id": mid} for s, t, mid in mention_edges
        ],
        "meta": {
            "total_messages": len(messages),
            "resolved_reply_edges": len(reply_edges),
            "unresolved_messages": unresolved,
            "mentioning_messages": mentioning_messages,
            "resolved_mention_edges": len(mention_edges),
        },
    }
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
