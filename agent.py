#!/usr/bin/env python3
"""
=============================================================================
Autonomous Open-Source Issue Resolver Agent
-----------------------------------------------------------------------------
Architecture: Local-First Agentic Workflow with Modular .skill.md Engine
Model: Google Gemma (via local Ollama inference: http://localhost:11434)
=============================================================================
"""

import os
import sys
import json
import re
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

# Force UTF-8 encoding on Windows console streams
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Optional PyYAML support with regex fallback for 100% zero-dependency out-of-the-box run
try:
    import yaml  # type: ignore
    HAS_PYYAML = True
except ImportError:
    HAS_PYYAML = False


# Safe Console Colors & Glyphs
class TerminalColors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    DIM = '\033[2m'
    RESET = '\033[0m'


def log_step(title: str, message: str = ""):
    print(f"\n{TerminalColors.BOLD}{TerminalColors.CYAN}==> [{title}]{TerminalColors.RESET} {message}")


def log_success(message: str):
    print(f"{TerminalColors.GREEN}[+] {message}{TerminalColors.RESET}")


def log_warning(message: str):
    print(f"{TerminalColors.YELLOW}[!] {message}{TerminalColors.RESET}")


def log_error(message: str):
    print(f"{TerminalColors.RED}[X] {message}{TerminalColors.RESET}")



# =============================================================================
# 1. MODULAR AGENT SKILL PARSER (.skill.md)
# =============================================================================

