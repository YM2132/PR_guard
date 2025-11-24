# PR Guard 

**PR Guard** is a GitHub Action that uses an LLM to check whether a pull request author actually understands their own change.

It doesn’t try to detect or ban AI generated code. Instead, it:

- Generates three focused **questions about the diff**
- Makes the author answer them in plain language
- And then judges whether the answers show the author understands the code submitted

If they pass, the check goes green and humans can review. If not, the bot explains why and blocks until the author thinks a bit harder.

The **purpose is to add friction to PRs**, taking undue weight off the reviewer and giving junior developers a method to learn while doing AI assisted programming.

---

### Why?

AI-assisted development is great, but it also makes it easy to ship changes you don’t fully understand, **placing undue load on the reviewer to understand the code**:

- “Copilot wrote it, tests passed, ship it.”
- Reviewers get PRs with weak descriptions and no context
- Juniors (and tired seniors) can lean too hard on the model

PR Guard supports **responsible AI-assisted programming**:

> Use AI as much as you like — but if your name is on the PR, you should be able to explain what it does, what might break, and how you validated it.

***Cost***

Cost comes into the why, time of reviewers is not cheap whereas LLMs are becoming too cheap to meter. The default model, gpt-5-mini comes at a cost of $0.250 for 1M input tokens, for code that looks like:

| PR Size | Lines Changed | Estimated Cost |
|---------|--------------|----------------|
| Tiny | <50 lines | ~$0.001 |
| Small | 50-200 lines | ~$0.002 |
| Medium | 200-500 lines | ~$0.003-0.005 |
| Large | 500-1000 lines | ~$0.006-0.010 |
| Huge | >1000 lines | ~$0.015+ |

*Pricing changes over time — check OpenAI’s pricing page for exact numbers.</text>

---

### What it does

On every pull request:

1. PR Guard reads the git diff.
2. It asks an OpenAI model to generate **3 concrete questions** about:
   - Why this change exists
   - What can go wrong
   - How it was tested
3. It posts those questions as a PR comment: **“PR Understanding Check”**.
4. The job fails until the author replies with a comment starting with:

   ```text
   /answers

   followed by their answers in plain language.
   ```

5. On the next run, PR Guard:
    - Reads the diff, the questions, and the /answers comment,
    - Asks the model to decide PASS or FAIL based on whether the answers show understanding,
    - Posts a result comment with the decision and a short reason,
    - Exits 0 (PASS) or 1 (FAIL) accordingly.

You can make this job a **required check** before merging.

---

### Quickstart

You need:

- GitHub Actions enabled on your repo
- An OpenAI API key

### 1. Add your OpenAI key as a secret

In your target repo:

1. Go to **Settings → Secrets and variables → Actions → New repository secret**
    - Name: `PR_GUARD_OPENAI_API_KEY` - Secret: your OpenAI API key

### 2. Add the PR Guard workflow

Create `.github/workflows/pr-guard.yml`:

```yaml
name: PR Guard

on:
  pull_request:
    types: [opened, reopened, synchronize, edited]

jobs:
  pr-guard:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write

    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Run PR Guard
        uses: YM2132/PR_guard@v0.1.0 
        with:
          openai_api_key: ${{ secrets.PR_GUARD_OPENAI_API_KEY }}
          # model:  # optional model override - default model is gpt-5-mini, you are free to use any OpenAI model
```

Commit and push this to your default branch. Open a PR and you should see:

    - A “PR Understanding Check” comment with questions
    - A failing check until you reply with /answers ...
    - A follow-up “PR Guard Result: PASS/FAIL” comment once it evaluates your answers

That’s all you need to start using PR Guard!

---

### FAQ

Is there an override?
- Yes, this is not a hard and fast rule. It is up to the maintainers to assert how pr-guard is to be used. In case of failure of the tool to work properly, a reviewer could choose to ignore the status of pr-guard

Can I re-author a /answers comment if it fails?
- Yes, you can change your answers and then restart the failed job

Can't someone just use AI to answer the questions?
- Yes, and that's okay. PR Guard is not trying to ban AI — it's trying to make AI-assisted work more responsible. Even if answers are AI-assisted, the author still has to read and submit them, which forces a brief pause to consider the change, the risks, and the tests. Like any trust-based system, it can't guarantee zero AI, but it raises the bar and nudges people toward actually engaging with their own PRs

### Roadmap

1. Increase developer configurability 
    - Minimum diff length for pr_guard to activate
    - Let developers edit the prompt, tailoring it to their needs
    - Add strictness parameter
