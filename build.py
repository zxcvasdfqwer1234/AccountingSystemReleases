import sys
import os
import shutil
import zipfile
import subprocess
import json
import urllib.request
import urllib.error
import time
import stat
from pathlib import Path
from datetime import datetime


PROJECT_NAME = None
GITHUB_TOKEN = None
REPO_OWNER = None
REPO_NAME = None
REPO_URL = None
PROJECT_URL = None

class Builder:
    @staticmethod
    def getEnv(env_path):
        global PROJECT_NAME, GITHUB_TOKEN, REPO_OWNER, REPO_NAME, REPO_URL, PROJECT_URL

        if not os.path.exists(env_path):
            raise FileNotFoundError(f"Environment file not found: {env_path}")

        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                value = value.strip().strip('"').strip("'")

                if key.strip() == "GITHUB_TOKEN":
                    GITHUB_TOKEN = value
                elif key.strip() == "REPO_OWNER":
                    REPO_OWNER = value
                elif key.strip() == "REPO_NAME":
                    REPO_NAME = value
                elif key.strip() == "PROJECT_NAME":
                    PROJECT_NAME = value

        missing = [
            name for name, value in {
                "GITHUB_TOKEN": GITHUB_TOKEN,
                "REPO_OWNER": REPO_OWNER,
                "REPO_NAME": REPO_NAME,
                "PROJECT_NAME": PROJECT_NAME
            }.items() if not value
        ]

        if missing:
            raise ValueError(f"Missing .env values: {', '.join(missing)}")

        REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}.git"
        PROJECT_URL = f"https://github.com/{REPO_OWNER}/{PROJECT_NAME}.git"

# ==========================================
# CONFIGURATION
# ==========================================
RELEASE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = RELEASE_ROOT.parent
ENV_FILE = RELEASE_ROOT / ".env"
Builder.getEnv(ENV_FILE)

SOURCE = PROJECT_ROOT / PROJECT_NAME
GIT = PROJECT_ROOT / "cmd" / "git.exe"

BRANCH = "main"

BUILD = RELEASE_ROOT / "build"
RELEASES = RELEASE_ROOT / "releases"
REPOSITORY = BUILD / "repository"
STAGE = BUILD / "source"
ENV_CREATE = STAGE / ".env"

# ==========================================
# HELPERS
# ==========================================

def run(command, cwd=None, capture_output=False):
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=capture_output
    )

def clean_folder(folder):
    folder = Path(folder)

    def handle_remove_error(func, path, error):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except OSError:
            raise error

    if folder.exists():
        for attempt in range(5):
            try:
                shutil.rmtree(folder, onerror=handle_remove_error)
                break
            except OSError:
                if attempt == 4:
                    raise
                time.sleep(2)

    folder.mkdir(parents=True, exist_ok=True)

def github_request(url, method="GET", data=None, content_type="application/json"):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": content_type
    }

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = response.read()
            return json.loads(result) if result else {}

    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub API Error ({error.code}): {details}"
        )

def create_github_release(zip_path, version, extra_assets):
    print("\nCreating GitHub release...")

    build_file = Path("build.txt")
    release_notes = (
        build_file.read_text(encoding="utf-8").strip()
        if build_file.exists()
        else ""
    )

    if not release_notes:
        release_notes = (
            f"{PROJECT_NAME} release {version}\n\n"
            "Automatically generated release package."
        )

    for asset in extra_assets:
        if not asset.is_file():
            raise RuntimeError(f"Release asset not found: {asset}")

    api_url = (
        f"https://api.github.com/repos/"
        f"{REPO_OWNER}/{REPO_NAME}/releases"
    )

    release_data = {
        "tag_name": version,
        "target_commitish": BRANCH,
        "name": f"{PROJECT_NAME} {version}",
        "body": release_notes,
        "draft": False,
        "prerelease": False
    }

    release = github_request(
        api_url,
        method="POST",
        data=json.dumps(release_data).encode("utf-8")
    )

    print(f"Release created: {release['html_url']}")

    assets = [zip_path] + list(extra_assets)

    for asset in assets:
        print(f"\nUploading {asset.name}...")

        upload_url = (
            release["upload_url"].split("{")[0]
            + "?name="
            + asset.name
        )

        content_type = (
            "application/zip"
            if asset.suffix.lower() == ".zip"
            else "application/octet-stream"
        )

        github_request(
            upload_url,
            method="POST",
            data=asset.read_bytes(),
            content_type=content_type
        )

        print(f"Uploaded: {asset.name}")

    print("\nAll release assets uploaded successfully!")

    return release["html_url"]

def get_project_files():
    result = run([
        str(GIT),
        "-c", f"safe.directory={REPOSITORY.as_posix()}",
        "-C", str(REPOSITORY),
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z"
    ], capture_output=True)

    return [
        Path(p.decode("utf-8", errors="surrogateescape"))
        for p in result.stdout.split(b"\0")
        if p
    ]