class AgentSkill:
    """Represents a dynamically loaded agent skill defined in a .skill.md file."""
    
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.metadata: Dict[str, Any] = {}
        self.instructions: str = ""
        self._load_and_parse()

    def _parse_yaml_frontmatter_fallback(self, raw_frontmatter: str) -> Dict[str, Any]:
        """Simple line-based parser in case PyYAML is not installed."""
        meta: Dict[str, Any] = {}
        current_dict: Optional[Dict[str, Any]] = None
        current_dict_name = ""

        for line in raw_frontmatter.splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                continue

            # Nested keys (indented)
            if line.startswith("  ") and current_dict is not None:
                if ":" in line_str:
                    sub_key, sub_val = line_str.split(":", 1)
                    sub_val = sub_val.strip().strip('"').strip("'")
                    try:
                        if "." in sub_val:
                            sub_val = float(sub_val)
                        else:
                            sub_val = int(sub_val)
                    except ValueError:
                        pass
                    current_dict[sub_key.strip()] = sub_val
                continue

            current_dict = None
            if ":" in line_str:
                key, val = line_str.split(":", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if not val:
                    # Possible start of nested dict
                    current_dict = {}
                    meta[key] = current_dict
                else:
                    meta[key] = val
        return meta

    def _load_and_parse(self):
        if not self.file_path.exists():
            raise FileNotFoundError(f"Skill file not found: {self.file_path}")

        content = self.file_path.read_text(encoding="utf-8")
        
        # Parse YAML frontmatter between '---' markers
        frontmatter_pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
        match = frontmatter_pattern.match(content)
        
        if match:
            raw_frontmatter, body = match.groups()
            if HAS_PYYAML:
                try:
                    self.metadata = yaml.safe_load(raw_frontmatter) or {}
                except Exception as e:
                    log_warning(f"PyYAML parse error in {self.file_path.name}: {e}. Falling back to internal parser.")
                    self.metadata = self._parse_yaml_frontmatter_fallback(raw_frontmatter)
            else:
                self.metadata = self._parse_yaml_frontmatter_fallback(raw_frontmatter)
            self.instructions = body.strip()
        else:
            self.metadata = {"name": self.file_path.stem}
            self.instructions = content.strip()

    @property
    def name(self) -> str:
        return self.metadata.get("name", self.file_path.stem)

    @property
    def description(self) -> str:
        return self.metadata.get("description", "No description provided.")

    @property
    def parameters(self) -> Dict[str, Any]:
        return self.metadata.get("parameters", {})


# =============================================================================
# 2. LOCAL OLLAMA INFERENCE CLIENT
# =============================================================================

class LocalOllamaClient:
    """Zero-dependency HTTP client interfacing directly with local Ollama API."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "gemma2:2b", timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.generate_endpoint = f"{self.base_url}/api/generate"
        self.tags_endpoint = f"{self.base_url}/api/tags"
        self.model = model
        self.timeout = timeout

    def check_health(self) -> Tuple[bool, str]:
        """Checks if local Ollama daemon is active and if the model is downloaded."""
        try:
            req = urllib.request.Request(self.tags_endpoint, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    available_models = [m.get("name") for m in data.get("models", [])]
                    
                    # Normalize check (e.g. 'gemma2:2b' vs 'gemma2:2b-instruct-q4_0')
                    matched = any(self.model in m or m.startswith(self.model.split(":")[0]) for m in available_models)
                    if not matched:
                        return False, (
                            f"Ollama is running, but model '{self.model}' was not found.\n"
                            f"Installed models: {', '.join(available_models) if available_models else 'None'}\n"
                            f"Run: ollama pull {self.model}"
                        )
                    return True, f"Ollama is healthy and model '{self.model}' is ready."
        except urllib.error.URLError as e:
            return False, (
                f"Cannot connect to local Ollama server at {self.base_url}.\n"
                f"Error detail: {e.reason}\n"
                f"Troubleshooting Steps:\n"
                f"  1. Start Ollama: 'ollama serve'\n"
                f"  2. Verify Gemma installation: 'ollama pull {self.model}'\n"
                f"  3. Test CLI: 'ollama run {self.model} \"Hello\"'"
            )
        except Exception as ex:
            return False, f"Unexpected error during Ollama health check: {ex}"
        return False, "Unknown Ollama health check failure."

    def generate(self, system_prompt: str, user_prompt: str, stream_output: bool = True, **kwargs) -> str:
        """Calls /api/generate on Ollama with streaming support."""
        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": stream_output,
            "options": {
                "temperature": kwargs.get("temperature", 0.2),
                "top_p": kwargs.get("top_p", 0.9),
            }
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.generate_endpoint,
            data=data_bytes,
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if not stream_output:
                    result = json.loads(resp.read().decode("utf-8"))
                    return result.get("response", "")
                
                # Streaming read
                accumulated = []
                for line in resp:
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        token = chunk.get("response", "")
                        print(token, end="", flush=True)
                        accumulated.append(token)
                        if chunk.get("done", False):
                            break
                print()  # newline after streaming completes
                return "".join(accumulated)
        except urllib.error.URLError as e:
            raise ConnectionError(f"Failed to communicate with local Ollama: {e.reason}")


# =============================================================================
# 3. AUTONOMOUS ORCHESTRATOR
# =============================================================================

class OpenSourceIssueAgent:
    """Two-stage autonomous agent utilizing modular Agent Skills."""

    def __init__(self, skills_dir: Path, ollama_client: LocalOllamaClient):
        self.skills_dir = skills_dir
        self.client = ollama_client
        self.skills: Dict[str, AgentSkill] = {}
        self._load_skills()

    def _load_skills(self):
        """Scans and dynamically registers all .skill.md files in skills_dir."""
        if not self.skills_dir.exists():
            raise FileNotFoundError(f"Skills directory does not exist: {self.skills_dir}")

        for skill_file in self.skills_dir.glob("*.skill.md"):
            skill = AgentSkill(skill_file)
            self.skills[skill.name] = skill
            log_success(f"Registered Skill: '{skill.name}' -> {skill.description[:65]}...")

        if not self.skills:
            raise ValueError(f"No '.skill.md' skill files found in {self.skills_dir}")

    def execute_skill(self, skill_name: str, input_payload: str) -> str:
        """Executes a specific skill against the local LLM."""
        if skill_name not in self.skills:
            raise KeyError(f"Skill '{skill_name}' is not registered. Available: {list(self.skills.keys())}")

        skill = self.skills[skill_name]
        log_step(f"EXECUTING SKILL: {skill.name.upper()}", f"(temp={skill.parameters.get('temperature', 0.2)})")
        
        response = self.client.generate(
            system_prompt=skill.instructions,
            user_prompt=input_payload,
            stream_output=True,
            **skill.parameters
        )
        return response

    def run_pipeline(self, issue_data: Dict[str, Any], output_dir: Path) -> Dict[str, Any]:
        """Runs the complete two-stage triage and patch generation workflow."""
        output_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n{TerminalColors.BOLD}{TerminalColors.GREEN}" + "="*70)
        print("   STARTING AUTONOMOUS OPEN-SOURCE ISSUE RESOLVER PIPELINE")
        print("="*70 + f"{TerminalColors.RESET}")
        print(f"Target Issue: #{issue_data.get('issue_number', 'N/A')} - {issue_data.get('title', 'Untitled')}")
        print(f"Inference Model: {self.client.model} @ {self.client.base_url}\n")

        # -------------------------------------------------------------
        # STAGE 1: ISSUE READER SKILL
        # -------------------------------------------------------------
        issue_input_text = (
            f"GitHub Issue #{issue_data.get('issue_number', 'N/A')}\n"
            f"Title: {issue_data.get('title', '')}\n"
            f"Labels: {', '.join(issue_data.get('labels', []))}\n"
            f"Body:\n{issue_data.get('body', '')}\n\n"
            f"Existing Code Context:\n{issue_data.get('existing_code_context', 'No context provided.')}"
        )

        stage1_output = self.execute_skill("issue-reader", issue_input_text)

        # Extract JSON from output if wrapped in backticks
        clean_json_str = stage1_output.strip()
        json_match = re.search(r"```json\s*(.*?)\s*```", stage1_output, re.DOTALL)
        if json_match:
            clean_json_str = json_match.group(1).strip()

        try:
            structured_analysis = json.loads(clean_json_str)
        except json.JSONDecodeError:
            log_warning("LLM response was not pure JSON. Preserving raw analysis.")
            structured_analysis = {"raw_analysis": stage1_output}

        # Save Stage 1 artifact
        stage1_file = output_dir / "issue_analysis.json"
        stage1_file.write_text(json.dumps(structured_analysis, indent=2), encoding="utf-8")
        log_success(f"Saved Stage 1 Analysis to {stage1_file}")

        # -------------------------------------------------------------
        # STAGE 2: CODE FIXER SKILL
        # -------------------------------------------------------------
        fixer_input_text = (
            f"Structured Triage Analysis Report:\n"
            f"{json.dumps(structured_analysis, indent=2)}\n\n"
            f"Original Target Code Context:\n"
            f"{issue_data.get('existing_code_context', 'N/A')}\n\n"
            f"Please generate the complete fix, explanation, unified git diff, and verification test case."
        )

        stage2_output = self.execute_skill("code-fixer", fixer_input_text)

        # Save Stage 2 artifacts
        report_file = output_dir / "fix_report.md"
        report_file.write_text(stage2_output, encoding="utf-8")
        log_success(f"Saved Full Fix Report to {report_file}")

        # Extract and save unified diff
        diff_match = re.search(r"```diff\s*(.*?)\s*```", stage2_output, re.DOTALL)
        if diff_match:
            diff_content = diff_match.group(1).strip()
            diff_file = output_dir / "patch.diff"
            diff_file.write_text(diff_content, encoding="utf-8")
            log_success(f"Extracted and Saved Ready-to-Apply Diff to {diff_file}")

        print(f"\n{TerminalColors.BOLD}{TerminalColors.GREEN}" + "="*70)
        print("   PIPELINE EXECUTION COMPLETE - ALL ARTIFACTS READY!")
        print("="*70 + f"{TerminalColors.RESET}")
        print(f"Review your generated patch in: {output_dir.resolve()}\n")

        return {
            "analysis": structured_analysis,
            "report_path": str(report_file),
            "diff_path": str(output_dir / "patch.diff") if diff_match else None
        }


# =============================================================================
# 4. CLI & RUNTIME ENTRYPOINT
# =============================================================================

def fetch_github_issue(issue_url_or_ref: str, token: Optional[str] = None) -> Dict[str, Any]:
    """Fetches real-time issue data directly from GitHub REST API (zero dependencies)."""
    # Matches https://github.com/owner/repo/issues/123 or owner/repo#123
    match = re.search(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)", issue_url_or_ref)
    if not match:
        match = re.search(r"^([^/]+)/([^#]+)#(\d+)$", issue_url_or_ref)
    
    if not match:
        raise ValueError(
            f"Invalid GitHub issue identifier: '{issue_url_or_ref}'.\n"
            f"Expected: https://github.com/owner/repo/issues/123 or owner/repo#123"
        )
    
    owner, repo, issue_num = match.groups()
    api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_num}"
    log_step("GITHUB API", f"Fetching issue #{issue_num} from {owner}/{repo}...")

    headers = {
        "User-Agent": "Autonomous-OpenSource-Agent/1.0",
        "Accept": "application/vnd.github.v3+json"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(api_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            labels = [l.get("name") for l in data.get("labels", []) if isinstance(l, dict)]
            log_success(f"Fetched GitHub Issue #{data.get('number')}: '{data.get('title')}'")
            return {
                "issue_number": data.get("number"),
                "title": data.get("title", ""),
                "labels": labels,
                "author": data.get("user", {}).get("login", "unknown"),
                "created_at": data.get("created_at", ""),
                "body": data.get("body", ""),
                "existing_code_context": "Fetched live from GitHub. Refer to issue body code blocks for target implementation."
            }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError(f"Issue or repository not found: {owner}/{repo} #{issue_num}. Is it private?")
        elif e.code == 403:
            raise RuntimeError("GitHub API rate limit exceeded. Set a GitHub token via --github-token or GITHUB_TOKEN env var.")
        raise RuntimeError(f"GitHub API HTTP error {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise ConnectionError(f"Could not connect to GitHub API: {e.reason}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Autonomous Open-Source Issue Resolver Agent (Ollama + Gemma + Agent Skills)"
    )
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=Path(__file__).parent / "skills",
        help="Path to directory containing .skill.md files (default: ./skills)"
    )
    parser.add_argument(
        "--issue-file",
        type=Path,
        default=Path(__file__).parent / "data" / "sample_issue.json",
        help="Path to JSON file containing GitHub issue details (ignored if --github-url is used)"
    )
    parser.add_argument(
        "--github-url",
        type=str,
        default=None,
        help="Direct URL or reference to a live GitHub issue (e.g. https://github.com/owner/repo/issues/123)"
    )
    parser.add_argument(
        "--github-token",
        type=str,
        default=os.environ.get("GITHUB_TOKEN", None),
        help="Optional GitHub Personal Access Token to avoid rate limits"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemma3:1b",
        help="Local Ollama model tag (e.g., gemma3:1b, gemma2:2b, gemma4:latest)"
    )
    parser.add_argument(
        "--ollama-url",
        type=str,
        default="http://localhost:11434",
        help="URL of the local Ollama daemon"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent / "output",
        help="Directory to write output artifacts (default: ./output)"
    )
    parser.add_argument(
        "--skip-health-check",
        action="store_true",
        help="Skip Ollama connectivity and model availability pre-flight check"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print(f"{TerminalColors.BOLD}{TerminalColors.BLUE}")
    print("+--------------------------------------------------------------------+")
    print("|      HACKTOBERFEST LOCAL AGENT - POWERED BY GEMMA & OLLAMA         |")
    print("|            Autonomous Good First Issue Resolver Engine             |")
    print("+--------------------------------------------------------------------+")
    print(f"{TerminalColors.RESET}")

    # 1. Initialize Client & Preflight Check
    client = LocalOllamaClient(base_url=args.ollama_url, model=args.model)
    
    if not args.skip_health_check:
        log_step("SYSTEM CHECK", f"Connecting to {args.ollama_url}...")
        healthy, status_msg = client.check_health()
        if not healthy:
            log_error(f"Health check failed:\n{status_msg}")
            sys.exit(1)
        log_success(status_msg)

    # 2. Load Issue Data (Either from live GitHub API or local file)
    if args.github_url:
        try:
            issue_data = fetch_github_issue(args.github_url, token=args.github_token)
        except Exception as e:
            log_error(f"Failed to fetch live GitHub issue: {e}")
            sys.exit(1)
    else:
        if not args.issue_file.exists():
            log_error(f"Target issue file not found: {args.issue_file}")
            sys.exit(1)

        try:
            issue_data = json.loads(args.issue_file.read_text(encoding="utf-8"))
        except Exception as e:
            log_error(f"Failed to read issue JSON: {e}")
            sys.exit(1)

    # 3. Instantiate Agent & Run Pipeline
    try:
        agent = OpenSourceIssueAgent(skills_dir=args.skills_dir, ollama_client=client)
        agent.run_pipeline(issue_data=issue_data, output_dir=args.output_dir)
    except Exception as e:
        log_error(f"Fatal execution error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
