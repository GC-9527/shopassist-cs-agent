from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from customer_service_app.api.dependencies import require_roles
from customer_service_app.core.config import Settings, get_settings
from customer_service_app.core.exceptions import AppError, NotFoundError, PermissionDeniedError
from customer_service_app.core.security import CurrentPrincipal, authorize_identity
from customer_service_app.infrastructure.db.models import Attachment
from customer_service_app.infrastructure.db.session import get_db_session


router = APIRouter(prefix="/uploads", tags=["uploads"])

_SUFFIX_BY_TYPE = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


class AttachmentView(BaseModel):
    id: str
    filename: str
    content_type: str
    size: int
    url: str


@router.post("", response_model=AttachmentView)
async def upload_attachment(
    tenant_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    principal: CurrentPrincipal = Depends(
        require_roles("customer", "agent", "operator", "admin")
    ),
) -> AttachmentView:
    """上传售后凭证图片。

    只接受图片类型并限制大小；归属取自令牌主体，前端不能指定别人的账号。
    图片存本地目录，读取时按归属校验。
    """

    tenant_id, _ = authorize_identity(principal, tenant_id=tenant_id)
    user_id = principal.subject
    if not user_id:
        raise PermissionDeniedError("需要登录后才能上传文件")

    allowed = {
        item.strip().lower()
        for item in settings.upload_allowed_types.split(",")
        if item.strip()
    }
    content_type = (file.content_type or "").lower()
    if content_type not in allowed:
        raise AppError(
            "只支持 JPG / PNG / WebP 图片",
            code="upload_type_not_allowed",
            status_code=400,
        )

    data = await file.read()
    if not data:
        raise AppError("文件为空", code="upload_empty", status_code=400)
    if len(data) > settings.upload_max_bytes:
        raise AppError(
            f"文件超过 {settings.upload_max_bytes // (1024 * 1024)}MB 限制",
            code="upload_too_large",
            status_code=413,
        )

    attachment_id = uuid.uuid4().hex
    suffix = _SUFFIX_BY_TYPE.get(content_type, ".bin")
    directory = Path(settings.upload_dir) / tenant_id / user_id
    directory.mkdir(parents=True, exist_ok=True)
    storage_path = directory / f"{attachment_id}{suffix}"
    storage_path.write_bytes(data)

    row = Attachment(
        id=attachment_id,
        tenant_id=tenant_id,
        user_id=user_id,
        filename=file.filename or f"upload{suffix}",
        content_type=content_type,
        size=len(data),
        storage_path=str(storage_path),
    )
    session.add(row)
    await session.commit()

    return AttachmentView(
        id=row.id,
        filename=row.filename,
        content_type=row.content_type,
        size=row.size,
        url=f"{settings.api_prefix}/uploads/{row.id}",
    )


@router.get("/{attachment_id}")
async def download_attachment(
    attachment_id: str,
    session: AsyncSession = Depends(get_db_session),
    principal: CurrentPrincipal = Depends(
        require_roles("customer", "agent", "operator", "admin")
    ),
) -> FileResponse:
    """按归属读取图片：本人、坐席或平台管理员。"""

    result = await session.execute(select(Attachment).where(Attachment.id == attachment_id))
    row = result.scalars().one_or_none()
    if row is None:
        raise NotFoundError("Attachment not found")

    allowed = (
        principal.is_platform_admin
        or principal.subject == row.user_id
        or principal.has_any_role("agent", "operator")
    )
    if not allowed:
        raise PermissionDeniedError("无权访问该附件")

    path = Path(row.storage_path)
    if not path.exists():
        raise NotFoundError("Attachment file missing")
    return FileResponse(path, media_type=row.content_type, filename=row.filename)
