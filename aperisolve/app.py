"""Aperi'Solve Flask application."""

import base64
import hashlib
import json
import os
import shutil
import time
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from io import BytesIO
from urllib.parse import quote_from_bytes
from pathlib import Path
from typing import Any, cast

import sentry_sdk
from flask import Flask, Response, abort, jsonify, redirect, render_template, request, send_file
from flask_babel import Babel, get_locale
from flask_babel import gettext as _
from redis import Redis
from redis.exceptions import RedisError
from rq import Queue
from PIL import Image as PillowImage
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.wrappers.response import Response as WerkzeugResponse

from .analyzers.registry import archive_tools, tool_order
from .cheatsheet import cheatsheet_bp, cheatsheet_lastmod
from .config import (
    CLEANUP_INTERVAL_SECONDS,
    DB_URI,
    FLASK_DEBUG,
    GOOGLE_ADS_TXT,
    IMAGE_EXTENSIONS,
    JOB_TIMEOUT,
    MAX_CONTENT_LENGTH,
    PROJECT_VERSION,
    REDIS_URL,
    REMOVAL_MIN_AGE_SECONDS,
    REMOVED_IMAGES_FOLDER,
    RESULT_FOLDER,
    SITE_BASE_URL,
)
from .filetype import detect_file_type
from .i18n import (
    DEFAULT_LANG,
    LANG_PREFIX_RULE,
    OG_LOCALES,
    PREFIX_LANGS,
    SUPPORTED_LANGS,
    alternates_for,
    js_catalog,
    lang_prefix,
    select_locale,
)
from .limits import is_local_request, limiter
from .models import Image, Submission, UploadLog, cleanup_old_entries, db
from .omni import configure_omni
from .pages import pages_bp
from .site_content import promo_html
from .utils.sentry import initialize_sentry
from .utils.utils import get_client_ip
from .wiki import page_lastmod, translated_langs, wiki_bp, wiki_pages, wiki_tool_names

CLEANUP_LOCK_KEY = "aperisolve:cleanup-lock"

_is_local_request = is_local_request


def _configure_app(app: Flask) -> None:
    """Configure Flask and extension settings."""
    app.config["JSON_SORT_KEYS"] = False
    app.config["PROJECT_VERSION"] = PROJECT_VERSION
    app.config["SQLALCHEMY_DATABASE_URI"] = DB_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    app.config["REDIS_QUEUE"] = Queue(connection=Redis.from_url(REDIS_URL))
    app.config["TOOL_ORDER"] = tool_order()
    # Static asset URLs are cache-busted with ?v=<PROJECT_VERSION> in templates.
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = timedelta(days=7)
    Babel(app, locale_selector=select_locale)
    limiter.init_app(app)
    db.init_app(app)


def _extract_unique_ips(upload_logs: list[UploadLog]) -> set[str]:
    """Return unique non-empty uploader IP addresses from logs."""
    return {str(log.ip_address) for log in upload_logs if log.ip_address}


def _archive_original_image(
    original_image_path: Path,
    image_hash: str,
    submission_hash: str,
) -> None:
    """Archive original image file before deletion."""
    if not original_image_path.exists():
        return
    REMOVED_IMAGES_FOLDER.mkdir(parents=True, exist_ok=True)
    dt = datetime.now(UTC).isoformat()
    archive_filename = f"{image_hash}_{submission_hash}_{dt}{original_image_path.suffix}"
    archive_path = REMOVED_IMAGES_FOLDER / archive_filename
    shutil.copy2(original_image_path, archive_path)


def _remove_result_folder(image_hash: str, submission_hash: str) -> None:
    """Delete result folder for a submission if it exists."""
    result_path = RESULT_FOLDER / image_hash / submission_hash
    if result_path.exists():
        shutil.rmtree(result_path)


def _delete_submission_entities(
    submission: Submission,
    image: Image,
    original_image_path: Path,
) -> None:
    """Delete submission and related image entity if applicable."""
    db.session.delete(submission)
    if len(image.submissions) <= 1:
        if original_image_path.exists():
            original_image_path.unlink()
        db.session.delete(image)
    db.session.commit()


def _base_url() -> str:
    """Public base URL for absolute links (canonical, Open Graph, sitemap)."""
    return SITE_BASE_URL or request.url_root.rstrip("/")


