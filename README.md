# RepoVault

**Interactive GitHub repository downloader & updater**

RepoVault keeps a local, organized archive of the GitHub repositories you care about.  
It downloads full source code + every release asset, verifies files with SHA-256 checksums, and only fetches what’s new.

---

## Features

| Feature | Description |
|---------|-------------|
| **External repo list** | Repos live in a simple `repos.txt` — no hardcoding inside the script |
| **Interactive menu** | Clean menu every time you run it |
| **Single or batch add** | Paste one URL or many at once (spaces, commas, or new lines) |
| **SHA-256 verification** | Already-downloaded files are checksummed and skipped |
| **Version-aware releases** | New releases go into their own `releases/<tag>/` folder |
| **Source + binaries** | Downloads both the source ZIP and every release asset (installers, AppImages, MSIs, etc.) |
| **Organized layout** | Everything lands in a tidy `downloads/<repo>/` structure |
| **Resume-friendly** | Safe to re-run anytime — only missing or updated files are fetched |

---

## Requirements

- Python 3.10+
- `requests`
- `tqdm`

```bash
pip install requests tqdm
```

(Optional but recommended) Set a GitHub personal access token to avoid rate limits:

```bash
# PowerShell
$env:GITHUB_TOKEN = "ghp_your_token_here"

# CMD
set GITHUB_TOKEN=ghp_your_token_here

# Linux / macOS
export GITHUB_TOKEN=ghp_your_token_here
```

Create a token at: https://github.com/settings/tokens  
(No special scopes needed for public repositories.)

---

## Installation

1. Create a folder (example):

```bash
mkdir "RepoVault"
cd "RepoVault"
```

2. Save the script as `repovault.py` (or `github.py`).

3. (Optional) Create `repos.txt` next to the script:

```txt
# One GitHub repo URL per line
https://github.com/storytold/artcraft
https://github.com/storytold/photocraft
https://github.com/storytold/lightcraft
https://github.com/storytold/filmcraft
```

If the file doesn’t exist, RepoVault creates it automatically the first time you run it.

---

## Usage

```bash
python repovault.py
```

You’ll see a menu:

```
============================================================
  GitHub Repo Downloader
============================================================
  Repos file : ...\repos.txt
  Output dir : ...\downloads
============================================================

  What would you like to do?
    1. Check for updates / download missing files for all tracked repos
    2. Add a new GitHub repository (paste URL)
    3. List currently tracked repositories
    4. Remove a repository from the list
    5. Exit
```

### Option 1 – Check for updates
Scans every repo in `repos.txt`, downloads any new source or release assets, and skips files that already match the stored SHA-256 checksum.

### Option 2 – Add repository(ies)
Paste one or many URLs. Supported formats:

```
https://github.com/storytold/pdfcraft
storytold/wordcraft
https://github.com/storytold/a, https://github.com/storytold/b
storytold/soundcraft  storytold/effectcraft
```

You can also paste multiple lines and finish with a blank line.  
New repos are automatically added to `repos.txt` and downloaded immediately.

### Option 3 – List tracked repos
Shows everything currently in `repos.txt`.

### Option 4 – Remove a repo
Removes a repo from the tracking list (downloaded files are left untouched).

---

## Folder Structure

After running, you’ll get something like:

```
RepoVault/
├── repovault.py
├── repos.txt
├── .checksums/                  ← internal SHA-256 sidecars
└── downloads/
    ├── artcraft/
    │   ├── source/              ← extracted source code
    │   ├── artcraft-main-source.zip
    │   └── releases/
    │       └── artcraft-v0.41.0/
    │           ├── ArtCraft_0.41.0_x64-setup.exe
    │           ├── ArtCraft_0.41.0_x64_en-US.msi
    │           └── ...
    ├── photocraft/
    │   ├── source/
    │   └── releases/
    │       └── v0.6.0/
    │           ├── photocraft-0.6.0-windows-x64.msi
    │           ├── photocraft-0.6.0-linux-x86_64.AppImage
    │           └── ...
    └── ...
```

---

## Examples

**First-time setup with several repos**

```bash
python repovault.py
# Choose 2
# Paste:
https://github.com/storytold/artcraft
https://github.com/storytold/photocraft
https://github.com/storytold/lightcraft
https://github.com/storytold/filmcraft
# Press Enter on a blank line
```

**Later – just check for updates**

```bash
python repovault.py
# Choose 1
```

**Add a couple more projects in one go**

```bash
python repovault.py
# Choose 2
# Paste:
storytold/pdfcraft  storytold/wordcraft  storytold/soundcraft
```

---

## Tips

- Safe to re-run as often as you like — only new or changed files are downloaded.
- Delete the `*-source.zip` files after extraction if you want to reclaim space (the `source/` folders already contain everything).
- Want higher rate limits? Set the `GITHUB_TOKEN` environment variable.
- The `.checksums/` folder is managed automatically — don’t delete it unless you want RepoVault to re-verify every file next run.

---

## License

MIT – do whatever you want with it.
