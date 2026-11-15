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

# --- Budżet wywołań narzędzi (konfigurowalny) ---
DETAILER_MAX_CALLS = 12
IMPLEMENTER_MAX_CALLS = 20

# --- Narzędzia agentów (definiowane raz, wspólne dla implementera i detailera) ---
DETAILER_TOOLS = [tools.list_dir, tools.read_file, tools.search_files]
IMPLEMENTER_TOOLS = [
    tools.list_dir,
    tools.read_file,
    tools.write_file,
    tools.replace_in_file,
    tools.search_files,
    tools.run_command,
]

# --- Logowanie (diagnostyka; bezpieczne: redaguje i skraca) ---
_REDACT_KEYS = ("GITHUB_TOKEN", "GEMINI_API_KEY")


def redact(text: str) -> str:
    """Replace secret env var values with '***'."""
    try:
        for key in _REDACT_KEYS:
            value = os.environ.get(key)
            if value and value in text:
                text = text.replace(value, "***")
    except Exception:
        pass
    return text


def log(msg: str) -> None:
    """Print '[HH:MM:SS] msg', redacted, truncated, single line, always flushed."""
    try:
        text = redact(str(msg))
        text = text.replace("\n", " ⏎ ")
        if len(text) > 300:
            text = text[:300] + "..."
        print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)
    except Exception:
        pass


def group(name: str) -> None:
    """Open a GitHub Actions log group (plain line, always flushed)."""
    try:
        print(f"::group::{name}", flush=True)
    except Exception:
        pass


def endgroup() -> None:
    """Close a GitHub Actions log group."""
    try:
        print("::endgroup::", flush=True)
    except Exception:
        pass


def _usage(res) -> tuple:
    """(prompt, candidates, total) token counts via getattr; 0 when absent."""
    try:
        meta = getattr(res, "usage_metadata", None)
        if meta is None:
            return (0, 0, 0)
        return (
            int(getattr(meta, "prompt_token_count", 0) or 0),
            int(getattr(meta, "candidates_token_count", 0) or 0),
            int(getattr(meta, "total_token_count", 0) or 0),
        )
    except Exception:
        return (0, 0, 0)


def _finish_reason(res) -> str:
    """finish_reason of the first candidate; '' when there are no candidates."""
    try:
        candidates = getattr(res, "candidates", None)
        if not candidates:
            return ""
        return str(getattr(candidates[0], "finish_reason", "") or "")
    except Exception:
        return ""


def _afc_count(res) -> int:
    """Number of items in automatic_function_calling_history (0 if None)."""
    try:
        history = getattr(res, "automatic_function_calling_history", None)
        return len(history) if history else 0
    except Exception:
        return 0


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
                log("RETRY daily quota error, raising without retry")
                raise DailyQuotaError(str(e)) from e
            code = getattr(e, "code", None)
            if code in [429, 503]:
                sleep_for = 15 * (2 ** retries)
                log(f"RETRY {retries + 1}/5: code={code}, sleeping {sleep_for}s")
                time.sleep(sleep_for)
                retries += 1
                continue
            raise e
    raise Exception("Model call failed after retries")

def run_detailer(issue, client, detail_prompt: str) -> str:
    """Turn the issue into a precise spec and post it as a comment.

    Returns the spec text. DailyQuotaError propagates so main() can abort.
    Falls back to the raw issue text when the model returns no usable output.
    """
    user_msg = (
        f"ISSUE #{issue.number}: {issue.title}\n\n"
        f"OPIS:\n{issue.body or ''}"
    )

    log(f"DETAILER call start (max_calls={DETAILER_MAX_CALLS})")
    start = time.monotonic()
    response = call_with_retry(
        client.models.generate_content,
        model=MODEL,
        contents=user_msg,
        config=types.GenerateContentConfig(
            system_instruction=detail_prompt,
            tools=DETAILER_TOOLS,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=DETAILER_MAX_CALLS)
        )
    )
    elapsed = time.monotonic() - start
    p_tok, c_tok, t_tok = _usage(response)
    log(
        f"DETAILER call done in {elapsed:.2f}s finish_reason={_finish_reason(response) or 'none'} "
        f"afc_history={_afc_count(response)} tokens={p_tok}/{c_tok}/{t_tok}"
    )

    spec = (response.text or "").strip()

    if not spec:
        log("DETAILER empty spec after tool calling, retrying without tools")
        history = getattr(response, "automatic_function_calling_history", None)
        if history:
            retry_contents = list(history)
            retry_contents.append(
                "Write the specification now, based only on the issue text and what you "
                "already learned. Do not call any tools."
            )
        else:
            retry_contents = (
                user_msg
                + "\n\nWrite the specification now, based only on the issue text and what you "
                  "already learned. Do not call any tools."
            )

        retry_start = time.monotonic()
        retry_res = call_with_retry(
            client.models.generate_content,
            model=MODEL,
            contents=retry_contents,
            config=types.GenerateContentConfig(system_instruction=detail_prompt),
        )
        retry_elapsed = time.monotonic() - retry_start
        p_tok, c_tok, t_tok = _usage(retry_res)
        log(
            f"DETAILER retry done in {retry_elapsed:.2f}s "
            f"finish_reason={_finish_reason(retry_res) or 'none'} tokens={p_tok}/{c_tok}/{t_tok}"
        )
        spec = (retry_res.text or "").strip()
        if not spec:
            log("DETAILER retry also empty -> fallback to raw issue text")
            issue.create_comment(
                "⚠️ Detailer nie wygenerował specyfikacji — przechodzę do implementacji "
                "na podstawie treści issue."
            )
            return f"{issue.title}\n\n{issue.body or ''}"
        log(f"DETAILER retry produced spec ({len(spec)} chars)")
        branch = "retry without tools"
    else:
        branch = "spec posted"

    spec = spec[:60000]
    log(f"DETAILER branch={branch} spec_len={len(spec)}")
    issue.create_comment(
        f"### 📋 Specyfikacja od issue detailera\n\n**{issue.title}**\n\n{spec}"
    )
    return spec

