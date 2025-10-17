import argparse
import atexit
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import termios
import time
import tty
from typing import Dict, List, Set

import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
TEMP_DIRS = []
INTERRUPTED = False
SILENT_MODE = False
START_TIME = None
OLD_TERM_SETTINGS = None

class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    ORANGE = '\033[38;5;208m'

IGNORED_PATTERNS = [
    r'example',
    r'demo',
    r'test',
    r'tests',
    r'testing',
    r'sample',
    r'samples',
    r'mock',
    r'fixture',
    r'playground',
    r'tutorial',
    r'skeleton',
    r'template',
    r'stub',
    r'dummy'
]

def should_label_as_medium(finding_data: Dict) -> bool:
    try:
        source_metadata = finding_data.get("SourceMetadata", {})
        data = source_metadata.get("Data", {})
        git_data = data.get("Git", {})

        file_path = git_data.get("file", "").lower()
        repository = git_data.get("repository", "").lower()

        combined_text = f"{file_path} {repository}"

        for pattern in IGNORED_PATTERNS:
            if re.search(pattern, combined_text, re.IGNORECASE):
                return True

        return False
    except:
        return False

def cleanup():
    global OLD_TERM_SETTINGS
    for temp_dir in TEMP_DIRS:
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
    if OLD_TERM_SETTINGS is not None:
        try:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, OLD_TERM_SETTINGS)
        except:
            pass

def signal_handler(signum, frame):
    global INTERRUPTED, START_TIME
    INTERRUPTED = True
    print(f"{Colors.YELLOW}[WRN]{Colors.RESET} Scan interrupted by user")
    print(f"{Colors.CYAN}[INF]{Colors.RESET} Cleaning up temporary files...")
    cleanup()
    elapsed_time = (time.time() - START_TIME) if START_TIME is not None else 0
    print(f"{Colors.CYAN}[INF]{Colors.RESET} Scan finished {Colors.DIM}({elapsed_time:.3f}s time elapsed){Colors.RESET}")
    sys.exit(130)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)

def print_banner():
    if SILENT_MODE:
        return
    banner = f"""
{Colors.CYAN} _____           __  __ _      _   _       _
|_   _|         / _|/ _| |    | | | |     | |
  | |_ __ _   _| |_| |_| | ___| |_| |_   _| |__
  | | '__| | | |  _|  _| |/ _ \\  _  | | | | '_ \\
  | | |  | |_| | | | | | |  __/ | | | |_| | |_) |
  \\_/_|   \\__,_|_| |_| |_|\\___\\_| |_/\\__,_|_.__/ {Colors.RESET}

{Colors.DIM}            GitHub Secret Scanner v1.0{Colors.RESET}
"""
    print(banner)

def get_headers():
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers

def run_command(cmd: List[str]) -> Dict:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return {"success": True, "output": result.stdout, "error": ""}
    except subprocess.CalledProcessError as e:
        return {"success": False, "output": "", "error": e.stderr}

def get_org_repos(org: str, include_forks: bool = True) -> List[str]:
    repos = []
    page = 1

    while True:
        if INTERRUPTED:
            return repos

        url = f"https://api.github.com/orgs/{org}/repos?per_page=100&page={page}"
        response = requests.get(url, headers=get_headers())

        if response.status_code != 200:
            if not SILENT_MODE:
                print(f"{Colors.RED}[ERR]{Colors.RESET} Failed to fetch org repos: {response.status_code}")
            break

        data = response.json()
        if not data:
            break

        for repo in data:
            if include_forks or not repo.get("fork", False):
                repos.append(repo["clone_url"])

        page += 1

    return repos

