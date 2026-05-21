from __future__ import annotations

from ...context import Context
from ...errors import IntegrationError
from ...integrations.composio_drive import parse_folder_id
from .contract import ResolveDriveFolderInput, ResolveDriveFolderOutput


async def run(
    payload: ResolveDriveFolderInput, ctx: Context
) -> ResolveDriveFolderOutput:
    log = ctx.logger.bind(behavior="resolve_drive_folder")
    folder_id = parse_folder_id(payload.drive_folder_url)
    try:
        folder = await ctx.drive.get_folder(folder_id)
    except Exception as exc:  # surface as IntegrationError for the HTTP layer
        log.warning("drive_lookup_failed", folder_id=folder_id, error=str(exc))
        raise IntegrationError(f"drive_lookup_failed: {exc}") from exc
    log.info("drive_folder_resolved", folder_id=folder_id, name=folder.name)
    return ResolveDriveFolderOutput(id=folder.id, name=folder.name, path=folder.path)
