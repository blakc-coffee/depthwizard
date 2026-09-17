"""Private bucket I/O and signed URLs.

Owner: Backend Engineer B. See PRD §9.

One private Supabase Storage bucket (`settings.storage_bucket`), with the
four top-level prefixes fixed by the contract (PRD §7): inputs/, staging/,
outputs/, compares/. These prefixes are not configurable — they're part of
the frozen storage-path contract, not deployment config. Auth is via the
service-role key, used server-side only: the backend has already verified
the JWT and checked ownership by the time any of these functions are
called, so bypassing per-row RLS here doesn't skip an authorization check —
it IS the authorization check, done once, upstream.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from supabase import Client, create_client

from app.core.config import get_settings
from app.core.errors import ApiException, ErrorCode

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        settings = get_settings()
        _client = create_client(settings.supabase_url, settings.supabase_service_role_key.get_secret_value())
    return _client


def _bucket():
    return _get_client().storage.from_(get_settings().storage_bucket)


# Extension comes from the sniffed content type, never the client filename:
# the ML pipeline only reads GeoTIFF location data from `.tif`/`.tiff` paths.
_INPUT_EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/tiff": ".tif"}


def input_path(user_id: str, job_id: str, media_type: str) -> str:
    return f"inputs/{user_id}/{job_id}/original{_INPUT_EXTENSIONS[media_type]}"


def staging_prefix(user_id: str, job_id: str) -> str:
    return f"staging/{user_id}/{job_id}"


def outputs_prefix(user_id: str, job_id: str) -> str:
    return f"outputs/{user_id}/{job_id}"


def compares_prefix(user_id: str, compare_id: str) -> str:
    return f"compares/{user_id}/{compare_id}"


def save_input(user_id: str, job_id: str, file_bytes: bytes, content_type: str) -> str:
    """Uploads the original upload to inputs/{user_id}/{job_id}/original.<ext> (PRD §9.3)."""
    path = input_path(user_id, job_id, content_type)
    try:
        _bucket().upload(path, file_bytes, file_options={"content-type": content_type})
    except Exception as exc:
        raise ApiException(ErrorCode.RESULT_STORAGE_FAILED, "Could not store the uploaded file.") from exc
    return path


def download_input(path: str) -> Path:
    """Downloads any stored object (an upload, or a previous job's artifact
    when comparing) to a local temp file, since ML code takes filesystem
    paths. Caller owns cleanup of the returned path."""
    try:
        data = _bucket().download(path)
    except Exception as exc:
        raise ApiException(ErrorCode.RESULT_STORAGE_FAILED, "Could not read the stored input file.") from exc

    suffix = Path(path).suffix
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(data)
    tmp.close()
    return Path(tmp.name)


def upload_staged_outputs(user_id: str, job_id: str, local_paths: dict[str, Path]) -> dict[str, str]:
    """Uploads pipeline artifacts to staging/{user_id}/{job_id}/{name}.

    `local_paths` maps the FIXED contract filename (e.g. 'texture.png', PRD
    §7) to wherever the pipeline actually wrote it locally — these are
    rarely the same name (ml/pipeline.py names its own temp files).

    Nothing reaches outputs/ here — see promote_staged_outputs. Staging
    first, promoting only after re-confirming the job still exists, is what
    closes the delete-during-processing orphan window (PRD §8).
    """
    prefix = staging_prefix(user_id, job_id)
    staged: dict[str, str] = {}
    for target_name, local_path in local_paths.items():
        dest = f"{prefix}/{target_name}"
        try:
            with open(local_path, "rb") as fh:
                _bucket().upload(dest, fh.read())
        except Exception as exc:
            raise ApiException(ErrorCode.RESULT_STORAGE_FAILED, f"Could not stage artifact {target_name!r}.") from exc
        staged[target_name] = dest
    return staged


def promote_staged_outputs(user_id: str, job_id: str) -> dict[str, str]:
    """Moves everything under staging/{user_id}/{job_id}/ to
    outputs/{user_id}/{job_id}/. Call only after re-confirming the job row
    still exists (PRD §8) — this function does the storage move, not the
    existence check."""
    return _promote(staging_prefix(user_id, job_id), outputs_prefix(user_id, job_id))


def promote_staged_compare_outputs(user_id: str, compare_id: str) -> dict[str, str]:
    """Same staging-then-promote step for a comparison's artifacts (PRD §9.9),
    into compares/{user_id}/{compare_id}/."""
    return _promote(staging_prefix(user_id, compare_id), compares_prefix(user_id, compare_id))


def _promote(from_prefix: str, to_prefix: str) -> dict[str, str]:
    bucket = _bucket()

    try:
        entries = bucket.list(from_prefix)
    except Exception as exc:
        raise ApiException(ErrorCode.RESULT_STORAGE_FAILED, "Could not list staged artifacts.") from exc

    promoted: dict[str, str] = {}
    for entry in entries:
        name = entry["name"]
        src = f"{from_prefix}/{name}"
        dest = f"{to_prefix}/{name}"
        try:
            bucket.move(src, dest)
        except Exception as exc:
            raise ApiException(ErrorCode.RESULT_STORAGE_FAILED, f"Could not promote artifact {name!r}.") from exc
        promoted[name] = dest
    return promoted


def delete_staging(user_id: str, job_id: str) -> None:
    """Cleans up staging/{user_id}/{job_id}/ — called when the job row is
    gone by the time the worker tries to promote (PRD §8)."""
    _remove_prefix(staging_prefix(user_id, job_id))


def delete_job_artifacts(user_id: str, job_id: str) -> None:
    """Purges inputs/, staging/, and outputs/ for a job (PRD §8 deletion semantics)."""
    _remove_prefix(f"inputs/{user_id}/{job_id}")
    _remove_prefix(staging_prefix(user_id, job_id))
    _remove_prefix(outputs_prefix(user_id, job_id))


def delete_compare_artifacts(user_id: str, compare_id: str) -> None:
    """Purges compares/{user_id}/{compare_id}/ (PRD §8 cascade-on-delete)."""
    _remove_prefix(f"compares/{user_id}/{compare_id}")


def _remove_prefix(prefix: str) -> None:
    bucket = _bucket()
    try:
        entries = bucket.list(prefix)
        if not entries:
            return
        bucket.remove([f"{prefix}/{entry['name']}" for entry in entries])
    except Exception as exc:
        raise ApiException(ErrorCode.RESULT_STORAGE_FAILED, f"Could not delete storage prefix {prefix!r}.") from exc


def create_signed_url(path: str, expiry_minutes: int | None = None) -> str:
    """Signed URL generated only after the caller has already verified the
    JWT and checked ownership, in that order (PRD §7) — this function trusts
    its caller on that."""
    settings = get_settings()
    minutes = expiry_minutes or settings.signed_url_expiry_minutes
    try:
        result = _bucket().create_signed_url(path, minutes * 60)
    except Exception as exc:
        raise ApiException(ErrorCode.RESULT_STORAGE_FAILED, "Could not create a signed URL.") from exc
    # supabase-py's response key casing has varied across versions.
    return result.get("signedURL") or result.get("signed_url") or result["signedUrl"]
