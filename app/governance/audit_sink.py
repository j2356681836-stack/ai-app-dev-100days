import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterator

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.governance.audit_event import AuditEvent
from app.governance.governance_runtime import (
    GovernanceRuntimeConfig,
)


_HEX_DIGEST_LENGTH = 64
_PROCESS_LOCKS: dict[str, threading.Lock] = {}
_PROCESS_LOCKS_GUARD = threading.Lock()


class AuditSinkReason(str, Enum):
    APPENDED = "appended"
    VERIFIED = "verified"
    INVALID_SINK_INPUT = "invalid_sink_input"
    AUDIT_LOG_CORRUPTED = "audit_log_corrupted"
    IO_ERROR = "io_error"


class AuditLogRecord(BaseModel):
    """
    Append-only JSONL 中的单条 Hash Chain 记录。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    sequence_number: int = Field(ge=1)
    written_at_utc: datetime
    previous_record_hash: str | None = None

    event: AuditEvent
    record_hash: str

    log_schema_version: str = "audit_log_record_v1"

    @field_validator("written_at_utc")
    @classmethod
    def validate_timestamp(
        cls,
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            raise ValueError(
                "written_at_utc must be timezone-aware."
            )

        return value.astimezone(timezone.utc)

    @field_validator(
        "previous_record_hash",
        "record_hash",
    )
    @classmethod
    def validate_hash(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        if len(value) != _HEX_DIGEST_LENGTH:
            raise ValueError(
                "Audit record hash must be a SHA-256 hex digest."
            )

        try:
            int(value, 16)
        except ValueError as error:
            raise ValueError(
                "Audit record hash must contain hexadecimal "
                "characters only."
            ) from error

        return value


class AuditLogVerificationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    reason_code: AuditSinkReason
    message: str

    record_count: int = Field(default=0, ge=0)
    last_record_hash: str | None = None

    error_type: str | None = None
    retryable: bool = False

    @model_validator(mode="after")
    def validate_result(self):
        if self.retryable:
            raise ValueError(
                "Audit verification failures are non-retryable."
            )

        if self.success:
            if self.reason_code != AuditSinkReason.VERIFIED:
                raise ValueError(
                    "Successful verification must use verified."
                )

            if self.error_type is not None:
                raise ValueError(
                    "Successful verification cannot contain "
                    "error_type."
                )
        else:
            if self.error_type != "audit_persistence_error":
                raise ValueError(
                    "Failed verification must use "
                    "audit_persistence_error."
                )

        return self


class AuditSinkResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    reason_code: AuditSinkReason
    message: str

    sequence_number: int | None = Field(
        default=None,
        ge=1,
    )
    record_hash: str | None = None
    bytes_written: int = Field(default=0, ge=0)
    audit_log_path: str

    error_type: str | None = None
    retryable: bool = False

    @model_validator(mode="after")
    def validate_result(self):
        if self.retryable:
            raise ValueError(
                "Audit persistence failures are non-retryable."
            )

        if self.success:
            if self.reason_code != AuditSinkReason.APPENDED:
                raise ValueError(
                    "Successful append must use appended."
                )

            if (
                self.sequence_number is None
                or self.record_hash is None
                or self.bytes_written <= 0
            ):
                raise ValueError(
                    "Successful append requires sequence, hash "
                    "and positive bytes_written."
                )

            if self.error_type is not None:
                raise ValueError(
                    "Successful append cannot contain error_type."
                )
        else:
            if self.error_type != "audit_persistence_error":
                raise ValueError(
                    "Failed append must use "
                    "audit_persistence_error."
                )

        return self


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _record_payload(
    *,
    sequence_number: int,
    written_at_utc: datetime,
    previous_record_hash: str | None,
    event: AuditEvent,
    log_schema_version: str,
) -> dict[str, Any]:
    return {
        "sequence_number": sequence_number,
        "written_at_utc": (
            written_at_utc
            .astimezone(timezone.utc)
            .isoformat()
        ),
        "previous_record_hash": previous_record_hash,
        "event": event.model_dump(mode="json"),
        "log_schema_version": log_schema_version,
    }


def _calculate_record_hash(
    *,
    sequence_number: int,
    written_at_utc: datetime,
    previous_record_hash: str | None,
    event: AuditEvent,
    log_schema_version: str,
) -> str:
    import hashlib

    payload = _record_payload(
        sequence_number=sequence_number,
        written_at_utc=written_at_utc,
        previous_record_hash=previous_record_hash,
        event=event,
        log_schema_version=log_schema_version,
    )

    return hashlib.sha256(
        _canonical_json(payload).encode("utf-8")
    ).hexdigest()


def _get_process_lock(
    lock_path: Path,
) -> threading.Lock:
    key = str(lock_path.resolve())

    with _PROCESS_LOCKS_GUARD:
        lock = _PROCESS_LOCKS.get(key)

        if lock is None:
            lock = threading.Lock()
            _PROCESS_LOCKS[key] = lock

        return lock


@contextmanager
def _exclusive_os_file_lock(
    lock_path: Path,
) -> Iterator[None]:
    """
    使用独立 .lock 文件进行跨进程互斥。

    Windows 使用 msvcrt，Unix 使用 fcntl。
    """

    lock_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)

        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()

        handle.seek(0)

        if os.name == "nt":
            import msvcrt

            msvcrt.locking(
                handle.fileno(),
                msvcrt.LK_LOCK,
                1,
            )

            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(
                    handle.fileno(),
                    msvcrt.LK_UNLCK,
                    1,
                )
        else:
            import fcntl

            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_EX,
            )

            try:
                yield
            finally:
                fcntl.flock(
                    handle.fileno(),
                    fcntl.LOCK_UN,
                )


@contextmanager
def _exclusive_audit_lock(
    audit_log_path: Path,
) -> Iterator[None]:
    lock_path = audit_log_path.with_suffix(
        audit_log_path.suffix + ".lock"
    )
    process_lock = _get_process_lock(lock_path)

    with process_lock:
        with _exclusive_os_file_lock(lock_path):
            yield


def _verification_success(
    *,
    record_count: int,
    last_record_hash: str | None,
) -> AuditLogVerificationResult:
    return AuditLogVerificationResult(
        success=True,
        reason_code=AuditSinkReason.VERIFIED,
        message="Audit log hash chain verified.",
        record_count=record_count,
        last_record_hash=last_record_hash,
        error_type=None,
        retryable=False,
    )


def _verification_failure(
    message: str,
) -> AuditLogVerificationResult:
    return AuditLogVerificationResult(
        success=False,
        reason_code=AuditSinkReason.AUDIT_LOG_CORRUPTED,
        message=message,
        record_count=0,
        last_record_hash=None,
        error_type="audit_persistence_error",
        retryable=False,
    )


def verify_audit_log(
    audit_log_path: str | Path,
) -> AuditLogVerificationResult:
    """
    验证完整 JSONL Hash Chain。

    该验证能够检测内容修改、删除中间记录、调换顺序、
    previous hash 变化和不完整尾行。
    """

    path = Path(audit_log_path)

    if not path.exists():
        return _verification_success(
            record_count=0,
            last_record_hash=None,
        )

    try:
        raw_bytes = path.read_bytes()
    except OSError:
        return AuditLogVerificationResult(
            success=False,
            reason_code=AuditSinkReason.IO_ERROR,
            message="Audit log could not be read.",
            record_count=0,
            last_record_hash=None,
            error_type="audit_persistence_error",
            retryable=False,
        )

    if not raw_bytes:
        return _verification_success(
            record_count=0,
            last_record_hash=None,
        )

    if not raw_bytes.endswith(b"\n"):
        return _verification_failure(
            "Audit log contains an incomplete final record."
        )

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return _verification_failure(
            "Audit log is not valid UTF-8."
        )

    lines = text.splitlines()
    previous_hash = None

    for expected_sequence, line in enumerate(
        lines,
        start=1,
    ):
        if not line.strip():
            return _verification_failure(
                "Audit log contains a blank record."
            )

        try:
            payload = json.loads(line)
            record = AuditLogRecord.model_validate(
                payload
            )
        except Exception:
            return _verification_failure(
                "Audit log contains an invalid record."
            )

        if record.sequence_number != expected_sequence:
            return _verification_failure(
                "Audit log sequence is not continuous."
            )

        if record.previous_record_hash != previous_hash:
            return _verification_failure(
                "Audit log previous hash does not match."
            )

        expected_hash = _calculate_record_hash(
            sequence_number=record.sequence_number,
            written_at_utc=record.written_at_utc,
            previous_record_hash=(
                record.previous_record_hash
            ),
            event=record.event,
            log_schema_version=(
                record.log_schema_version
            ),
        )

        if record.record_hash != expected_hash:
            return _verification_failure(
                "Audit log record hash does not match."
            )

        previous_hash = record.record_hash

    return _verification_success(
        record_count=len(lines),
        last_record_hash=previous_hash,
    )


def _append_failure(
    *,
    config: GovernanceRuntimeConfig,
    reason_code: AuditSinkReason,
    message: str,
) -> AuditSinkResult:
    return AuditSinkResult(
        success=False,
        reason_code=reason_code,
        message=message,
        sequence_number=None,
        record_hash=None,
        bytes_written=0,
        audit_log_path=str(config.audit_log_path),
        error_type="audit_persistence_error",
        retryable=False,
    )


def append_audit_event(
    *,
    event: AuditEvent,
    config: GovernanceRuntimeConfig,
    written_at_utc: datetime | None = None,
) -> AuditSinkResult:
    """
    将 AuditEvent 追加为单行 JSONL Hash Chain 记录。

    写入成功的定义：
    - 已持有进程内和操作系统文件锁；
    - 现有完整 Hash Chain 验证通过；
    - 新记录已经 append；
    - flush 完成；
    - 配置要求时 fsync 完成。
    """

    if not isinstance(event, AuditEvent):
        return _append_failure(
            config=config,
            reason_code=(
                AuditSinkReason.INVALID_SINK_INPUT
            ),
            message="Audit sink only accepts AuditEvent.",
        )

    timestamp = (
        written_at_utc
        if written_at_utc is not None
        else datetime.now(timezone.utc)
    )

    if timestamp.tzinfo is None:
        return _append_failure(
            config=config,
            reason_code=(
                AuditSinkReason.INVALID_SINK_INPUT
            ),
            message=(
                "written_at_utc must be timezone-aware."
            ),
        )

    timestamp = timestamp.astimezone(timezone.utc)
    path = config.audit_log_path

    try:
        if config.create_parent_directory:
            path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
        elif not path.parent.exists():
            return _append_failure(
                config=config,
                reason_code=AuditSinkReason.IO_ERROR,
                message=(
                    "Audit log parent directory does not exist."
                ),
            )

        with _exclusive_audit_lock(path):
            verification = verify_audit_log(path)

            if not verification.success:
                return _append_failure(
                    config=config,
                    reason_code=verification.reason_code,
                    message=(
                        "Existing audit log failed integrity "
                        "verification."
                    ),
                )

            sequence_number = (
                verification.record_count + 1
            )
            previous_record_hash = (
                verification.last_record_hash
            )
            log_schema_version = (
                "audit_log_record_v1"
            )

            record_hash = _calculate_record_hash(
                sequence_number=sequence_number,
                written_at_utc=timestamp,
                previous_record_hash=(
                    previous_record_hash
                ),
                event=event,
                log_schema_version=(
                    log_schema_version
                ),
            )

            record = AuditLogRecord(
                sequence_number=sequence_number,
                written_at_utc=timestamp,
                previous_record_hash=(
                    previous_record_hash
                ),
                event=event,
                record_hash=record_hash,
                log_schema_version=(
                    log_schema_version
                ),
            )

            serialized = _canonical_json(
                record.model_dump(mode="json")
            )
            encoded = (serialized + "\n").encode(
                "utf-8"
            )

            with path.open("ab") as handle:
                handle.write(encoded)
                handle.flush()

                if config.fsync_enabled:
                    os.fsync(handle.fileno())

            return AuditSinkResult(
                success=True,
                reason_code=AuditSinkReason.APPENDED,
                message="Audit event appended.",
                sequence_number=sequence_number,
                record_hash=record_hash,
                bytes_written=len(encoded),
                audit_log_path=str(path),
                error_type=None,
                retryable=False,
            )

    except OSError:
        return _append_failure(
            config=config,
            reason_code=AuditSinkReason.IO_ERROR,
            message="Audit event could not be persisted.",
        )