def get_org_members(org: str) -> List[str]:
    members = []
    page = 1

    while True:
        if INTERRUPTED:
            return members

        url = f"https://api.github.com/orgs/{org}/members?per_page=100&page={page}"
        response = requests.get(url, headers=get_headers())

        if response.status_code != 200:
            if not SILENT_MODE:
                print(f"{Colors.RED}[ERR]{Colors.RESET} Failed to fetch org members: {response.status_code}")
            break

        data = response.json()
        if not data:
            break

        for member in data:
            members.append(member["login"])

        page += 1

    return list(set(members))

def get_user_repos(username: str, include_forks: bool = True) -> List[str]:
    repos = []
    page = 1

    while True:
        if INTERRUPTED:
            return repos

        url = f"https://api.github.com/users/{username}/repos?per_page=100&page={page}"
        response = requests.get(url, headers=get_headers())

        if response.status_code != 200:
            if not SILENT_MODE:
                print(f"{Colors.RED}[ERR]{Colors.RESET} Failed to fetch repos for {username}: {response.status_code}")
            break

        data = response.json()
        if not data:
            break

        for repo in data:
            if include_forks or not repo.get("fork", False):
                repos.append(repo["clone_url"])

        page += 1

    return repos

def scan_with_trufflehog(repo_url: str, idx: int, total: int, output_dir: str = None, only_verified: bool = False):
    if INTERRUPTED:
        return

    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    org_or_user = repo_url.rstrip("/").split("/")[-2]
    repo_full = f"{org_or_user}/{repo_name}"

    cmd = ["trufflehog", "git", repo_url, "--json"]

    if only_verified:
        cmd.append("--only-verified")

    result = run_command(cmd)

    if result["success"]:
        critical_findings = []
        medium_findings = []
        has_any_medium = False

        if result["output"]:
            findings = [line for line in result["output"].strip().split("\n") if line]

            for finding_line in findings:
                try:
                    finding_data = json.loads(finding_line)
                    if should_label_as_medium(finding_data):
                        medium_findings.append(finding_line)
                        has_any_medium = True
                    else:
                        critical_findings.append(finding_line)
                except json.JSONDecodeError:
                    critical_findings.append(finding_line)

            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                if critical_findings:
                    output_file = os.path.join(output_dir, f"{org_or_user}_{repo_name}_critical.json")
                    with open(output_file, "w") as f:
                        f.write("\n".join(critical_findings))
                if medium_findings:
                    output_file = os.path.join(output_dir, f"{org_or_user}_{repo_name}_medium.json")
                    with open(output_file, "w") as f:
                        f.write("\n".join(medium_findings))

        critical_count = len(critical_findings)
        medium_count = len(medium_findings)
        total_findings = critical_count + medium_count

        if total_findings > 0 and has_any_medium:
            status = f"{Colors.ORANGE}[medium]{Colors.RESET}"
            count_color = Colors.ORANGE
        elif total_findings > 0:
            status = f"{Colors.RED}[critical]{Colors.RESET}"
            count_color = Colors.RED
        else:
            status = f"{Colors.GREEN}[clean]{Colors.RESET}"
            count_color = Colors.GREEN

        padding = len(str(total))
        progress = f"{Colors.DIM}[{str(idx).zfill(padding)}/{total}]{Colors.RESET}"
        count = f"{count_color}{total_findings}{Colors.RESET}"

        if not SILENT_MODE or critical_count > 0 or medium_count > 0:
            print(f"{progress} {status} {repo_full} {Colors.DIM}[{count} findings]{Colors.RESET}")
    else:
        padding = len(str(total))
        progress = f"{Colors.DIM}[{str(idx).zfill(padding)}/{total}]{Colors.RESET}"
        print(f"{progress} {Colors.RED}[failed]{Colors.RESET} {repo_full}")

