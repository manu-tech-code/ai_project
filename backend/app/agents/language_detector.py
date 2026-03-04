"""
Agent 1: LanguageDetector

Scans the repository and identifies all programming languages present.
Detects frameworks based on dependency files (pom.xml, composer.json, etc.).

Output:
  - Updates jobs.languages, jobs.file_count, jobs.total_lines
  - Returns list[LanguageInfo]
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import update

from app.agents.base import BaseAgent, JobContext
from app.models.job import Job

# Extension to language mapping
EXTENSION_MAP: dict[str, str] = {
    ".java": "java",
    ".py": "python",
    ".php": "php",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mjs": "javascript",
    ".cjs": "javascript",
}

# Directories to skip during traversal
SKIP_DIRS: set[str] = {
    "node_modules", "vendor", ".git", "__pycache__",
    ".venv", "venv", "env", "dist", "build", "target",
    ".idea", ".vscode", "coverage", ".tox", "htmlcov",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}


@dataclass
class LanguageInfo:
    language: str
    file_count: int = 0
    total_lines: int = 0
    file_extensions: list[str] = field(default_factory=list)
    frameworks_detected: list[str] = field(default_factory=list)


class LanguageDetectorAgent(BaseAgent):
    """
    Scans the repository tree and identifies languages and frameworks.
    No LLM calls. No external services.
    """

    stage_name = "detecting"

    async def run(self, context: JobContext) -> dict:
        """
        Walk the repo directory, classify files by extension,
        detect frameworks from manifest files, and update the job record.
        """
        language_map: dict[str, LanguageInfo] = {}
        total_file_count = 0

        for path in self._walk(context.repo_path):
            total_file_count += 1
            ext = path.suffix.lower()
            lang = EXTENSION_MAP.get(ext)
            if lang:
                if lang not in language_map:
                    language_map[lang] = LanguageInfo(language=lang)
                info = language_map[lang]
                info.file_count += 1
                if ext not in info.file_extensions:
                    info.file_extensions.append(ext)
                try:
                    info.total_lines += self._count_lines(path)
                except (OSError, UnicodeDecodeError):
                    pass

        # Detect frameworks from manifest files
        self._detect_frameworks(context.repo_path, language_map)

        # Also check package manager files that imply languages
        self._detect_from_manifests(context.repo_path, language_map)

        # Sort languages by file count (descending)
        sorted_langs = sorted(
            language_map.values(), key=lambda x: x.file_count, reverse=True
        )

        dominant = sorted_langs[0].language if sorted_langs else None
        total_lines = sum(v.total_lines for v in language_map.values())

        # Update context with detected languages
        context.languages = [v.language for v in sorted_langs]

        # Persist results to the jobs table
        await self._persist_results(context, language_map, total_file_count, total_lines)

        self.logger.info(
            "[%s] Detected languages: %s (dominant: %s, files: %d, lines: %d)",
            context.job_id, context.languages, dominant, total_file_count, total_lines,
        )

        return {
            "languages": [vars(v) for v in sorted_langs],
            "dominant": dominant,
            "total_files": total_file_count,
            "total_lines": total_lines,
            "file_counts": {v.language: v.file_count for v in sorted_langs},
        }

    async def _persist_results(
        self,
        context: JobContext,
        language_map: dict[str, LanguageInfo],
        total_files: int,
        total_lines: int,
    ) -> None:
        """Update the job record with language detection results."""
        try:
            sorted_langs = sorted(
                language_map.keys(),
                key=lambda k: language_map[k].file_count,
                reverse=True,
            )
            stmt = (
                update(Job)
                .where(Job.id == context.job_id)
                .values(
                    languages=sorted_langs,
                    file_count=total_files if total_files > 0 else None,
                    total_lines=total_lines if total_lines > 0 else None,
                    updated_at=datetime.now(UTC),
                )
            )
            await context.db_session.execute(stmt)
            await context.db_session.commit()
        except Exception as exc:
            self.logger.error(
                "[%s] Failed to persist language detection results: %s",
                context.job_id, exc,
            )

    def _walk(self, root: Path):
        """Yield all non-binary source files, skipping known vendor dirs."""
        for item in root.rglob("*"):
            if item.is_file():
                # Skip if any path component is in the skip set
                if any(part in SKIP_DIRS for part in item.parts):
                    continue
                # Skip hidden directories (starting with '.')
                if any(part.startswith(".") for part in item.relative_to(root).parts[:-1]):
                    continue
                yield item

    def _count_lines(self, path: Path) -> int:
        """Count non-empty lines in a text file."""
        try:
            return sum(
                1 for line in path.open(encoding="utf-8", errors="ignore")
                if line.strip()
            )
        except Exception:
            return 0

    def _detect_frameworks(
        self, repo_root: Path, language_map: dict[str, LanguageInfo]
    ) -> None:
        """Detect frameworks from manifest files in the repo root."""
        # Java: pom.xml -> Spring, Jakarta EE, Hibernate
        pom = repo_root / "pom.xml"
        if pom.exists():
            if "java" not in language_map:
                language_map["java"] = LanguageInfo(language="java")
            try:
                content = pom.read_text(encoding="utf-8", errors="ignore").lower()
                frameworks: list[str] = []
                if "spring" in content:
                    frameworks.append("spring")
                if "jakarta" in content or "javax.persistence" in content:
                    frameworks.append("jakarta-ee")
                if "hibernate" in content:
                    frameworks.append("hibernate")
                if "quarkus" in content:
                    frameworks.append("quarkus")
                if "micronaut" in content:
                    frameworks.append("micronaut")
                language_map["java"].frameworks_detected.extend(
                    f for f in frameworks if f not in language_map["java"].frameworks_detected
                )
            except Exception:
                pass

        # Python: requirements.txt, pyproject.toml, setup.py -> Django, Flask, FastAPI
        for manifest_name in ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"):
            manifest = repo_root / manifest_name
            if manifest.exists():
                if "python" not in language_map:
                    language_map["python"] = LanguageInfo(language="python")
                try:
                    content = manifest.read_text(encoding="utf-8", errors="ignore").lower()
                    frameworks_detected = language_map["python"].frameworks_detected
                    if "django" in content and "django" not in frameworks_detected:
                        frameworks_detected.append("django")
                    if "flask" in content and "flask" not in frameworks_detected:
                        frameworks_detected.append("flask")
                    if "fastapi" in content and "fastapi" not in frameworks_detected:
                        frameworks_detected.append("fastapi")
                    if "sqlalchemy" in content and "sqlalchemy" not in frameworks_detected:
                        frameworks_detected.append("sqlalchemy")
                    if "celery" in content and "celery" not in frameworks_detected:
                        frameworks_detected.append("celery")
                except Exception:
                    pass

        # PHP: composer.json -> Laravel, Symfony
        composer = repo_root / "composer.json"
        if composer.exists():
            if "php" not in language_map:
                language_map["php"] = LanguageInfo(language="php")
            try:
                data = json.loads(composer.read_text(encoding="utf-8", errors="ignore"))
                require = data.get("require", {})
                all_deps = " ".join(require.keys()).lower()
                frameworks_detected = language_map["php"].frameworks_detected
                if "laravel" in all_deps and "laravel" not in frameworks_detected:
                    frameworks_detected.append("laravel")
                if "symfony" in all_deps and "symfony" not in frameworks_detected:
                    frameworks_detected.append("symfony")
                if "slim" in all_deps and "slim" not in frameworks_detected:
                    frameworks_detected.append("slim")
                if "codeigniter" in all_deps and "codeigniter" not in frameworks_detected:
                    frameworks_detected.append("codeigniter")
            except Exception:
                pass

        # JS/TS: package.json -> React, Vue, Angular, Next.js
        pkg_json = repo_root / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
                all_deps_keys = list(data.get("dependencies", {}).keys()) + list(
                    data.get("devDependencies", {}).keys()
                )
                all_deps = " ".join(all_deps_keys).lower()

                for lang in ("javascript", "typescript"):
                    if lang in language_map:
                        fd = language_map[lang].frameworks_detected
                        if "react" in all_deps and "react" not in fd:
                            fd.append("react")
                        if "vue" in all_deps and "vue" not in fd:
                            fd.append("vue")
                        if "@angular/core" in all_deps and "angular" not in fd:
                            fd.append("angular")
                        if "next" in all_deps and "next.js" not in fd:
                            fd.append("next.js")
                        if "nuxt" in all_deps and "nuxt" not in fd:
                            fd.append("nuxt")
                        if "svelte" in all_deps and "svelte" not in fd:
                            fd.append("svelte")
                        if "express" in all_deps and "express" not in fd:
                            fd.append("express")
            except Exception:
                pass

    def _detect_from_manifests(
        self, repo_root: Path, language_map: dict[str, LanguageInfo]
    ) -> None:
        """
        Check for manifest files that indicate a language is present
        even if no source files with matching extensions were found yet.
        """
        # Gradle: build.gradle implies Java
        for gradle_file in ("build.gradle", "build.gradle.kts"):
            if (repo_root / gradle_file).exists():
                if "java" not in language_map:
                    language_map["java"] = LanguageInfo(language="java")
                break

        # tsconfig.json implies TypeScript
        if (repo_root / "tsconfig.json").exists():
            if "typescript" not in language_map:
                language_map["typescript"] = LanguageInfo(language="typescript")
