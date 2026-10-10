#!/usr/bin/env python3
"""
Interactive GitHub Repo Downloader
----------------------------------
- Keeps your repo list in repos.txt (no hardcoding)
- Interactive menu every time you run it
- SHA256 checksums so already-downloaded files are skipped
- New versions go into their own version folders
- Paste a new GitHub URL (or batch of URLs) and it gets added + downloaded
"""

import os
import sys
import hashlib
import zipfile
import time
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from tqdm import tqdm

# ============================================================
#  Configuration
# ============================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
REPOS_FILE = SCRIPT_DIR / "repos.txt"
OUTPUT_DIR = SCRIPT_DIR / "downloads"
CHECKSUMS_DIR = SCRIPT_DIR / ".checksums"   # stores .sha256 sidecars

# Optional GitHub token (recommended for higher rate limits)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", None)

# ============================================================
#  Session & helpers
# ============================================================

session = requests.Session()
session.headers.update({
    "Accept": "application/vnd.github+json",
    "User-Agent": "github-repo-downloader/2.0",
})
if GITHUB_TOKEN:
    session.headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"


def ensure_dirs():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHECKSUMS_DIR.mkdir(parents=True, exist_ok=True)


def load_repos() -> list[str]:
    """Load repo URLs from repos.txt (one per line). Creates the file if missing."""
    if not REPOS_FILE.exists():
        REPOS_FILE.write_text(
            "# One GitHub repo URL per line\n"
            "# Examples:\n"
            "# https://github.com/storytold/artcraft\n"
            "# https://github.com/storytold/photocraft\n"
            "\n",
            encoding="utf-8",
        )
        return []

    repos = []
    for line in REPOS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        repos.append(line)
    return repos


def save_repo(url: str):
    """Append a new repo URL to repos.txt if it isn't already there."""
    existing = {r.lower().rstrip("/") for r in load_repos()}
    clean = url.strip().rstrip("/")
    if clean.lower() in existing:
        return False  # already present

    with open(REPOS_FILE, "a", encoding="utf-8") as f:
        f.write(clean + "\n")
    return True


def parse_repo_url(url: str) -> tuple[str, str]:
    """Extract owner and repo name from various GitHub URL formats."""
    url = url.strip().rstrip("/").removesuffix(".git")
    # Support both full URLs and "owner/repo"
    if "github.com" in url:
        parts = urlparse(url).path.strip("/").split("/")
    else:
        parts = url.strip("/").split("/")

    if len(parts) < 2:
        raise ValueError(f"Could not parse owner/repo from: {url}")
    return parts[0], parts[1]