def main():
    global SILENT_MODE, START_TIME, OLD_TERM_SETTINGS

    try:
        OLD_TERM_SETTINGS = termios.tcgetattr(sys.stdin)
        new_settings = termios.tcgetattr(sys.stdin)
        new_settings[3] = new_settings[3] & ~termios.ECHOCTL
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, new_settings)
    except:
        pass

    parser = argparse.ArgumentParser(description="Fetch Git URLs and scan with TruffleHog")
    parser.add_argument("-org", help="GitHub organization name")
    parser.add_argument("-user", help="GitHub username")
    parser.add_argument("-repo", help="Single repository URL")
    parser.add_argument("-include-forks", action="store_true", help="Include forked repositories")
    parser.add_argument("-include-members", action="store_true", help="Include organization member repositories (only with -org)")
    parser.add_argument("-output", help="Directory to save TruffleHog results")
    parser.add_argument("-results", choices=["valid", "all"], default="all", help="Filter results: 'valid' for verified secrets only, 'all' for everything")
    parser.add_argument("-silent", action="store_true", help="Only print scan results")

    args = parser.parse_args()

    SILENT_MODE = args.silent

    if not args.org and not args.repo and not args.user:
        if not SILENT_MODE:
            print(f"{Colors.RED}[ERR]{Colors.RESET} Must specify -org, -user, or -repo")
        sys.exit(1)

    print_banner()

    if not GITHUB_TOKEN and not SILENT_MODE:
        print(f"{Colors.YELLOW}[WRN]{Colors.RESET} GITHUB_TOKEN not set, rate limits may apply")

    only_verified = args.results == "valid"

    all_repos: Set[str] = set()

    if args.repo:
        all_repos.add(args.repo)

    if args.org:
        if not SILENT_MODE:
            print(f"{Colors.CYAN}[INF]{Colors.RESET} Target organization: {Colors.BOLD}{args.org}{Colors.RESET}")
        org_repos = get_org_repos(args.org, args.include_forks)
        if not SILENT_MODE:
            print(f"{Colors.CYAN}[INF]{Colors.RESET} Found {Colors.BOLD}{len(org_repos)}{Colors.RESET} organization repositories")
        all_repos.update(org_repos)

        if args.include_members:
            if not SILENT_MODE:
                print(f"{Colors.CYAN}[INF]{Colors.RESET} Fetching organization members")
            members = get_org_members(args.org)
            if not SILENT_MODE:
                print(f"{Colors.CYAN}[INF]{Colors.RESET} Found {Colors.BOLD}{len(members)}{Colors.RESET} organization members")

            for member in members:
                if INTERRUPTED:
                    break
                member_repos = get_user_repos(member, args.include_forks)
                if member_repos and not SILENT_MODE:
                    print(f"{Colors.DIM}[*]{Colors.RESET} {member}: {len(member_repos)} repositories")
                all_repos.update(member_repos)

    if args.user:
        if not SILENT_MODE:
            print(f"{Colors.CYAN}[INF]{Colors.RESET} Target user: {Colors.BOLD}{args.user}{Colors.RESET}")
        user_repos = get_user_repos(args.user, args.include_forks)
        if not SILENT_MODE:
            print(f"{Colors.CYAN}[INF]{Colors.RESET} Found {Colors.BOLD}{len(user_repos)}{Colors.RESET} user repositories")
        all_repos.update(user_repos)

    if INTERRUPTED:
        sys.exit(130)

    all_repos_list = sorted(list(all_repos))

    if not SILENT_MODE:
        print(f"{Colors.CYAN}[INF]{Colors.RESET} Starting scan of {Colors.BOLD}{len(all_repos_list)}{Colors.RESET} repositories")

    START_TIME = time.time()

    for idx, repo_url in enumerate(all_repos_list, 1):
        if INTERRUPTED:
            break
        scan_with_trufflehog(repo_url, idx, len(all_repos_list), args.output, only_verified)

    elapsed_time = time.time() - START_TIME
    print(f"\n{Colors.CYAN}[INF]{Colors.RESET} Scan finished {Colors.DIM}({elapsed_time:.3f}s elapsed time){Colors.RESET}")
    cleanup()

if __name__ == "__main__":
    main()
