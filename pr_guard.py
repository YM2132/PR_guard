#!/usr/bin/env python
import os
import sys


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
        _ = get_openai_api_key()
        print("OpenAI API key found. PR guard will run here.")
        # Placeholder for now:
        # Just fail so you can see the check in GitHub.
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
