"""TSM update manifest client and verified release downloader."""
import hashlib
import json
import urllib.parse
import urllib.request


MANIFEST_URL = (
    "https://aliyusbly.eu.pythonanywhere.com/api/updates/latest"
)


def fetch_manifest(platform_name, channel):
    query = urllib.parse.urlencode({
        "platform": platform_name,
        "channel": channel,
    })

    req = urllib.request.Request(
        f"{MANIFEST_URL}?{query}",
        headers={
            "Accept": "application/json",
            "User-Agent": "TSM-Updater",
        },
    )

    with urllib.request.urlopen(req, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))

    if not isinstance(data, dict):
        raise ValueError("Update server returned an invalid manifest.")

    return data


def version_tuple(value):
    parts = str(value).strip().lstrip("vV").split(".")

    try:
        return tuple(int(p.split("-", 1)[0]) for p in parts)
    except ValueError:
        raise ValueError(f"Invalid version string: {value!r}")


def is_newer(remote, current):
    return version_tuple(remote) > version_tuple(current)


def download_verified(url, expected_sha256, destination):
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("Update URL must use HTTPS.")

    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
    ):
        raise ValueError(
            "Update manifest has no valid SHA-256 checksum."
        )

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "TSM-Updater"},
    )

    digest = hashlib.sha256()

    with urllib.request.urlopen(req, timeout=60) as response:
        with open(destination, "wb") as out:
            while True:
                chunk = response.read(1024 * 1024)

                if not chunk:
                    break

                digest.update(chunk)
                out.write(chunk)

    actual = digest.hexdigest()

    if actual.lower() != expected_sha256.lower():
        import os

        try:
            os.unlink(destination)
        except OSError:
            pass

        raise ValueError(
            "Downloaded update failed SHA-256 verification; file deleted."
        )

    return actual