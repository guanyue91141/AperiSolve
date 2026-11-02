"""Tests that uploads have no application-level request-size limit."""

import io

from flask.testing import FlaskClient

def test_large_upload_is_not_rejected_by_application_limit(client: FlaskClient) -> None:
    """Uploads larger than the former default cap reach the upload handler."""
    payload = b"x" * (2 * 1024 * 1024)
    response = client.post(
        "/upload",
        data={"image": (io.BytesIO(payload), "big.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code != 413
