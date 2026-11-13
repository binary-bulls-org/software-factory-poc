import os
import subprocess
import time
from pathlib import Path
from typing import Literal

from github import Github
from google import genai
from google.genai import types
from pydantic import BaseModel


# --- Kontrakty JSON (Structured Outputs) ---
class FileOutput(BaseModel):
    path: str
    content: str


class ImplementerResponse(BaseModel):
    summary: str
    files: list[FileOutput]


class ReviewerResponse(BaseModel):
    verdict: Literal["PASS", "BLOCK"]
    feedback: str


# --- Narzędzia pomocnicze ---
def read_repo_files() -> str:
    """Zbiera obecne pliki projektu (z pominięciem plików samej fabryki)."""
    ignored_dirs = {".git", ".github", "factory", ".venv", "__pycache__"}
    chunks = []
    for path in Path(".").rglob("*"):
        if path.is_file() and not any(part in ignored_dirs for part in path.parts):
            if path.name in {"uv.lock", "pyproject.toml"}:
                continue
            try:
                chunks.append(f"--- FILE: {path} ---\n{path.read_text(encoding='utf-8')}")
            except UnicodeDecodeError:
                pass
    return "\n\n".join(chunks) if chunks else "(Repozytorium jest na razie puste)"


def run_git(args: list[str]) -> None:
    subprocess.run(["git", *args], check=True)


def main() -> None:
    issue_number = int(os.environ["ISSUE_NUMBER"])
    gh = Github(os.environ["GITHUB_TOKEN"])
    repo = gh.get_repo(os.environ["GITHUB_REPOSITORY"])
    issue = repo.get_issue(number=issue_number)

    client = genai.Client()  # Pobiera GEMINI_API_KEY automatycznie z env
    impl_prompt = Path("factory/implementer.md").read_text(encoding="utf-8")
    rev_prompt = Path("factory/reviewer.md").read_text(encoding="utf-8")

    repo_context = read_repo_files()
    review_feedback = ""
    last_impl: ImplementerResponse | None = None
    max_attempts = 3  # 1 pierwsza próba + max 2 poprawki po uwagach Reviewera

    for attempt in range(1, max_attempts + 1):
        print(f"\n=== PRÓBA {attempt}/{max_attempts}: IMPLEMENTER ===")
        time.sleep(4)  # Ochrona przed limitem zapytań na minutę (Free Tier)

        user_msg = (
            f"ISSUE #{issue.number}: {issue.title}\n\n"
            f"OPIS:\n{issue.body or ''}\n\n"
            f"OBECNE PLIKI W REPO:\n{repo_context}"
        )
        if review_feedback and last_impl:
            prev_files = "\n\n".join(f"--- {f.path} ---\n{f.content}" for f in last_impl.files)
            user_msg += (
                f"\n\nPOPRZEDNIA WERSJA KODU:\n{prev_files}\n\n"
                f"UWAGI Z CODE REVIEW (DO POPRAWY):\n{review_feedback}"
            )

        impl_res = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=user_msg,
            config=types.GenerateContentConfig(
                system_instruction=impl_prompt,
                response_mime_type="application/json",
                response_schema=ImplementerResponse,
            ),
        )
        last_impl = impl_res.parsed
        print(f"Implementer wygenerował {len(last_impl.files)} plik(ów): {last_impl.summary}")

        print(f"=== PRÓBA {attempt}/{max_attempts}: REVIEWER ===")
        time.sleep(4)

        proposed_code = "\n\n".join(f"--- {f.path} ---\n{f.content}" for f in last_impl.files)
        rev_msg = (
            f"ISSUE #{issue.number}: {issue.title}\n\n"
            f"OPIS:\n{issue.body or ''}\n\n"
            f"PROPONOWANY KOD DO OCENY:\n{proposed_code}"
        )

        rev_res = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=rev_msg,
            config=types.GenerateContentConfig(
                system_instruction=rev_prompt,
                response_mime_type="application/json",
                response_schema=ReviewerResponse,
            ),
        )
        review: ReviewerResponse = rev_res.parsed
        print(f"Werdykt Reviewera: [{review.verdict}]")

        if review.verdict == "PASS":
            # Zapis bezpiecznych plików na dysk
            for f in last_impl.files:
                target = Path(f.path)
                if target.parts[0] in {"factory", ".github", ".git"}:
                    raise PermissionError(f"Agent próbował nadpisać chronioną ścieżkę: {target}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f.content, encoding="utf-8")

            # Git branch -> commit -> push -> PR
            branch_name = f"agent/issue-{issue.number}"
            run_git(["config", "user.name", "Software Factory Bot"])
            run_git(["config", "user.email", "bot@users.noreply.github.com"])
            run_git(["checkout", "-b", branch_name])
            run_git(["add", "."])
            run_git(["commit", "-m", f"feat: resolve #{issue.number}"])
            run_git(["push", "-u", "origin", branch_name])

            pr = repo.create_pull(
                title=f"Resolve #{issue.number}: {issue.title}",
                body=f"Closes #{issue.number}\n\n### Podsumowanie zmian\n{last_impl.summary}\n\n### Status Review\n`[PASS]` — zatwierdzone przez AI Reviewera.",
                head=branch_name,
                base=repo.default_branch,
            )
            issue.create_comment(f"✅ **Gotowe!** Reviewer zaakceptował kod (`[PASS]`).\n\nPull Request do sprawdzenia: {pr.html_url}")
            return

        review_feedback = review.feedback
        print(f"Powód odrzucenia:\n{review_feedback}")

    # Jeśli wyczerpano limit prób
    issue.create_comment(
        f"❌ **Zatrzymano po {max_attempts} próbach.** Reviewer nadal blokuje kod.\n\n"
        f"**Ostatnie uwagi:**\n{review_feedback}"
    )


if __name__ == "__main__":
    main()