import hashlib
import os

CHUNK_SIZE = 65536


def compute_sha256(file_path: str) -> dict:
    result = {"hash": None, "error": None}

    if not file_path or not os.path.isfile(file_path):
        result["error"] = "File not found. It may have been moved, renamed, or deleted."
        return result

    try:
        sha256 = hashlib.sha256()

        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(CHUNK_SIZE)

                if not chunk:
                    break

                sha256.update(chunk)

        result["hash"] = sha256.hexdigest()

    except FileNotFoundError:
        result["error"] = "File not found while computing the hash."

    except PermissionError:
        result["error"] = "Permission denied while reading the file."

    except OSError as e:
        result["error"] = f"A file system error occurred while reading the file: {e}"

    except Exception as e:
        result["error"] = f"Unexpected error while computing SHA-256: {e}"

    return result


def compare_hashes(hash_a: str, hash_b: str) -> bool:
    try:
        if not hash_a or not hash_b:
            return False

        return hash_a.strip().lower() == hash_b.strip().lower()

    except Exception:
        return False