def main() -> None:
    issue_number = int(os.environ["ISSUE_NUMBER"])
    gh = Github(os.environ["GITHUB_TOKEN"])
    repo = gh.get_repo(os.environ["GITHUB_REPOSITORY"])
    issue = repo.get_issue(number=issue_number)
    github_run_id = os.environ.get("GITHUB_RUN_ID", "local")

    client = genai.Client()
    impl_prompt = Path("factory/implementer.md").read_text(encoding="utf-8")
    rev_prompt = Path("factory/reviewer.md").read_text(encoding="utf-8")
    detail_prompt = Path("factory/issue_detailer.md").read_text(encoding="utf-8")

    review_feedback = ""
    last_failure_reason = ""
    max_attempts = 3

    body_len = len(issue.body or "")
    log(
        f"START issue=#{issue_number} run_id={github_run_id} model={MODEL} "
        f"body_len={body_len} max_attempts={max_attempts} "
        f"detailer_max={DETAILER_MAX_CALLS} implementer_max={IMPLEMENTER_MAX_CALLS}"
    )

    # Ensure repo is clean before starting
    run_git(["reset", "--hard", "HEAD"])
    log(f"BASE commit={run_git(['rev-parse', '--short', 'HEAD']).strip()}")

    # Spec from the issue detailer (skipped when the issue is already detailed)
    raw_issue_text = f"{issue.title}\n\n{issue.body or ''}"
    detail_spec = raw_issue_text
    if body_len > 1500:
        log(f"DETAILER skipped (body_len={body_len} > 1500)")
    else:
        group("DETAILER")
        try:
            detail_spec = run_detailer(issue, client, detail_prompt)
        except DailyQuotaError:
            endgroup()
            log("END STATE quota (detailer)")
            issue.create_comment("⚠️ **Dzienny limit quota Gemini został wyczerpany.** Spróbuj ponownie później.")
            return
        endgroup()

    for attempt in range(1, max_attempts + 1):
        group(f"ATTEMPT {attempt}")
        log(f"ATTEMPT {attempt}/{max_attempts}: IMPLEMENTER call start")
        print(f"\n=== PRÓBA {attempt}/{max_attempts}: IMPLEMENTER ===")
        
        system_msg = impl_prompt
        user_msg = (
            f"ISSUE #{issue.number}: {issue.title}\n\n"
            f"OPIS:\n{issue.body or ''}"
        )
        user_msg += f"\n\nSPEC OD ISSUE DETAILERA (wynik analizy, orientacyjny):\n{detail_spec}"
        if review_feedback:
            user_msg += f"\n\nUWAGI Z CODE REVIEW (DO POPRAWY):\n{review_feedback}"

        try:
            # Automatic tool calling
            impl_start = time.monotonic()
            response = call_with_retry(
                client.models.generate_content,
                model=MODEL,
                contents=user_msg,
                config=types.GenerateContentConfig(
                    system_instruction=system_msg,
                    tools=IMPLEMENTER_TOOLS,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=IMPLEMENTER_MAX_CALLS)
                )
            )
            impl_elapsed = time.monotonic() - impl_start
        except DailyQuotaError:
            endgroup()
            log("END STATE quota (implementer)")
            issue.create_comment("⚠️ **Dzienny limit quota Gemini został wyczerpany.** Spróbuj ponownie później.")
            return
        p_tok, c_tok, t_tok = _usage(response)
        log(
            f"ATTEMPT {attempt}: IMPLEMENTER done in {impl_elapsed:.2f}s "
            f"finish_reason={_finish_reason(response) or 'none'} afc_history={_afc_count(response)} "
            f"tokens={p_tok}/{c_tok}/{t_tok} text_len={len(response.text or '')}"
        )
        print(response.text)

        log(f"ATTEMPT {attempt}: REVIEWER call start")
        print(f"=== PRÓBA {attempt}/{max_attempts}: REVIEWER ===")
        
        # Prepare workspace for review
        run_git(["checkout", "HEAD", "--", "factory", ".github"])
        run_git(["clean", "-fd", "factory", ".github"])
        run_git(["add", "-A"])
        changed = [p for p in run_git(["diff", "--cached", "--name-only"]).splitlines() if p.strip()]
        git_diff = run_git(["diff", "--cached", "HEAD"])[:60000]
        log(
            f"WORKSPACE changed_files={len(changed)} first15={changed[:15]} "
            f"diff_chars={len(git_diff)} truncated={len(git_diff) >= 60000}"
        )

        if not git_diff.strip():
            review_feedback = "No changes were made"
            last_failure_reason = "no_changes"
            log(f"ATTEMPT {attempt}: no changes, reviewer skipped")
            print("No changes were made, skipping reviewer.")
            endgroup()
            continue

        rev_msg = (
            f"ISSUE #{issue.number}: {issue.title}\n\n"
            f"OPIS:\n{issue.body or ''}\n\n"
            f"SPEC OD ISSUE DETAILERA (wynik analizy, orientacyjny):\n{detail_spec}\n\n"
            f"GIT DIFF:\n{git_diff}"
        )

        try:
            rev_start = time.monotonic()
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
            rev_elapsed = time.monotonic() - rev_start
        except DailyQuotaError:
            endgroup()
            log("END STATE quota (reviewer)")
            issue.create_comment("⚠️ **Dzienny limit quota Gemini został wyczerpany.** Spróbuj ponownie później.")
            return

        p_tok, c_tok, t_tok = _usage(rev_res)
        if rev_res.parsed is None:
            log("REVIEWER parsed=None -> BLOCK (invalid output)")
            review = ReviewerResponse(verdict="BLOCK", feedback="Reviewer returned invalid output")
        else:
            review = cast(ReviewerResponse, rev_res.parsed)
        log(
            f"REVIEWER done in {rev_elapsed:.2f}s verdict={review.verdict} "
            f"feedback_len={len(review.feedback)} tokens={p_tok}/{c_tok}/{t_tok}"
        )

        print(f"Werdykt Reviewera: [{review.verdict}]")

        if review.verdict == "PASS":
            branch_name = f"agent/issue-{issue.number}-{github_run_id}"
            log(f"PASS branch={branch_name}")

            # Collect changed lines of pyproject.toml for the PR body
            pyproject_diff = run_git(["diff", "--cached", "HEAD", "--", "pyproject.toml"])
            dep_lines = [
                line for line in pyproject_diff.splitlines()
                if (line.startswith("+") or line.startswith("-"))
                and not line.startswith("+++") and not line.startswith("---")
            ]

            log(f"PASS pyproject_changed={bool(dep_lines)} dep_lines={len(dep_lines)}")

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
            log("PUSH start")
            run_git(["-c", "core.hooksPath=/dev/null", "push", "-u", "origin", branch_name])
            log("PUSH done")

            pr = repo.create_pull(
                title=f"Resolve #{issue.number}: {issue.title}",
                body=pr_body,
                head=branch_name,
                base=repo.default_branch,
            )
            log(f"PR created: {pr.html_url}")
            issue.create_comment(f"✅ **Gotowe!** Reviewer zaakceptował kod (`[PASS]`).\n\nPull Request do sprawdzenia: {pr.html_url}")
            endgroup()
            log("END STATE pass")
            return

        review_feedback = review.feedback
        last_failure_reason = "review_block"
        log(f"ATTEMPT {attempt}: BLOCK, feedback_len={len(review_feedback)}")
        print(f"Powód odrzucenia:\n{review_feedback}")
        endgroup()

    if last_failure_reason == "no_changes":
        log(f"END STATE no_changes after {max_attempts} attempts")
        issue.create_comment(
            f"❌ **Zatrzymano po {max_attempts} próbach.** Agent nie wprowadził żadnych zmian w żadnej próbie, więc Reviewer nie został wywołany."
        )
    else:
        log(f"END STATE review_block after {max_attempts} attempts")
        issue.create_comment(
            f"❌ **Zatrzymano po {max_attempts} próbach.** Reviewer nadal blokuje kod.\n\n"
            f"**Ostatnie uwagi:**\n{review_feedback}"
        )

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: {type(e).__name__}: {e}")
        raise