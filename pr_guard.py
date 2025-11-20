#!/usr/bin/env python
import os
import sys
import json
import subprocess
import requests
from openai import OpenAI

def get_openai_api_key() -> None:
    key = (
        os.environ.get("PR_GUARD_OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    if not key:
        raise RuntimeError(
            "No OpenAI API key found. "
            "Set PR_GUARD_OPENAI_API_KEY or OPENAI_API_KEY."
        )
    return None

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

def call_llm(messages: list[str], model: str | None = None) -> str:
    if model is None:
        model = os.environ.get("OPENAI_MODEL", "gpt-5-mini")

    client = OpenAI(api_key=os.environ["PR_UNDERSTANDING_OPENAI_API_KEY"])
    completion = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "developer", "content": f"{messages[0]}"},
            {"role": "user", "content": f"{messages[1]}"},
        ]
    )

    return completion["choices"][0]["message"]["content"]

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
        # Try to get OpenAI API to check it exists
        get_openai_api_key()
        print("OpenAI API key found. PR guard will run here.")

        event_json = load_github_event()
        ctx = get_pr_context(event_json)
        print("PR context:", ctx)

        diff = get_diff(ctx["base_sha"], ctx["head_sha"])
        print("Diff length:", len(diff))
        print(diff[:500])

        # sanity check if we can fetch comments
        comments = list_comments(ctx["repo"], ctx["pr_number"])
        print(f"Existing comments: {len(comments)}")

        # Post a test comment
        post_comment(ctx["repo"], ctx["pr_number"], "Hello from pr_guard.py :wave:")
        print("Posted test comment.")

        msg = call_llm(
            [
                "You say hi in one short sentence.",
                "Say hi to the PR author.",
            ]
        )
        print("LLM replied:", msg)

        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