def _register_error_handlers(app: Flask) -> None:
    """Register application-wide error handlers."""

    @app.context_processor
    def inject_datetime() -> dict[str, type[datetime]]:
        """Inject datetime into all templates."""
        return {"datetime": datetime}

    @app.context_processor
    def inject_base_url() -> dict[str, str]:
        """Inject the public base URL into all templates."""
        return {"base_url": _base_url()}

    @app.context_processor
    def inject_site_content() -> dict[str, str | None]:
        """Inject deployment-local site content (promo banner); None when absent."""
        return {"promo_html": promo_html(str(get_locale()))}

    @app.context_processor
    def inject_i18n() -> dict[str, Any]:
        """Inject language context: prefix, switcher targets, JS catalog."""
        switch = None
        endpoint = request.endpoint or ""
        if endpoint.startswith(
            ("pages.", "wiki.", "cheatsheet.", "pages_i18n.", "wiki_i18n.", "cheatsheet_i18n."),
        ):
            bare = request.path
            prefix = lang_prefix()
            if prefix and bare.startswith(prefix):
                bare = bare[len(prefix) :] or "/"
            switch = [
                (lang, bare if lang == DEFAULT_LANG else f"/{lang}{bare}")
                for lang in SUPPORTED_LANGS
            ]
        current = str(get_locale())
        return {
            "lang_prefix": lang_prefix(),
            "current_lang": current,
            "js_i18n": js_catalog(),
            "lang_switch": switch,
            "wiki_tools": sorted(wiki_tool_names()),
            "og_locale": OG_LOCALES.get(current, "en_US"),
            "og_locale_alternates": [v for k, v in OG_LOCALES.items() if k != current],
        }

    @app.errorhandler(413)
    def too_large(_error: object) -> tuple[Response, int]:
        """Handle max upload size errors."""
        sentry_sdk.set_context(
            "upload",
            {
                "content_length": request.content_length,
                "max_allowed": app.config["MAX_CONTENT_LENGTH"],
            },
        )
        sentry_sdk.capture_message("Upload failed: 413 Payload Too Large", level="warning")
        return jsonify({"error": _("Image size exceeded")}), 413

    @app.errorhandler(404)
    def not_found(_error: object) -> tuple[str, int]:
        """Handle not found errors."""
        return render_template("error.html", message=_("Resource not found"), statuscode=404), 404

    @app.errorhandler(429)
    def too_many_requests(_error: object) -> tuple[Response, int]:
        """Handle rate-limit errors with the JSON shape the frontend renders."""
        return jsonify({"error": _("Too many requests, please slow down.")}), 429


def _register_page_routes(app: Flask) -> None:
    """Register non-translated page routes (translated pages live in pages_bp)."""

    @app.route("/faq")
    def faq() -> WerkzeugResponse:
        """Redirect the legacy FAQ URL to the cheatsheet."""
        return redirect("/cheatsheet", code=301)

    @app.route("/<string(length=32):hash_val>", methods=["GET"])
    def result_page(hash_val: str) -> str:
        """Render the result page for a given submission hash (32-hex md5)."""
        submission = Submission.query.get_or_404(hash_val)
        Image.query.get_or_404(submission.image_hash)
        return render_template("result.html", hash_val=hash_val)

    @app.route("/ads.txt")
    def google_ads() -> str:
        """Serve the Google Ads required file."""
        return GOOGLE_ADS_TXT

    @app.route("/robots.txt")
    def robots_txt() -> Response:
        """Serve crawler directives; API endpoints are not for indexing."""
        lines = [
            "User-agent: *",
            *[
                f"Disallow: {path}"
                for path in (
                    "/upload",
                    "/status/",
                    "/result/",
                    "/infos/",
                    "/image/",
                    "/download/",
                    "/remove/",
                    "/remove_password/",
                )
            ],
            "",
            f"Sitemap: {_base_url()}/sitemap.xml",
            "",
        ]
        return Response("\n".join(lines), mimetype="text/plain")

    @app.route("/sitemap.xml")
    def sitemap_xml() -> Response:
        """Serve the sitemap with lastmod dates and hreflang alternates."""
        base = _base_url()
        parts = []
        for path, lastmod, alts in _sitemap_entries():
            links = "".join(
                f'<xhtml:link rel="alternate" hreflang="{code}" href="{base}{href}"/>'
                for code, href in alts
            )
            lastmod_tag = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
            parts.append(f"<url><loc>{base}{path}</loc>{lastmod_tag}{links}</url>")
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:xhtml="http://www.w3.org/1999/xhtml">'
            f"{''.join(parts)}</urlset>"
        )
        return Response(xml, mimetype="application/xml")


def _sitemap_entries() -> list[tuple[str, str | None, list[tuple[str, str]]]]:
    """(path, lastmod, hreflang alternates) for every indexable URL.

    Wiki pages only list languages with a real translation; untranslated
    fallbacks canonicalize to English and stay out of the sitemap.
    """
    home_alts = alternates_for("/")
    entries: list[tuple[str, str | None, list[tuple[str, str]]]] = [("/", None, home_alts)]
    entries += [(f"/{lang}/", None, home_alts) for lang in PREFIX_LANGS]
    # The standalone cheatsheet is English-only for now; only the English URL is
    # indexable (prefixed languages fall back and canonicalize to it).
    entries.append(
        ("/cheatsheet", cheatsheet_lastmod(), alternates_for("/cheatsheet", [DEFAULT_LANG])),
    )
    for page in wiki_pages():
        langs = translated_langs(page.slug)
        alts = alternates_for(page.path, [DEFAULT_LANG, *langs])
        entries.append((page.path, page_lastmod(DEFAULT_LANG, page.slug), alts))
        entries.extend(
            (f"/{lang}{page.path}", page_lastmod(lang, page.slug), alts) for lang in langs
        )
    return entries


