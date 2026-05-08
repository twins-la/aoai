"""AOAI-twin log emission helper.

Wraps :func:`twins_local.logs.build_log_record` with the canonical
``twin`` identifier. Every operation in the twin emits via :func:`emit`;
ad-hoc dicts are non-conformant per LOGGING.md §7.1.
"""

from typing import Optional

from twins_local.logs import build_log_record, current_correlation_id

TWIN_NAME = "aoai"


def emit(
    storage,
    *,
    tenant_id: str,
    plane: str,
    operation: str,
    resource: Optional[dict] = None,
    outcome: str = "success",
    reason: Optional[str] = None,
    details: Optional[dict] = None,
) -> dict:
    """Build a normative log record and append it to ``storage``.

    Returns the record so tests can assert on it directly.
    """
    record = build_log_record(
        twin=TWIN_NAME,
        tenant_id=tenant_id,
        correlation_id=current_correlation_id(),
        plane=plane,
        operation=operation,
        resource=resource,
        outcome=outcome,
        reason=reason,
        details=details,
    )
    storage.append_log(record)
    return record
