import os
import subprocess
import time
from pathlib import Path
from typing import Literal, cast

from github import Github
from google import genai
from google.genai import types
from pydantic import BaseModel
import factory.tools as tools

MODEL = "gemini-3.5-flash-lite"

# --- Kontrakty JSON (Structured Outputs) ---
class ReviewerResponse(BaseModel):
    verdict: Literal["PASS", "BLOCK"]
    feedback: str

class DailyQuotaError(Exception):
    pass

def run_git(args: list[str]) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {r.stderr[-500:]}")
    return r.stdout

def call_with_retry(fn, *args, **kwargs):
    retries = 0
    while retries < 5:
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            msg = str(e).lower()
            if "quota" in msg and ("day" in msg or "daily" in msg):
                raise DailyQuotaError(str(e)) from e
            if hasattr(e, 'code') and e.code in [429, 503]:
                time.sleep(15 * (2 ** retries))
                retries += 1
                continue
            raise e
    raise Exception("Model call failed after retries")

def main() -> None:
    issue_number = int(os.environ["ISSUE_NUMBER"])
    gh = Github(os.environ["GITHUB_TOKEN"])
    repo = gh.get_repo(os.environ["GITHUB_REPOSITORY"])
    issue = repo.get_issue(number=issue_number)
    github_run_id = os.environ.get("GITHUB_RUN_ID", "local")

    client = genai.Client()
    impl_prompt = Path("factory/implementer.md").read_text(encoding="utf-8")
    rev_prompt = Path("factory/reviewer.md").read_text(encoding="utf-8")

    review_feedback = ""
    last_failure_reason = ""
    max_attempts = 3

    # Ensure repo is clean before starting
    run_git(["reset", "--hard", "HEAD"])

    for attempt in range(1, max_attempts + 1):
        print(f"\n=== PRÓBA {attempt}/{max_attempts}: IMPLEMENTER ===")
        
        system_msg = impl_prompt
        user_msg = (
            f"ISSUE #{issue.number}: {issue.title}\n\n"
            f"OPIS:\n{issue.body or ''}"
        )
        if review_feedback:
            user_msg += f"\n\nUWAGI Z CODE REVIEW (DO POPRAWY):\n{review_feedback}"

        try:
            # Automatic tool calling
            response = call_with_retry(
                client.models.generate_content,
                model=MODEL,
                contents=user_msg,
                config=types.GenerateContentConfig(
                    system_instruction=system_msg,
                    tools=[tools.list_dir, tools.read_file, tools.write_file, tools.replace_in_file, tools.search_files, tools.run_command],
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=20)
                )
            )
        except DailyQuotaError:
            issue.create_comment("⚠️ **Dzienny limit quota Gemini został wyczerpany.** Spróbuj ponownie później.")
            return
        print(response.text)

        print(f"=== PRÓBA {attempt}/{max_attempts}: REVIEWER ===")
        
        # Prepare workspace for review
        run_git(["checkout", "HEAD", "--", "factory", ".github"])
        run_git(["clean", "-fd", "factory", ".github"])
        run_git(["add", "-A"])
        git_diff = run_git(["diff", "--cached", "HEAD"])[:60000]

        if not git_diff.strip():
            review_feedback = "No changes were made"
            last_failure_reason = "no_changes"
            print("No changes were made, skipping reviewer.")
            continue

        rev_msg = (
            f"ISSUE #{issue.number}: {issue.title}\n\n"
            f"OPIS:\n{issue.body or ''}\n\n"
            f"GIT DIFF:\n{git_diff}"
        )

        try:
            rev_res = call_with_retry(
                client.models.generate_content,
                model=MODEL,
                contents=rev_msg,
                config=types.GenerateContentConfig(
                    system_instruction=rev_prompt,
                    response_mime_type="application/json",
                    response_schema=ReviewerResponse,
                ),
            )
        except DailyQuotaError:
            issue.create_comment("⚠️ **Dzienny limit quota Gemini został wyczerpany.** Spróbuj ponownie później.")
            return
        
        if rev_res.parsed is None:
            review = ReviewerResponse(verdict="BLOCK", feedback="Reviewer returned invalid output")
        else:
            review = cast(ReviewerResponse, rev_res.parsed)

        print(f"Werdykt Reviewera: [{review.verdict}]")

        if review.verdict == "PASS":
            branch_name = f"agent/issue-{issue.number}-{github_run_id}"

            # Collect changed lines of pyproject.toml for the PR body
            pyproject_diff = run_git(["diff", "--cached", "HEAD", "--", "pyproject.toml"])
            dep_lines = [
                line for line in pyproject_diff.splitlines()
                if (line.startswith("+") or line.startswith("-"))
                and not line.startswith("+++") and not line.startswith("---")
            ]

            pr_body = f"Closes #{issue.number}\n\nStatus Review: `[PASS]`"
            if dep_lines:
                pr_body += (
                    "\n\n### Dependency changes (review carefully)\n```diff\n"
                    + "\n".join(dep_lines)
                    + "\n```"
                )

            # Use token for auth
            token = os.environ["GITHUB_TOKEN"]
            repo_url = f"https://x-access-token:{token}@github.com/{os.environ['GITHUB_REPOSITORY']}.git"
            
            run_git(["remote", "set-url", "origin", repo_url])
            run_git(["config", "user.name", "Software Factory Bot"])
            run_git(["config", "user.email", "bot@users.noreply.github.com"])
            run_git(["checkout", "-b", branch_name])
            run_git(["add", "."])
            run_git(["-c", "core.hooksPath=/dev/null", "commit", "--no-verify", "-m", f"feat: resolve #{issue.number}"])
            run_git(["-c", "core.hooksPath=/dev/null", "push", "-u", "origin", branch_name])

            pr = repo.create_pull(
                title=f"Resolve #{issue.number}: {issue.title}",
                body=pr_body,
                head=branch_name,
                base=repo.default_branch,
            )
            issue.create_comment(f"✅ **Gotowe!** Reviewer zaakceptował kod (`[PASS]`).\n\nPull Request do sprawdzenia: {pr.html_url}")
            return

        review_feedback = review.feedback
        last_failure_reason = "review_block"
        print(f"Powód odrzucenia:\n{review_feedback}")

    if last_failure_reason == "no_changes":
        issue.create_comment(
            f"❌ **Zatrzymano po {max_attempts} próbach.** Agent nie wprowadził żadnych zmian w żadnej próbie, więc Reviewer nie został wywołany."
        )
    else:
        issue.create_comment(
            f"❌ **Zatrzymano po {max_attempts} próbach.** Reviewer nadal blokuje kod.\n\n"
            f"**Ostatnie uwagi:**\n{review_feedback}"
        )

if __name__ == "__main__":
    main()