def _acquire_cleanup_lock(app: Flask) -> bool:
    """Claim the per-interval cleanup lock. False on contention or Redis error.

    A Redis ``SET NX EX`` ensures a single process (a gunicorn worker or the
    cron scheduler) drives the sweep per interval; everyone else backs off.
    """
    redis_conn = app.config["REDIS_QUEUE"].connection
    try:
        return bool(
            redis_conn.set(
                CLEANUP_LOCK_KEY,
                "1",
                nx=True,
                ex=CLEANUP_INTERVAL_SECONDS,
            ),
        )
    except RedisError as exc:
        sentry_sdk.capture_exception(exc)
        return False


def run_cleanup_with_lock(app: Flask) -> None:
    """Run the retention sweep inline, at most once per interval, cluster-wide.

    Used by the cron worker (``aperisolve/tasks.py``), which runs off the
    request path where a long sweep cannot abort an HTTP worker.
    """
    if _acquire_cleanup_lock(app):
        cleanup_old_entries()


def schedule_cleanup(app: Flask) -> None:
    """Enqueue the retention sweep as a background job, once per interval.

    The request path calls this as a safety net for when the cron service is
    down. Running the sweep inline in a gunicorn worker risked exceeding the
    (30 s default) worker timeout on a large backlog and aborting the request
    with ``SystemExit`` (issue #191); enqueuing keeps it off the request path.
    The interval lock is claimed here so at most one job is queued per
    interval, and the job runs the sweep directly without re-claiming it.
    """
    if _acquire_cleanup_lock(app):
        try:
            app.config["REDIS_QUEUE"].enqueue(
                "aperisolve.tasks.cleanup_sweep_job",
                job_timeout=JOB_TIMEOUT,
            )
        except RedisError as exc:
            sentry_sdk.capture_exception(exc)


def _get_or_create_image(img_hash: str, new_img_path: Path, size: int) -> Image:
    """Fetch the Image row or insert it, tolerating a concurrent insert."""
    sub_img = Image.query.filter_by(hash=img_hash).first()
    if sub_img is None:
        sub_img = Image(
            file=str(new_img_path),
            hash=img_hash,
            size=size,
            upload_count=0,
            first_submission_date=datetime.now(UTC),
            last_submission_date=datetime.now(UTC),
        )
        db.session.add(sub_img)
        try:
            db.session.commit()
        except IntegrityError:
            # A concurrent identical upload won the insert race; use its row.
            db.session.rollback()
            sub_img = Image.query.filter_by(hash=img_hash).one()
    return sub_img


def _upload_image(app: Flask) -> tuple[Response, int]:
    """Handle image upload and initiate analysis."""
    # The cron service is the primary cleanup driver; this enqueue is a safety
    # net for when it is down. It runs off the request path (issue #191) and is
    # a no-op whenever the cron job already holds the interval lock.
    schedule_cleanup(app)

    if "image" not in request.files:
        return jsonify({"error": _("No image provided")}), 400

    image = request.files["image"]
    password = request.form.get("password")
    deep_analysis = request.form.get("deep") == "true"

    if image.filename is None or image.filename == "":
        return jsonify({"error": _("No image provided")}), 400

    # Any file type is accepted; only require a usable extension because storage
    # and get_image split the stored name on ".".
    if "." not in image.filename or not Path(image.filename).suffix:
        return jsonify({"error": _("Unsupported file type")}), 400

    image_data = image.read()
    img_hash = hashlib.md5(image_data, usedforsecurity=False).hexdigest()
    image_name = img_hash + "." + image.filename.rsplit(".", maxsplit=1)[-1].lower()

    submission_data = (
        image_data
        + image.filename.encode()
        + (password.encode() if password else b"")
        + (b"deep_analysis" if deep_analysis else b"")
    )
    submission_hash = hashlib.md5(submission_data, usedforsecurity=False).hexdigest()
    submission_path = RESULT_FOLDER / img_hash / submission_hash

    client_ip = get_client_ip()
    user_agent = request.headers.get("User-Agent", "Unknown")

    upload_log = UploadLog(
        ip_address=client_ip,
        user_agent=user_agent,
        image_hash=img_hash,
        submission_hash=submission_hash,
        filename=image.filename,
    )
    db.session.add(upload_log)
    db.session.commit()

    submission = Submission.query.filter_by(hash=submission_hash).first()
    if submission_path.exists() and submission is not None:
        return jsonify({"submission_hash": submission.hash}), 200

    new_img_path = RESULT_FOLDER / img_hash / image_name
    if not new_img_path.exists():
        new_img_path.parent.mkdir(parents=True, exist_ok=True)
        with new_img_path.open("wb") as file_obj:
            file_obj.write(image_data)

    sub_img = _get_or_create_image(img_hash, new_img_path, len(image_data))

    sub_img_any = cast("Any", sub_img)
    sub_img_any.upload_count = int(sub_img_any.upload_count or 0) + 1
    db.session.commit()

    submission_path.mkdir(parents=True, exist_ok=True)
    if not submission:
        submission = Submission(
            filename=image.filename,
            password=password,
            deep_analysis=deep_analysis,
            hash=submission_hash,
            status="pending",
            date=time.time(),
            image_hash=sub_img.hash,
        )
        db.session.add(submission)
        try:
            db.session.commit()
        except IntegrityError:
            # A concurrent identical upload won the insert race; use its row.
            db.session.rollback()
            submission = Submission.query.filter_by(hash=submission_hash).one()

    submission_any = cast("Any", submission)
    submission_any.status = "pending"
    db.session.commit()

    app.config["REDIS_QUEUE"].enqueue(
        "aperisolve.workers.analyze_image",
        submission.hash,
        # Analyzer subprocess timeouts (SUBPROCESS_TIMEOUT) must fire before RQ
        # kills the job, so partial results get written and the submission
        # never sticks in "running".
        job_timeout=JOB_TIMEOUT,
    )
    return jsonify({"submission_hash": submission.hash}), 200


