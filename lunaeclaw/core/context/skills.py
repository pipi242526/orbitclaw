"""Skills loader for agent capabilities."""

import json
import os
import re
import shutil
from pathlib import Path

from lunaeclaw.platform.utils.helpers import get_global_skills_path

# Default builtin skills directory (relative to this file)
BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills"


class SkillsLoader:
    """
    Loader for agent skills.

    Skills are markdown files (SKILL.md) that teach the agent how to use
    specific tools or perform certain tasks.
    """

    def __init__(
        self,
        workspace: Path,
        builtin_skills_dir: Path | None = None,
        disabled_skills: set[str] | None = None,
    ):
        self.workspace = workspace
        self.workspace_skills = workspace / "skills"
        self.global_skills = get_global_skills_path()
        self.builtin_skills = builtin_skills_dir or BUILTIN_SKILLS_DIR
        self.disabled_skills = {s.lower() for s in (disabled_skills or set())}
        self._metadata_cache: dict[str, dict | None] = {}
        self._skill_meta_cache: dict[str, dict] = {}

    def _is_skill_enabled(self, name: str) -> bool:
        """Return True if the skill is not disabled by config."""
        return name.lower() not in self.disabled_skills

    def list_skills(self, filter_unavailable: bool = True) -> list[dict[str, str]]:
        """
        List all available skills.

        Args:
            filter_unavailable: If True, filter out skills with unmet requirements.

        Returns:
            List of skill info dicts with 'name', 'path', 'source'.
        """
        skills: list[dict[str, str]] = []
        seen_names: set[str] = set()

        def _collect_from(root: Path, source: str) -> None:
            if not root.exists():
                return
            for skill_dir in root.iterdir():
                if not skill_dir.is_dir():
                    continue
                name = skill_dir.name
                if name in seen_names or not self._is_skill_enabled(name):
                    continue
                skill_file = skill_dir / "SKILL.md"
                if not skill_file.exists():
                    continue
                seen_names.add(name)
                skills.append({"name": name, "path": str(skill_file), "source": source})

        # Precedence order: workspace > global > builtin
        _collect_from(self.workspace_skills, "workspace")
        _collect_from(self.global_skills, "global")
        if self.builtin_skills:
            _collect_from(self.builtin_skills, "builtin")

        # Filter by requirements
        if filter_unavailable:
            return [s for s in skills if self._check_requirements(self._get_skill_meta(s["name"]))]
        return skills

    def load_skill(self, name: str) -> str | None:
        """
        Load a skill by name.

        Args:
            name: Skill name (directory name).

        Returns:
            Skill content or None if not found.
        """
        if not self._is_skill_enabled(name):
            return None

        # Check workspace first
        workspace_skill = self.workspace_skills / name / "SKILL.md"
        if workspace_skill.exists():
            return workspace_skill.read_text(encoding="utf-8")

        # Check global custom skills
        global_skill = self.global_skills / name / "SKILL.md"
        if global_skill.exists():
            return global_skill.read_text(encoding="utf-8")

        # Check built-in
        if self.builtin_skills:
            builtin_skill = self.builtin_skills / name / "SKILL.md"
            if builtin_skill.exists():
                return builtin_skill.read_text(encoding="utf-8")

        return None

    def load_skills_for_context(self, skill_names: list[str]) -> str:
        """
        Load specific skills for inclusion in agent context.

        Args:
            skill_names: List of skill names to load.

        Returns:
            Formatted skills content.
        """
        parts = []
        for name in skill_names:
            content = self.load_skill(name)
            if content:
                content = self._strip_frontmatter(content)
                parts.append(f"### Skill: {name}\n\n{content}")

        return "\n\n---\n\n".join(parts) if parts else ""

    def build_skills_summary(self) -> str:
        """
        Build a summary of all skills (name, description, path, availability).

        This is used for progressive loading - the agent can read the full
        skill content using read_file when needed.

        Returns:
            XML-formatted skills summary.
        """
        all_skills = self.list_skills(filter_unavailable=False)
        if not all_skills:
            return ""

        def escape_xml(s: str) -> str:
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        lines = ["<skills>"]
        for s in all_skills:
            name = escape_xml(s["name"])
            path = s["path"]
            desc = escape_xml(self._get_skill_description(s["name"]))
            skill_meta = self._get_skill_meta(s["name"])
            available = self._check_requirements(skill_meta)
            attrs = []
            if skill_meta.get("category"):
                attrs.append(f' category="{escape_xml(str(skill_meta["category"]))}"')
            if skill_meta.get("lang"):
                attrs.append(f' lang="{escape_xml(str(skill_meta["lang"]))}"')

            lines.append(f"  <skill available=\"{str(available).lower()}\"{''.join(attrs)}>")
            lines.append(f"    <name>{name}</name>")
            lines.append(f"    <description>{desc}</description>")
            lines.append(f"    <location>{path}</location>")

            # Show missing requirements for unavailable skills
            if not available:
                missing = self._get_missing_requirements(skill_meta)
                if missing:
                    lines.append(f"    <requires>{escape_xml(missing)}</requires>")

            lines.append("  </skill>")
        lines.append("</skills>")

        return "\n".join(lines)

    def _get_missing_requirements(self, skill_meta: dict) -> str:
        """Get a description of missing requirements."""
        missing = []
        requires = skill_meta.get("requires", {})
        for b in requires.get("bins", []):
            if not shutil.which(b):
                missing.append(f"CLI: {b}")
        for env in requires.get("env", []):
            if not os.environ.get(env):
                missing.append(f"ENV: {env}")
        if requires.get("network") and os.environ.get("LUNAECLAW_OFFLINE") in {"1", "true", "yes"}:
            missing.append("NETWORK: disabled (LUNAECLAW_OFFLINE)")
        return ", ".join(missing)

    def _get_skill_description(self, name: str) -> str:
        """Get the description of a skill from its frontmatter."""
        meta = self.get_skill_metadata(name)
        if meta and meta.get("description"):
            return meta["description"]
        return name  # Fallback to skill name

    def _strip_frontmatter(self, content: str) -> str:
        """Remove YAML frontmatter from markdown content."""
        if content.startswith("---"):
            match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
            if match:
                return content[match.end():].strip()
        return content

    def _parse_nanobot_metadata(self, raw: str) -> dict:
        """Parse skill metadata JSON from frontmatter (supports lunaeclaw and openclaw keys)."""
        try:
            data = json.loads(raw)
            return data.get("lunaeclaw", data.get("openclaw", {})) if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _parse_list_field(self, value: str | None) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in str(value).split(",") if item.strip()]

    def _parse_bool_field(self, value: str | None) -> bool | None:
        if value is None:
            return None
        sval = str(value).strip().lower()
        if sval in {"1", "true", "yes", "on"}:
            return True
        if sval in {"0", "false", "no", "off"}:
            return False
        return None

    def _frontmatter_to_skill_meta(self, frontmatter: dict | None) -> dict:
        """Map simple frontmatter fields into lunaeclaw skill metadata shape."""
        if not frontmatter:
            return {}
        skill_meta: dict = {}
        requires: dict[str, object] = {}
        bins = self._parse_list_field(frontmatter.get("requires_cli"))
        envs = self._parse_list_field(frontmatter.get("requires_env"))
        if bins:
            requires["bins"] = bins
        if envs:
            requires["env"] = envs
        network = self._parse_bool_field(frontmatter.get("requires_network"))
        if network is not None:
            requires["network"] = network
        if requires:
            skill_meta["requires"] = requires
        if category := str(frontmatter.get("category") or "").strip():
            skill_meta["category"] = category
        if lang := str(frontmatter.get("lang") or "").strip():
            skill_meta["lang"] = lang
        always = self._parse_bool_field(frontmatter.get("always"))
        if always is not None:
            skill_meta["always"] = always
        return skill_meta

    def _merge_skill_meta(self, base: dict, override: dict) -> dict:
        if not base:
            return dict(override or {})
        out = dict(base)
        for key, value in (override or {}).items():
            if key == "requires" and isinstance(value, dict) and isinstance(out.get(key), dict):
                req = dict(out[key])
                req.update(value)
                out[key] = req
            else:
                out[key] = value
        return out

    def _check_requirements(self, skill_meta: dict) -> bool:
        """Check if skill requirements are met (bins, env vars)."""
        requires = skill_meta.get("requires", {})
        for b in requires.get("bins", []):
            if not shutil.which(b):
                return False
        for env in requires.get("env", []):
            if not os.environ.get(env):
                return False
        if requires.get("network") and os.environ.get("LUNAECLAW_OFFLINE") in {"1", "true", "yes"}:
            return False
        return True

    def _get_skill_meta(self, name: str) -> dict:
        """Get lunaeclaw metadata for a skill (cached in frontmatter)."""
        if name in self._skill_meta_cache:
            return self._skill_meta_cache[name]
        meta = self.get_skill_metadata(name) or {}
        nested = self._parse_nanobot_metadata(meta.get("metadata", ""))
        direct = self._frontmatter_to_skill_meta(meta)
        merged = self._merge_skill_meta(nested, direct)
        self._skill_meta_cache[name] = merged
        return merged

    def get_always_skills(self) -> list[str]:
        """Get skills marked as always=true that meet requirements."""
        result = []
        for s in self.list_skills(filter_unavailable=True):
            meta = self.get_skill_metadata(s["name"]) or {}
            skill_meta = self._parse_nanobot_metadata(meta.get("metadata", ""))
            if skill_meta.get("always") or meta.get("always"):
                result.append(s["name"])
        return result

    def get_skill_metadata(self, name: str) -> dict | None:
        """
        Get metadata from a skill's frontmatter.

        Args:
            name: Skill name.

        Returns:
            Metadata dict or None.
        """
        if name in self._metadata_cache:
            return self._metadata_cache[name]

        content = self.load_skill(name)
        if not content:
            self._metadata_cache[name] = None
            return None

        if content.startswith("---"):
            match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if match:
                # Simple YAML parsing
                metadata = {}
                for line in match.group(1).split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        metadata[key.strip()] = value.strip().strip('"\'')
                self._metadata_cache[name] = metadata
                return metadata

        self._metadata_cache[name] = None
        return None

    def build_availability_report(self) -> list[dict[str, str | bool]]:
        """Return a diagnostic report for all skills (including unavailable ones)."""
        rows: list[dict[str, str | bool]] = []
        for s in self.list_skills(filter_unavailable=False):
            meta = self._get_skill_meta(s["name"])
            available = self._check_requirements(meta)
            rows.append(
                {
                    "name": s["name"],
                    "source": s["source"],
                    "path": s["path"],
                    "available": available,
                    "requires": self._get_missing_requirements(meta) if not available else "",
                    "category": str(meta.get("category", "")),
                    "lang": str(meta.get("lang", "")),
                }
            )
        return rows