def sha256_file(path: Path) -> str:
    """Compute SHA256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def checksum_path_for(dest: Path) -> Path:
    """Where we store the .sha256 sidecar for a given downloaded file."""
    # Keep the relative structure under .checksums/
    rel = dest.relative_to(OUTPUT_DIR) if dest.is_relative_to(OUTPUT_DIR) else dest.name
    return CHECKSUMS_DIR / (str(rel) + ".sha256")


def is_up_to_date(dest: Path, expected_sha: str | None = None) -> bool:
    """
    Return True if the file already exists and its checksum matches.
    If expected_sha is provided we use that; otherwise we trust our stored sidecar.
    """
    if not dest.exists() or dest.stat().st_size == 0:
        return False

    side = checksum_path_for(dest)
    if expected_sha:
        # Compare against the expected value
        current = sha256_file(dest)
        if current == expected_sha:
            # Refresh our sidecar just in case
            side.parent.mkdir(parents=True, exist_ok=True)
            side.write_text(current, encoding="utf-8")
            return True
        return False

    # No expected hash from API → use our stored sidecar
    if side.exists():
        stored = side.read_text(encoding="utf-8").strip()
        current = sha256_file(dest)
        return current == stored

    # First time we've seen this file – compute and store
    current = sha256_file(dest)
    side.parent.mkdir(parents=True, exist_ok=True)
    side.write_text(current, encoding="utf-8")
    return True  # treat existing file as good


def store_checksum(dest: Path, digest: str | None = None):
    """Write the SHA256 sidecar."""
    side = checksum_path_for(dest)
    side.parent.mkdir(parents=True, exist_ok=True)
    if digest is None:
        digest = sha256_file(dest)
    side.write_text(digest, encoding="utf-8")


def download_file(url: str, dest: Path, desc: str = None, expected_sha: str | None = None) -> bool:
    """
    Stream-download a file with progress bar.
    Returns True if a download actually happened, False if skipped.
    """
    if is_up_to_date(dest, expected_sha):
        print(f"  ✓ Already up-to-date: {dest.name}")
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    desc = desc or dest.name

    try:
        with session.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))

            with open(dest, "wb") as f, tqdm(
                total=total,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                desc=f"  {desc}",
                leave=False,
            ) as pbar:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))

        # Verify / store checksum
        if expected_sha:
            actual = sha256_file(dest)
            if actual != expected_sha:
                print(f"  ⚠ Checksum mismatch for {dest.name}! (got {actual[:12]}…)")
                # Keep the file but warn
            store_checksum(dest, actual)
        else:
            store_checksum(dest)

        print(f"  ✓ Downloaded: {dest.name}")
        return True

    except Exception as e:
        print(f"  ✗ Failed to download {dest.name}: {e}")
        if dest.exists():
            dest.unlink(missing_ok=True)
        return False


# ============================================================
#  GitHub API helpers
# ============================================================

def get_repo_info(owner: str, repo: str) -> dict:
    r = session.get(f"https://api.github.com/repos/{owner}/{repo}", timeout=30)
    r.raise_for_status()
    return r.json()


def get_latest_release(owner: str, repo: str) -> dict | None:
    r = session.get(f"https://api.github.com/repos/{owner}/{repo}/releases/latest", timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def extract_sha_from_digest(digest: str | None) -> str | None:
    """GitHub sometimes returns 'sha256:abcdef…' """
    if not digest:
        return None
    if digest.startswith("sha256:"):
        return digest[7:]
    return digest


# ============================================================
#  Download logic
# ============================================================

def download_and_extract_source(owner: str, repo: str, default_branch: str, target_dir: Path):
    """Download source ZIP of the default branch and extract it."""
    zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{default_branch}.zip"
    zip_path = target_dir / f"{repo}-{default_branch}-source.zip"
    extract_dir = target_dir / "source"

    print(f"  → Source code ({default_branch})")
    downloaded = download_file(zip_url, zip_path, desc=f"{repo} source")

    # Only re-extract if we just downloaded a new ZIP or the source folder is missing
    if not downloaded and extract_dir.exists() and any(extract_dir.iterdir()):
        print(f"  ✓ Source already extracted")
        return

    print(f"  → Extracting source...")
    if extract_dir.exists():
        # Clear old extraction so we get a clean tree
        import shutil
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                if member.endswith("/"):
                    continue
                parts = Path(member).parts
                if len(parts) <= 1:
                    continue
                relative = Path(*parts[1:])
                target = extract_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as dst:
                    dst.write(src.read())
        print(f"  ✓ Source extracted → {extract_dir}")
    except Exception as e:
        print(f"  ✗ Extraction failed: {e}")


def download_release_assets(owner: str, repo: str, release: dict, target_dir: Path):
    """Download every asset from a release into releases/<tag>/"""
    tag = release.get("tag_name", "unknown")
    assets = release.get("assets", [])

    release_dir = target_dir / "releases" / tag
    release_dir.mkdir(parents=True, exist_ok=True)

    if not assets:
        print(f"  ℹ No binary assets in release {tag}")
        # Still grab the source archive GitHub always attaches
        zipball = release.get("zipball_url")
        if zipball:
            dest = release_dir / f"{repo}-{tag}-source.zip"
            download_file(zipball, dest, desc=f"{tag} source archive")
        return

    print(f"  → Latest release: {tag}  ({len(assets)} assets)")
    new_count = 0
    for asset in assets:
        name = asset["name"]
        url = asset["browser_download_url"]
        size_mb = asset.get("size", 0) / (1024 * 1024)
        expected = extract_sha_from_digest(asset.get("digest"))
        dest = release_dir / name
        if download_file(url, dest, desc=f"{name} ({size_mb:.1f} MB)", expected_sha=expected):
            new_count += 1

    if new_count == 0:
        print(f"  ✓ All assets for {tag} already present")
    else:
        print(f"  ✓ Downloaded {new_count} new asset(s) for {tag}")


def process_repo(repo_url: str, force_source: bool = False):
    """Full processing of one repository."""
    try:
        owner, repo = parse_repo_url(repo_url)
    except ValueError as e:
        print(f"  ✗ {e}")
        return

    print(f"\n{'='*60}")
    print(f"  {owner}/{repo}")
    print(f"{'='*60}")

    try:
        info = get_repo_info(owner, repo)
    except requests.HTTPError as e:
        print(f"  ✗ Failed to fetch repo info: {e}")
        return

    default_branch = info.get("default_branch", "main")
    print(f"  Default branch: {default_branch}")

    target_dir = OUTPUT_DIR / repo
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Source
    try:
        download_and_extract_source(owner, repo, default_branch, target_dir)
    except Exception as e:
        print(f"  ✗ Source step failed: {e}")

    # 2. Latest release assets
    try:
        release = get_latest_release(owner, repo)
        if release:
            download_release_assets(owner, repo, release, target_dir)
        else:
            print("  ℹ No releases published yet")
    except Exception as e:
        print(f"  ✗ Release step failed: {e}")

    print(f"  ✓ Finished → {target_dir}")


# ============================================================
#  Interactive menu
# ============================================================

def print_header():
    print("\n" + "=" * 60)
    print("  GitHub Repo Downloader")
    print("=" * 60)
    print(f"  Repos file : {REPOS_FILE}")
    print(f"  Output dir : {OUTPUT_DIR}")
    if GITHUB_TOKEN:
        print("  Auth      : GitHub token detected (higher rate limits)")
    else:
        print("  Auth      : anonymous (set GITHUB_TOKEN env var for better limits)")
    print("=" * 60)


def menu_list_repos(repos: list[str]):
    if not repos:
        print("\n  (no repositories in repos.txt yet)")
        return
    print(f"\n  Currently tracking {len(repos)} repo(s):")
    for i, url in enumerate(repos, 1):
        try:
            owner, repo = parse_repo_url(url)
            print(f"    {i:2d}. {owner}/{repo}")
        except Exception:
            print(f"    {i:2d}. {url}")


def menu_add_repo():
    print("\n  Paste one or more GitHub repository URLs")
    print("  You can enter:")
    print("    • A single URL")
    print("    • Multiple URLs separated by spaces, commas, or new lines")
    print("  Examples:")
    print("    https://github.com/storytold/pdfcraft")
    print("    storytold/wordcraft  storytold/soundcraft")
    print("    https://github.com/storytold/pdfcraft, https://github.com/storytold/effectcraft")
    print("  (press Enter on an empty line when finished, or press Enter immediately to cancel)")
    print()

    lines = []
    while True:
        try:
            line = input("  > ").strip()
        except EOFError:
            break
        if not line:
            break
        lines.append(line)

    if not lines:
        print("  Cancelled.")
        return

    # Split on commas, spaces, and newlines
    raw_urls = []
    for line in lines:
        for part in line.replace(",", " ").split():
            part = part.strip()
            if part:
                raw_urls.append(part)

    if not raw_urls:
        print("  No valid URLs found.")
        return

    print(f"\n  Processing {len(raw_urls)} URL(s)...")

    for url in raw_urls:
        try:
            owner, repo = parse_repo_url(url)
        except ValueError as e:
            print(f"  ✗ Skipping '{url}': {e}")
            continue

        full_url = f"https://github.com/{owner}/{repo}"
        added = save_repo(full_url)
        if added:
            print(f"  ✓ Added {owner}/{repo} to repos.txt")
        else:
            print(f"  ℹ {owner}/{repo} was already in the list")

        # Immediately download it
        process_repo(full_url)


def menu_check_updates(repos: list[str]):
    if not repos:
        print("\n  No repositories configured. Add some first.")
        return

    print(f"\n  Checking {len(repos)} repository(ies) for updates…")
    for url in repos:
        process_repo(url)
        time.sleep(0.4)  # be polite to the API

    print(f"\n{'='*60}")
    print("  All done!")
    print(f"  Everything is under: {OUTPUT_DIR}")
    print(f"{'='*60}")


def menu_remove_repo(repos: list[str]):
    if not repos:
        print("\n  Nothing to remove.")
        return

    menu_list_repos(repos)
    print("\n  Enter the number of the repo to remove (or press Enter to cancel)")
    choice = input("  Number: ").strip()
    if not choice.isdigit():
        print("  Cancelled.")
        return

    idx = int(choice) - 1
    if idx < 0 or idx >= len(repos):
        print("  Invalid number.")
        return

    to_remove = repos[idx]
    # Rewrite the file without that line
    lines = REPOS_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped.rstrip("/") == to_remove.rstrip("/"):
            continue
        new_lines.append(line)

    REPOS_FILE.write_text("".join(new_lines), encoding="utf-8")
    try:
        owner, repo = parse_repo_url(to_remove)
        print(f"  ✓ Removed {owner}/{repo} from the list")
        print(f"    (downloaded files under downloads/{repo}/ were left untouched)")
    except Exception:
        print(f"  ✓ Removed from the list")


def main():
    ensure_dirs()
    print_header()

    while True:
        repos = load_repos()
        print("\n  What would you like to do?")
        print("    1. Check for updates / download missing files for all tracked repos")
        print("    2. Add a new GitHub repository (paste URL)")
        print("    3. List currently tracked repositories")
        print("    4. Remove a repository from the list")
        print("    5. Exit")

        choice = input("\n  Choice [1-5]: ").strip()

        if choice == "1":
            menu_check_updates(repos)
        elif choice == "2":
            menu_add_repo()
        elif choice == "3":
            menu_list_repos(repos)
        elif choice == "4":
            menu_remove_repo(repos)
        elif choice == "5" or choice.lower() in ("q", "quit", "exit"):
            print("\n  Bye!")
            break
        else:
            print("  Invalid choice, try again.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Interrupted. Bye!")
        sys.exit(0)