def _register_submission_routes(app: Flask) -> None:
    """Register upload and status routes."""

    @app.route("/upload", methods=["POST"])
    @limiter.limit("10 per minute; 100 per hour", exempt_when=_is_local_request)
    def upload_image() -> tuple[Response, int]:
        return _upload_image(app)

    @app.route("/status/<hash_val>", methods=["GET"])
    @limiter.limit("240 per minute", exempt_when=_is_local_request)
    def get_status(hash_val: str) -> Response:
        """Get the processing status of a submission."""
        submission = Submission.query.get_or_404(hash_val)
        response = jsonify({"status": submission.status})
        response.headers["Cache-Control"] = "no-store"
        return response


def _keyword_patterns(query: str) -> dict[str, bytes]:
    """Build common textual encodings for a keyword, omitting duplicates."""
    raw = query.encode("utf-8")
    base64_value = base64.b64encode(raw)
    base32_value = base64.b32encode(raw)
    hex_value = raw.hex().encode("ascii")
    binary_value = " ".join(f"{byte:08b}" for byte in raw).encode("ascii")
    candidates = {
        "text": raw,
        "base64": base64_value,
        "base64 (unpadded)": base64_value.rstrip(b"="),
        "base32": base32_value,
        "base32 (unpadded)": base32_value.rstrip(b"="),
        "binary": "".join(f"{byte:08b}" for byte in raw).encode("ascii"),
        "binary (spaced)": binary_value,
        "hex": hex_value,
        "hex (uppercase)": hex_value.upper(),
        "URL encoded": quote_from_bytes(raw, safe="").encode("ascii"),
        "decimal": " ".join(str(byte) for byte in raw).encode("ascii"),
    }
    patterns: dict[str, bytes] = {}
    seen: set[bytes] = set()
    for label, pattern in candidates.items():
        if pattern and pattern not in seen:
            patterns[label] = pattern
            seen.add(pattern)
    return patterns


def _find_keyword_matches(data: bytes, patterns: dict[str, bytes]) -> list[str]:
    """Return matching encodings, treating only the literal text case-insensitively."""
    lowered = data.lower()
    matches = []
    for encoding, pattern in patterns.items():
        haystack = lowered if encoding == "text" else data
        needle = pattern.lower() if encoding == "text" else pattern
        if needle in haystack:
            matches.append(encoding)
    return matches


def _search_file_patterns(path: Path, patterns: dict[str, bytes]) -> dict[str, list[int]]:
    """Search a large file in bounded chunks and retain at most 100 offsets per encoding."""
    if not patterns:
        return {}
    max_pattern_length = max(map(len, patterns.values()))
    found: dict[str, list[int]] = {name: [] for name in patterns}
    carry = b""
    position = 0
    with path.open("rb") as file_obj:
        while chunk := file_obj.read(1024 * 1024):
            data = carry + chunk
            base_offset = position - len(carry)
            for encoding, pattern in patterns.items():
                offsets = found[encoding]
                if len(offsets) >= 100:
                    continue
                haystack = data.lower() if encoding == "text" else data
                needle = pattern.lower() if encoding == "text" else pattern
                start = 0
                while len(offsets) < 100 and (match_at := haystack.find(needle, start)) >= 0:
                    absolute = base_offset + match_at
                    if absolute >= 0 and absolute not in offsets:
                        offsets.append(absolute)
                    start = match_at + 1
            if all(len(offsets) >= 100 for offsets in found.values()):
                break
            position += len(chunk)
            carry = data[-(max_pattern_length - 1):] if max_pattern_length > 1 else b""
    return {encoding: offsets for encoding, offsets in found.items() if offsets}


