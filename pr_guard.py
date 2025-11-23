#!/usr/bin/env python
import os
import sys
import json
import subprocess
import requests
import re

from typing import Literal
from pydantic import BaseModel
from openai import OpenAI

QUESTIONS_MARKER = "pr-guard:questions"
RESULT_MARKER = "pr-guard:result"

def get_openai_api_key() -> str:
    key = (
        os.environ.get("PR_GUARD_OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    if not key:
        raise RuntimeError(
            "No OpenAI API key found. "
            "Set PR_GUARD_OPENAI_API_KEY or OPENAI_API_KEY."
        )
    return key

def load_github_event():
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        raise RuntimeError("GITHUB_EVENT_PATH not set.")
    with open(event_path, "r", encoding="utf-8") as event_file:
        return json.load(event_file)

def get_pr_context(event_json):
    pr = event_json.get("pull_request")
    if not pr:
        raise RuntimeError("This action must run on a pull request event.")

    return {
        "repo": os.environ["GITHUB_REPOSITORY"],  # "owner/repo"
        "pr_number": event_json["number"],
        "base_sha": pr["base"]["sha"],
        "head_sha": pr["head"]["sha"],
    }

def get_diff(base_sha: str, head_sha: str) -> str:
    result = subprocess.run(
        ["git", "diff", f"{base_sha}...{head_sha}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout

def github_headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

def list_comments(repo: str, pr_number: int) -> list[dict]:
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    resp = requests.get(url, headers=github_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()

def post_comment(repo: str, pr_number: int, body: str) -> None:
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    resp = requests.post(
        url,
        headers=github_headers(),
        json={"body": body},
        timeout=30,
    )
    resp.raise_for_status()

def call_llm_structured(
    messages: list[dict[str, str]],
    response_model: type[BaseModel],
    model: str | None = None,
):
    if model is None:
        model = os.environ.get("OPENAI_MODEL", "gpt-5-mini")

    completion = client.chat.completions.parse(
        model=model,
        messages=messages,
        response_format=response_model,
    )

    message = completion.choices[0].message

    # If model refuses, treat it as an error for now
    if getattr(message, "refusal", None):
        raise RuntimeError(f"Model refused to answer: {message.refusal}")

    # This is an instance of `response_model`
    return message.parsed

def generate_questions(diff: str) -> list[str]:
    system_msg = (
        "You help review pull requests. Your goal is to ensure the developer understands the code they have written.\n"
        "Given a git diff, write 3 short, concrete questions that probe:\n"
        "- why the change is made,\n"
        "- what can go wrong,\n"
        "- how it was validated.\n"
        "Avoid trivial questions that just restate obvious diffs."
    )
    user_msg = f"Here is the git diff:\n```diff\n{diff}\n```"

    parsed: QuestionsOutput = call_llm_structured(
        [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        QuestionsOutput,
    )

    # Clean up whitespace, just in case
    return [q.strip() for q in parsed.questions if q.strip()]


class QuestionsOutput(BaseModel):
    questions: list[str]

class EvaluationOutput(BaseModel):
    decision: Literal["PASS", "FAIL"]
    reason: str

def render_questions_comment(questions: list[str]) -> str:
    json_blob = json.dumps({"questions": questions}, ensure_ascii=False)
    lines = [
        "### PR Understanding Check",
        "",
        "Please reply with a comment that starts with `/answers` and answer these questions in plain language.",
        "",
    ]
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {q}")
    lines.append("")
    lines.append("<!-- " + QUESTIONS_MARKER)
    lines.append(json_blob)
    lines.append("-->")
    return "\n".join(lines)


def find_questions_comment(comments: list[dict]) -> dict | None:
    for c in reversed(comments):  # newest first
        body = c.get("body") or ""
        if QUESTIONS_MARKER in body:
            return c
    return None


def extract_questions_from_comment(comment: dict) -> list[str]:
    body = comment.get("body") or ""
    m = re.search(
        r"<!--\s*" + re.escape(QUESTIONS_MARKER) + r"\s*(\{.*?\})\s*-->",
        body,
        re.DOTALL,
    )
    if not m:
        raise RuntimeError("Failed to find embedded questions JSON in comment body")

    data = json.loads(m.group(1))
    questions = data.get("questions")
    if not isinstance(questions, list):
        raise RuntimeError("Embedded JSON does not contain 'questions' list")

    return [str(q).strip() for q in questions if str(q).strip()]

def find_answers_comment(comments: list[dict]) -> dict | None:
    for c in reversed(comments):  # newest first
        body = (c.get("body") or "").strip()
        if body.startswith("/answers"):
            return c
    return None

def evaluate_answers(diff: str, questions: list[str], answers_text: str) -> dict:
    system_msg = (
        "You evaluate whether a pull request author appears to understand THEIR OWN change.\n"
        "You are given a git diff, some questions about the diff, and the author's answers.\n"
        "\n"
        "Your job is NOT to judge whether the change is ideal engineering practice.\n"
        "Your job IS to judge whether the author:\n"
        "- refers concretely to the code and behavior in the diff,\n"
        "- addresses the specific questions in a reasonably direct way,\n"
        "- and shows some awareness of tradeoffs or limitations (even if they accept them).\n"
        "\n"
        "Use these rules:\n"
        "- PASS if the answers clearly reference the actual code and show some thought about behavior, risks, or testing, "
        "even if the design or justification is simple or acknowledges shortcuts.\n"
        "- PASS if the author explicitly acknowledges limitations or context (e.g. 'this is a throwaway script', "
        "'we know it's not thread-safe but it's only used in a single-process tool').\n"
        "- FAIL only if the answers are mostly generic, ignore the questions, contradict the diff, "
        "or clearly indicate the author has not actually looked at the code or considered its behavior.\n"
        "- When in doubt, especially for very small or toy diffs, prefer PASS and mention any concerns in the reason."
    )

    user_msg = (
        "Git diff:\n"
        f"```diff\n{diff}\n```\n\n"
        f"Questions:\n{json.dumps(questions, ensure_ascii=False)}\n\n"
        f"Author's `/answers` comment:\n{answers_text}\n"
    )

    parsed: EvaluationOutput = call_llm_structured(
        [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        EvaluationOutput,
    )

    return {"decision": parsed.decision, "reason": parsed.reason}

def find_result_comment(comments: list[dict]) -> dict | None:
    for c in reversed(comments):  # newest first
        body = c.get("body") or ""
        if RESULT_MARKER in body:
            return c
    return None

def update_comment(repo: str, comment_id: int, body: str) -> None:
    url = f"https://api.github.com/repos/{repo}/issues/comments/{comment_id}"
    resp = requests.patch(
        url,
        headers=github_headers(),
        json={"body": body},
        timeout=30,
    )
    resp.raise_for_status()


client = OpenAI(api_key=get_openai_api_key())

def main() -> None:
    # TODO:
    # 1. Load GitHub event JSON from GITHUB_EVENT_PATH
    # 2. Extract PR info (base SHA, head SHA)
    # 3. Compute git diff
    # 4. Fetch PR comments via GitHub API
    # 5. If no questions yet:
    #    - Call OpenAI to generate questions
    #    - Post a comment with questions
    #    - exit(1)
    # 6. Else:
    #    - Look for `/answers` comment
    #    - Call OpenAI to evaluate answers
    #    - exit(0) or exit(1)
    try:
        # Ensure API key works
        get_openai_api_key()
        print("OpenAI API key found. PR guard will run here.")

        event_json = load_github_event()
        ctx = get_pr_context(event_json)
        print("PR context:", ctx)

        diff = get_diff(ctx["base_sha"], ctx["head_sha"])
        print("Diff length:", len(diff))

        comments = list_comments(ctx["repo"], ctx["pr_number"])
        print(f"Existing comments: {len(comments)}")

        q_comment = find_questions_comment(comments)

        if q_comment is None:
            # First run for this PR: generate questions and fail the check
            questions = generate_questions(diff)
            body = render_questions_comment(questions)
            post_comment(ctx["repo"], ctx["pr_number"], body)
            print("Posted PR understanding questions. Waiting for /answers comment.")
            sys.exit(1)

        # We already have a questions comment; extract questions
        questions = extract_questions_from_comment(q_comment)

        # Look for an /answers comment
        answers_comment = find_answers_comment(comments)
        if answers_comment is None:
            print("Questions exist but no `/answers` comment found yet.")
            sys.exit(1)

        evaluation = evaluate_answers(diff, questions, answers_comment["body"])
        print(f"LLM decision: {evaluation['decision']}")
        print(f"Reason: {evaluation['reason']}")

        # Build result comment body, with a hidden marker so we can find/update it
        result_comment_body = (
            f"### PR Guard Result: **{evaluation['decision']}**\n\n"
            f"{evaluation['reason']}\n\n"
            f"<!-- {RESULT_MARKER} -->"
        )

        existing_result = find_result_comment(comments)
        if existing_result is None:
            post_comment(ctx["repo"], ctx["pr_number"], result_comment_body)
            print("Posted PR Guard result comment.")
        else:
            update_comment(ctx["repo"], existing_result["id"], result_comment_body)
            print("Updated existing PR Guard result comment.")

        if evaluation["decision"] == "PASS":
            sys.exit(0)
        else:
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
