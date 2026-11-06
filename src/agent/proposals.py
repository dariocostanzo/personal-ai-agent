"""Human-reviewed, explicitly allow-listed self-improvement proposals."""

import json

from src.agent import agent_state, guardians, news

ALLOWED_KINDS = {"news_source", "guardian_check", "assistant_prompt"}


def propose(kind, title, details="", payload=None):
    if not isinstance(kind, str) or kind not in ALLOWED_KINDS:
        raise ValueError("Unsupported proposal type.")
    title = title.strip() if isinstance(title, str) else ""
    details = details.strip() if isinstance(details, str) else ""
    if not title or len(title) > 200 or len(details) > 2000:
        raise ValueError("Proposal title and details are required and must be within limits.")
    payload = {} if payload is None else payload
    if not isinstance(payload, dict):
        raise ValueError("Proposal payload must be an object.")
    return agent_state.add_proposal(kind, title, details, payload)


def list_proposals():
    return agent_state.list_proposals()


def suggest():
    from src.agent import goals, interests, providers

    snapshot = {
        "news_sources": [
            {"name": source["name"], "kind": source["kind"],
             "has_error": bool(source["last_error"])}
            for source in news.list_sources()
        ],
        "guardian_checks": [
            {"name": check["name"], "status": check["status"]}
            for check in agent_state.latest_guardian_checks()
        ],
        "interests": [
            {"topic": item["topic"], "weight": item["weight"]}
            for item in interests.list_interests()["interests"]
        ],
        "active_goals": [
            goal["title"] for goal in goals.list_goals(include_completed=False)
        ],
    }
    response = providers.complete([
        {
            "role": "system",
            "content": (
                "Propose up to three small, safe improvements to this personal agent. "
                "Return only a JSON array with objects containing kind, title, details, "
                "payload. Allowed kinds: news_source (payload: name, kind, location), "
                "guardian_check (payload: name, url), assistant_prompt (payload: prompt). "
                "Do not propose code execution, secrets, or automatic external actions. "
                "Only suggest a source URL when you know a valid public URL."
            ),
        },
        {"role": "user", "content": json.dumps(snapshot, ensure_ascii=False)},
    ], capability="self_improvement")
    try:
        suggestions = json.loads(response)
    except json.JSONDecodeError as error:
        raise ValueError("The configured model did not return valid proposal JSON.") from error
    if not isinstance(suggestions, list) or not 1 <= len(suggestions) <= 3:
        raise ValueError("The model must return between one and three proposals.")
    validated = []
    for item in suggestions:
        if not isinstance(item, dict):
            raise ValueError("Each model proposal must be a JSON object.")
        kind, title = item.get("kind"), item.get("title")
        details, payload = item.get("details", ""), item.get("payload", {})
        if not isinstance(kind, str) or kind not in ALLOWED_KINDS or not isinstance(title, str):
            raise ValueError("The model returned an unsupported proposal.")
        if not isinstance(details, str) or not isinstance(payload, dict):
            raise ValueError("Proposal details and payload have invalid types.")
        if not title.strip() or len(title.strip()) > 200 or len(details.strip()) > 2000:
            raise ValueError("The model returned a proposal outside the allowed text limits.")
        validated.append((kind, title, details, payload))
    return [
        agent_state.get_proposal(
            propose(kind, title, details, payload)
        )
        for kind, title, details, payload in validated
    ]


def review(proposal_id, decision, title=None, details=None, payload=None):
    if decision not in ("accepted", "rejected"):
        raise ValueError("Proposal decision must be accepted or rejected.")
    proposal = agent_state.get_proposal(proposal_id)
    if not proposal or proposal["status"] != "pending":
        return False
    if payload is not None and not isinstance(payload, dict):
        raise ValueError("Proposal payload must be an object.")
    final_title = title.strip() if isinstance(title, str) else proposal["title"]
    final_details = details.strip() if isinstance(details, str) else proposal["details"]
    final_payload = payload if payload is not None else proposal["payload"]
    if not final_title or len(final_title) > 200 or len(final_details) > 2000:
        raise ValueError("Proposal title and details must be within limits.")

    if decision == "accepted":
        if proposal["kind"] == "news_source":
            news.add_source(final_payload.get("name", final_title),
                            final_payload.get("kind"), final_payload.get("location"))
        elif proposal["kind"] == "guardian_check":
            guardians.add_service(final_payload.get("name", final_title),
                                  final_payload.get("url"))
        elif proposal["kind"] == "assistant_prompt":
            prompt = final_payload.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
                raise ValueError("Accepted assistant prompts must contain 1-4000 characters.")
            with agent_state.connect() as connection:
                connection.execute(
                    "INSERT INTO agent_settings (key, value) VALUES ('assistant_prompt', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                    "updated_at = CURRENT_TIMESTAMP",
                    (prompt.strip(),),
                )
    reviewed = agent_state.review_proposal(
        proposal_id, decision, final_title, final_details, final_payload
    )
    if reviewed:
        agent_state.add_decision(
            "proposal_" + decision, final_title,
            "Proposal was " + decision + " after human review.",
            {"kind": proposal["kind"]},
        )
    return reviewed


def decode_payload(value):
    return json.loads(value)