def create_env_file():
    ENV_CREATE.parent.mkdir(parents=True, exist_ok=True)

    if not ENV_CREATE.exists():

        ENV_CREATE.write_text(
            "DJANGO_APPLICATION=Accounting\n"
            "DEFAULT_USER_PASSWORD=\n"
            "SECRET_KEY=\n"
            "SALT_KEY=\n"
            "DATABASE_NAME=\n"
            "DATABASE_HOST=\n"
            "DATABASE_PORT=\n"
            "DATABASE_USER=\n"
            "DATABASE_PASSWORD=\n"
            "SERVER_HOSTNAME=\n"
            "ALLOWED_HOSTS=127.0.0.1,localhost\n"
            "CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://127.0.0.1:3000,http://localhost:8000,http://localhost:3000\n"
            "CORS_ALLOWED_ORIGINS=http://127.0.0.1:3000,http://localhost:3000\n"
            "SERVER_SCRIPT=python manage.py runserver 127.0.0.1:8000\n",
            encoding="utf-8"
        )


# ==========================================
# MAIN BUILD
# ==========================================

def main():
    if not SOURCE.is_dir():
        raise RuntimeError(f"{PROJECT_NAME} not found: {SOURCE}")

    if not GIT.is_file():
        raise RuntimeError(f"Portable Git not found: {GIT}")

    BUILD.mkdir(parents=True, exist_ok=True)

    # --------------------------------------
    # 1. CLONE OR PULL PRIVATE REPOSITORY
    # --------------------------------------
    lock_file = REPOSITORY / ".git" / "index.lock"

    if lock_file.exists():
        raise RuntimeError(
            f"Git lock file exists: {lock_file}\n"
            "Close other Git processes and remove the stale lock file."
        )

    print("\n[1/6] Updating private repository...")
    if (REPOSITORY / ".git").is_dir():
        run([
            str(GIT),
            "-c", f"safe.directory={REPOSITORY.as_posix()}",
            "-C", str(REPOSITORY),
            "remote", "set-url", "origin", PROJECT_URL
        ])

        run([
            str(GIT),
            "-c", f"safe.directory={REPOSITORY.as_posix()}",
            "-C", str(REPOSITORY),
            "fetch", "origin", BRANCH
        ])

        run([
            str(GIT),
            "-c", f"safe.directory={REPOSITORY.as_posix()}",
            "-C", str(REPOSITORY),
            "reset", "--hard", f"origin/{BRANCH}"
        ])
    elif REPOSITORY.exists():
        raise RuntimeError(
            f"Repository folder exists but is not a Git repository: {REPOSITORY}"
        )
    else:
        run([
            str(GIT),
            "clone",
            "--branch", BRANCH,
            "--single-branch",
            PROJECT_URL,
            str(REPOSITORY)
        ])

    # --------------------------------------
    # 2. GET PROJECT FILES
    # --------------------------------------

    print("\n[2/6] Reading project files...")

    project_files = get_project_files()
    project_files = [
        relative for relative in project_files
        if relative.name.lower() != ".gitignore"
        and ".git" not in relative.parts
        and "server_launcher" not in relative.parts
    ]

    print(f"Project files found: {len(project_files)}")

    # --------------------------------------
    # 3. COPY PROJECT USING GITIGNORE
    # --------------------------------------

    print("\n[3/6] Preparing release files...")

    clean_folder(STAGE)

    copied = 0

    for relative in project_files:
        source_file = REPOSITORY / relative
        destination = STAGE / relative

        if source_file.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, destination)
            copied += 1

    print(f"Files copied: {copied}")

    # --------------------------------------
    # 4. CREATE ENVIRONMENT FILE
    # --------------------------------------

    print("\n[4/6] Creating .env file...")

    create_env_file()

    print(f"Environment file: {ENV_CREATE}")

    # --------------------------------------
    # 5. CREATE ZIP
    # --------------------------------------

    print("\n[5/6] Creating ZIP package...")

    RELEASES.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    version = f"v{timestamp}"
    zip_path = RELEASES / f"{PROJECT_NAME}_{version}.zip"

    with zipfile.ZipFile(
        zip_path,
        "w",
        zipfile.ZIP_DEFLATED
    ) as archive:
        for file in STAGE.rglob("*"):
            if file.is_file() and file.name.lower() != "update.bat":
                archive.write(file, file.relative_to(STAGE))


    print(f"Version: {version}")
    print(f"ZIP: {zip_path}")
    print(f"ZIP size: {zip_path.stat().st_size / (1024 * 1024):.2f} MB")

    # --------------------------------------
    # 6. UPLOAD TO GITHUB RELEASES
    # --------------------------------------

    print("\n[6/6] Publishing GitHub release...")

    extra_assets = [
        STAGE / "update.bat"
    ]
    
    release_url = create_github_release(zip_path,version,extra_assets)

    # --------------------------------------
    # FINISHED
    # --------------------------------------

    print("\n" + "=" * 55)
    print("BUILD AND RELEASE COMPLETED")
    print("=" * 55)

    print(f"Repository: {REPO_URL}")
    print(f"Version: {version}")
    print(f"Release: {release_url}")
    print(f"ZIP: {zip_path}")
    print(f"Files: {copied}")

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nBUILD FAILED: {error}")
        sys.exit(1)