def _build_result_response(result_path: Path) -> Response | tuple[Response, int]:
    """Build the /result response with an ETag over the raw results.json bytes.

    The frontend polls this endpoint while analysis runs; the ETag turns
    unchanged polls into 304s.
    """
    if not result_path.exists():
        response = jsonify({"error": _("Results not ready yet...")})
        response.headers["Cache-Control"] = "no-store"
        return response, 425

    raw = result_path.read_bytes()
    try:
        results = json.loads(raw)
    except json.JSONDecodeError:
        response = jsonify({"error": _("Results not ready yet...")})
        response.headers["Cache-Control"] = "no-store"
        return response, 425

    response = jsonify({"results": results})
    response.headers["Cache-Control"] = "no-cache"
    response.set_etag(hashlib.md5(raw, usedforsecurity=False).hexdigest())
    return cast("Response", response.make_conditional(request))


def _register_data_routes(app: Flask) -> None:
    """Register metadata, results, and download routes."""

    @app.route("/infos/<hash_val>", methods=["GET"])
    @limiter.limit("60 per minute", exempt_when=_is_local_request)
    def get_infos(hash_val: str) -> Response:
        """Get the metadata and information of a submission."""
        submission = Submission.query.get_or_404(hash_val)
        image = Image.query.get_or_404(submission.image_hash)
        names = [name for name in {sub.filename for sub in image.submissions} if name]
        passwords = [pwd for pwd in {sub.password for sub in image.submissions} if pwd]
        # detect_file_type is best-effort and never raises; kind drives the
        # frontend preview (image/video/audio/pdf/other) and mime is informational.
        file_type = detect_file_type(Path(image.file))
        response = jsonify(
            {
                "image_path": "image/" + str(Path(image.file).name),
                "kind": file_type.kind,
                "mime": file_type.mime,
                "names": names,
                "size": image.size,
                "first_submission_date": image.first_submission_date,
                "last_submission_date": image.last_submission_date,
                "upload_count": image.upload_count,
                "passwords": passwords,
                "removal_min_age_seconds": REMOVAL_MIN_AGE_SECONDS,
                "submission_date": submission.date,
            },
        )
        response.headers["Cache-Control"] = "private, max-age=30"
        return response

    @app.route("/gif-frames/<hash_val>", methods=["GET"])
    @limiter.limit("60 per minute", exempt_when=_is_local_request)
    def get_gif_frames(hash_val: str) -> Response:
        """Return frame count for an animated GIF submission."""
        submission = Submission.query.get_or_404(hash_val)
        image = Image.query.get_or_404(submission.image_hash)
        input_path = Path(image.file)
        if not input_path.is_file():
            abort(404, description="Original file not found.")
        try:
            with PillowImage.open(input_path) as source:
                frame_count = getattr(source, "n_frames", 1) if source.format == "GIF" else 0
        except (OSError, ValueError, PillowImage.DecompressionBombError):
            frame_count = 0
        response = jsonify({"frame_count": frame_count})
        response.headers["Cache-Control"] = "private, max-age=300"
        return response

    @app.route("/gif-frame-preview/<hash_val>/<int:frame_index>", methods=["GET"])
    @limiter.limit("600 per minute", exempt_when=_is_local_request)
    def get_gif_frame_preview(hash_val: str, frame_index: int) -> Response:
        """Render one small PNG preview from an uploaded animated GIF."""
        submission = Submission.query.get_or_404(hash_val)
        image = Image.query.get_or_404(submission.image_hash)
        input_path = Path(image.file)
        if not input_path.is_file():
            abort(404, description="Original file not found.")
        try:
            with PillowImage.open(input_path) as source:
                if source.format != "GIF" or frame_index >= getattr(source, "n_frames", 1):
                    abort(404, description="GIF frame not found.")
                source.seek(frame_index)
                preview = source.convert("RGBA")
                preview.thumbnail((112, 84), PillowImage.Resampling.LANCZOS)
                buffer = BytesIO()
                preview.save(buffer, format="PNG", optimize=True)
        except (OSError, ValueError, EOFError, PillowImage.DecompressionBombError):
            abort(422, description="GIF frame could not be decoded.")
        buffer.seek(0)
        response = send_file(buffer, mimetype="image/png", max_age=86400)
        response.headers["Cache-Control"] = "private, max-age=86400"
        return response

    @app.route("/decomposer-frame/<hash_val>/<int:frame_index>", methods=["POST"])
    @limiter.limit("60 per minute", exempt_when=_is_local_request)
    def decompose_gif_frame(hash_val: str, frame_index: int) -> tuple[Response, int] | Response:
        """Build bit-plane images for one GIF frame selected in the result UI."""
        submission = Submission.query.get_or_404(hash_val)
        if submission.status != "completed":
            return jsonify({"error": _("Results not ready yet...")}), 425
        image = Image.query.get_or_404(submission.image_hash)
        input_path = Path(image.file)
        if not input_path.is_file():
            abort(404, description="Original file not found.")
        try:
            with PillowImage.open(input_path) as source:
                if source.format != "GIF":
                    abort(404, description="Animated GIF not found.")
                frame_count = getattr(source, "n_frames", 1)
        except (OSError, ValueError, PillowImage.DecompressionBombError):
            abort(422, description="GIF could not be decoded.")
        if frame_index < 0 or frame_index >= frame_count:
            abort(404, description="GIF frame not found.")

        from .analyzers.decomposer import DecomposerAnalyzer

        output_dir = RESULT_FOLDER / str(image.hash) / str(submission.hash)
        result = DecomposerAnalyzer(input_path, output_dir).get_frame_results(frame_index)
        status_code = HTTPStatus.OK if result.get("status") == "ok" else HTTPStatus.UNPROCESSABLE_ENTITY
        response = jsonify(result)
        response.headers["Cache-Control"] = "no-store"
        return response, status_code

    @app.route("/hex-preview/<hash_val>", methods=["GET"])
    @limiter.limit("60 per minute", exempt_when=_is_local_request)
    def get_hex_preview(hash_val: str) -> Response:
        """Return a bounded hexadecimal window for the Strings byte view."""
        submission = Submission.query.get_or_404(hash_val)
        image = Image.query.get_or_404(submission.image_hash)
        input_path = Path(image.file)
        if not input_path.is_file():
            abort(404, description="Original file not found.")

        file_size = input_path.stat().st_size
        load_full_file = request.args.get("full", default="0") == "1"
        requested_offset = request.args.get("offset", default=0, type=int) or 0
        if load_full_file:
            window_start = 0
        else:
            requested_offset = max(0, min(requested_offset, max(0, file_size - 1)))
            window_start = max(0, requested_offset - 2048)
            window_start = (window_start // 16) * 16
        with input_path.open("rb") as file_obj:
            if load_full_file:
                data = file_obj.read()
            else:
                file_obj.seek(window_start)
                data = file_obj.read(4096)
        rows = [
            {
                "offset": window_start + start,
                "offset_hex": f"{window_start + start:08X}",
                "hex": " ".join(f"{value:02X}" for value in data[start : start + 16]),
                "ascii": "".join(
                    chr(value) if 32 <= value <= 126 else "."
                    for value in data[start : start + 16]
                ),
            }
            for start in range(0, len(data), 16)
        ]
        response = jsonify(
            {
                "file_size": file_size,
                "preview_start": window_start,
                "preview_bytes": len(data),
                "preview_truncated": window_start + len(data) < file_size,
                "hex_rows": rows,
            },
        )
        response.headers["Cache-Control"] = "private, max-age=300"
        return response

    @app.route("/hex-search/<hash_val>", methods=["GET"])
    @limiter.limit("60 per minute", exempt_when=_is_local_request)
    def search_hex_file(hash_val: str) -> Response:
        """Find ASCII and hexadecimal byte matches across the complete file."""
        submission = Submission.query.get_or_404(hash_val)
        image = Image.query.get_or_404(submission.image_hash)
        input_path = Path(image.file)
        if not input_path.is_file():
            abort(404, description="Original file not found.")

        query = request.args.get("q", "").strip()
        if not query or len(query) > 128:
            return jsonify({"matches": [], "truncated": False})

        patterns: set[tuple[bytes, bool]] = set()
        try:
            ascii_pattern = query.encode("ascii").lower()
        except UnicodeEncodeError:
            ascii_pattern = b""
        if ascii_pattern:
            patterns.add((ascii_pattern, True))

        compact_hex = "".join(char for char in query if char not in " \t\r\n,:-")
        if compact_hex and len(compact_hex) % 2 == 0 and all(char in "0123456789abcdefABCDEF" for char in compact_hex):
            patterns.add((bytes.fromhex(compact_hex), False))

        if not patterns:
            return jsonify({"matches": [], "truncated": False})

        max_matches = 20000
        overlap_size = max(len(pattern) for pattern, _ in patterns) - 1
        matches: set[int] = set()
        truncated = False
        carry = b""
        position = 0
        with input_path.open("rb") as file_obj:
            while chunk := file_obj.read(1024 * 1024):
                data = carry + chunk
                base_offset = position - len(carry)
                lowered_data = data.lower()
                for pattern, case_insensitive in patterns:
                    search_data = lowered_data if case_insensitive else data
                    start = 0
                    while (found := search_data.find(pattern, start)) >= 0:
                        absolute_offset = base_offset + found
                        if absolute_offset >= 0:
                            if absolute_offset not in matches and len(matches) >= max_matches:
                                truncated = True
                                break
                            matches.add(absolute_offset)
                        start = found + 1
                    if truncated:
                        break
                if truncated:
                    break
                position += len(chunk)
                carry = data[-overlap_size:] if overlap_size else b""

        response = jsonify({"matches": sorted(matches), "truncated": truncated})
        response.headers["Cache-Control"] = "private, max-age=30"
        return response

    @app.route("/keyword-search/<hash_val>", methods=["GET"])
    @limiter.limit("60 per minute", exempt_when=_is_local_request)
    def keyword_search(hash_val: str) -> Response:
        """Search the original file and saved analyzer outputs for keyword encodings."""
        submission = Submission.query.get_or_404(hash_val)
        image = Image.query.get_or_404(submission.image_hash)
        query = request.args.get("q", "").strip()
        if not query or len(query) > 128:
            return jsonify({"query": query, "matches": [], "truncated": False})

        patterns = _keyword_patterns(query)
        input_path = Path(image.file)
        matches: list[dict[str, Any]] = []
        if input_path.is_file():
            offsets = _search_file_patterns(input_path, patterns)
            if offsets:
                matches.append({"tool": "original", "encodings": list(offsets), "offsets": offsets})

        result_path = RESULT_FOLDER / str(image.hash) / str(submission.hash) / "results.json"
        try:
            results = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            results = {}
        if isinstance(results, dict):
            for tool, result in results.items():
                if not isinstance(result, dict):
                    continue
                output = json.dumps(result, ensure_ascii=False, sort_keys=True).encode("utf-8")
                encodings = _find_keyword_matches(output, patterns)
                if encodings:
                    matches.append({"tool": str(tool), "encodings": encodings, "offsets": {}})

        response = jsonify({"query": query, "matches": matches, "truncated": False})
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/result/<hash_val>", methods=["GET"])
    @limiter.limit("240 per minute", exempt_when=_is_local_request)
    def get_result(hash_val: str) -> Response | tuple[Response, int]:
        """Get the analysis results of a submission."""
        submission = Submission.query.get_or_404(hash_val)
        image = Image.query.get_or_404(submission.image_hash)
        result_path = RESULT_FOLDER / str(image.hash) / str(submission.hash) / "results.json"
        # Result JSON is retained across deployments. Populate newly added
        # analyzers the first time a completed legacy result is opened, so
        # users do not need to upload the same file again.
        if submission.status == "completed" and result_path.is_file():
            try:
                cached_results = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                cached_results = {}
            cached_results = cached_results if isinstance(cached_results, dict) else {}
            input_path = Path(image.file)
            if input_path.is_file():
                if "file_anomalies" not in cached_results:
                    from .analyzers.file_anomalies import FileAnomaliesAnalyzer

                    FileAnomaliesAnalyzer(input_path, result_path.parent).analyze()
                if (
                    "base64_images" not in cached_results
                    and detect_file_type(input_path).kind == "image"
                ):
                    from .analyzers.base64_images import Base64ImagesAnalyzer

                    Base64ImagesAnalyzer(input_path, result_path.parent).analyze()
        return _build_result_response(result_path)

    @app.route("/download/<hash_val>/<tool>")
    @limiter.limit("30 per minute; 300 per hour", exempt_when=_is_local_request)
    def download_output(hash_val: str, tool: str) -> Response:
        """Download output of a specific analyzer for a submission hash."""
        submission = Submission.query.filter_by(hash=hash_val).first_or_404()
        image = Image.query.get_or_404(submission.image_hash)
        output_dir = RESULT_FOLDER / str(image.hash) / str(submission.hash)
        output_file = output_dir / f"{tool}.7z"

        if tool not in archive_tools() or not output_file.exists():
            abort(404, description="Tool output not found.")

        response = send_file(output_file, as_attachment=True)
        response.headers["Cache-Control"] = "public, max-age=86400"
        return response

    @app.route("/image/<img_name>")
    @app.route("/image/<hash_val>/<img_name>")
    # Generous: one result page legitimately fetches ~40 derived images in a
    # burst (they cache immutably afterwards).
    @limiter.limit("600 per minute", exempt_when=_is_local_request)
    def get_image(hash_val: str | None = None, img_name: str | None = None) -> Response:
        """Download an image for a submission hash or by direct image filename.

        Usually this serves derived images generated by the decomposer analyzer.
        """
        if img_name is None:
            return abort(404, description="Image not found or unsupported format")

        # The original upload (/image/<name>) may be any stored file type; the
        # derived sub-path (/image/<hash>/<name>) only ever serves images.
        # Capture this before the else-branch reassigns hash_val below.
        serving_original = hash_val is None
        if hash_val is not None:
            submission = Submission.query.filter_by(hash=hash_val).first_or_404()
            image = Image.query.get_or_404(submission.image_hash)
            output_dir = RESULT_FOLDER / str(image.hash) / str(submission.hash)
            output_file = output_dir / Path(img_name).name
        else:
            hash_val = img_name.split(".")[0]
            image = Image.query.filter_by(hash=hash_val).first_or_404()
            output_file = Path(image.file)

        if not output_file.exists():
            return abort(404, description="Image not found or unsupported format")
        if not serving_original and output_file.suffix.lower() not in IMAGE_EXTENSIONS:
            return abort(404, description="Image not found or unsupported format")

        # URLs are content-addressed (md5 hashes), so responses never change:
        # the ~40 derived bit-plane images per result page cache forever.
        response = send_file(output_file, as_attachment=True)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def _register_management_routes(app: Flask) -> None:
    """Register removal and moderation routes."""

    @app.route("/remove/<hash_val>", methods=["POST"])
    @limiter.limit("5 per minute", exempt_when=_is_local_request)
    def remove_image(hash_val: str) -> tuple[Response, int]:
        """Remove an image and associated results if criteria are met."""
        submission = Submission.query.get_or_404(hash_val)
        image = Image.query.get_or_404(submission.image_hash)

        age_seconds = time.time() - submission.date
        if age_seconds < REMOVAL_MIN_AGE_SECONDS:
            return (
                jsonify(
                    {
                        "error": _(
                            "Image must be at least %(min)d seconds old. Current age: %(age)ds",
                            min=REMOVAL_MIN_AGE_SECONDS,
                            age=int(age_seconds),
                        ),
                    },
                ),
                403,
            )

        upload_logs = UploadLog.query.filter_by(image_hash=image.hash).all()
        unique_ips = _extract_unique_ips(upload_logs)
        if len(unique_ips) > 1:
            return (
                jsonify(
                    {
                        "error": _(
                            "Image uploaded from multiple IP addresses. Removal is not allowed.",
                        ),
                        "ip_count": len(unique_ips),
                    },
                ),
                403,
            )

        original_image_path = Path(image.file)
        try:
            _archive_original_image(original_image_path, image.hash, submission.hash)
            _remove_result_folder(str(image.hash), str(submission.hash))
            _delete_submission_entities(submission, image, original_image_path)
        except (OSError, SQLAlchemyError) as exc:
            db.session.rollback()
            sentry_sdk.capture_exception(exc)
            return jsonify({"error": _("Failed to remove image")}), 500

        return jsonify({"message": "Image successfully removed"}), 200

    @app.route("/remove_password/<hash_val>", methods=["POST"])
    @limiter.limit("5 per minute", exempt_when=_is_local_request)
    def remove_password(hash_val: str) -> tuple[Response, int]:
        """Remove a password from a submission if criteria are met."""
        submission = Submission.query.get_or_404(hash_val)

        if not submission.password:
            return jsonify({"error": _("No password to remove")}), 400

        age_seconds = time.time() - submission.date
        if age_seconds < REMOVAL_MIN_AGE_SECONDS:
            return (
                jsonify(
                    {
                        "error": _(
                            "Submission must be at least %(min)d seconds old. "
                            "Current age: %(age)ds",
                            min=REMOVAL_MIN_AGE_SECONDS,
                            age=int(age_seconds),
                        ),
                    },
                ),
                403,
            )

        upload_logs = UploadLog.query.filter_by(submission_hash=submission.hash).all()
        unique_ips = _extract_unique_ips(upload_logs)
        if len(unique_ips) > 1:
            return (
                jsonify(
                    {
                        "error": _(
                            "Submission uploaded from multiple IP addresses. "
                            "Password removal is not allowed.",
                        ),
                        "ip_count": len(unique_ips),
                    },
                ),
                403,
            )

        try:
            submission.password = None
            db.session.commit()
        except SQLAlchemyError as exc:
            db.session.rollback()
            sentry_sdk.capture_exception(exc)
            return jsonify({"error": _("Failed to remove password")}), 500

        return jsonify({"message": "Password successfully removed"}), 200


def create_app() -> Flask:
    """Create flask application with routes."""
    initialize_sentry()
    app = Flask(__name__)
    _configure_app(app)
    configure_omni(app)
    _register_error_handlers(app)
    _register_page_routes(app)
    _register_submission_routes(app)
    _register_data_routes(app)
    _register_management_routes(app)
    # Translatable pages are served at the root (English) and under a
    # language prefix (/fr/, /es/, ...) for indexable per-language URLs.
    app.register_blueprint(pages_bp)
    app.register_blueprint(pages_bp, url_prefix=LANG_PREFIX_RULE, name="pages_i18n")
    app.register_blueprint(wiki_bp)
    app.register_blueprint(wiki_bp, url_prefix=LANG_PREFIX_RULE, name="wiki_i18n")
    app.register_blueprint(cheatsheet_bp)
    app.register_blueprint(cheatsheet_bp, url_prefix=LANG_PREFIX_RULE, name="cheatsheet_i18n")

    @app.after_request
    def set_security_headers(response: Response) -> Response:
        # Baseline hardening; a strict CSP is deferred until the inline
        # scripts in base.html move to nonces (docs/improvement-plan.md).
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        return response

    @app.after_request
    def set_static_cache_headers(response: Response) -> Response:
        """Cache version-stamped static assets for a year instead of a week.

        Templates request CSS/JS as ``?v=<PROJECT_VERSION>``, so those exact
        URLs never change contents -- a new release means a new URL. Requests
        without the parameter (logo.svg, the Three.js bundles reached through
        the import map) keep the 7-day default, because their URL is reused
        across releases and a year-long cache would pin clients to stale bytes.
        """
        if (
            request.endpoint == "static"
            and request.args.get("v")
            and response.status_code == HTTPStatus.OK
        ):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    return app


if __name__ == "__main__":
    my_app = create_app()
    flask_host = os.getenv("FLASK_HOST", "127.0.0.1")
    my_app.run(host=flask_host, port=5000, debug=FLASK_DEBUG)
