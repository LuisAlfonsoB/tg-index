import logging
from aiohttp import web
from telethon.tl.custom import Message
from app.util import get_file_name
from app.config import block_downloads
from .base import BaseView

log = logging.getLogger(__name__)

class Download(BaseView):
    async def download_get(self, req: web.Request) -> web.StreamResponse:
        return await self.handle_request(req)

    async def download_head(self, req: web.Request) -> web.Response:
        return await self.handle_request(req, head=True)

    async def handle_request(
        self, req: web.Request, head: bool = False
    ) -> web.StreamResponse:
        if block_downloads:
            return web.Response(status=403, text="403: Forbidden" if not head else None)

        file_id = int(req.match_info["id"])
        alias_id = req.match_info["chat"]
        chat = self.chat_ids[alias_id]
        chat_id = chat["chat_id"]

        try:
            message: Message = await self.client.get_messages(
                entity=chat_id, ids=file_id
            )
        except Exception:
            log.debug(f"Error in getting message {file_id} in {chat_id}", exc_info=True)
            message = None

        if not message or not message.file:
            log.debug(f"No result for {file_id} in {chat_id}")
            return web.Response(
                status=410,
                text="410: Gone. Access to the target resource is no longer available!"
                if not head
                else None,
            )

        media = message.media
        size = message.file.size
        file_name = get_file_name(message, quote_name=False)
        mime_type = message.file.mime_type

        try:
            request = req
            range_header = request.headers.get('Range', 0)
            if range_header:
                range_data = range_header.replace('bytes=', '').split('-')
                from_bytes = int(range_data[0])
                until_bytes = int(range_data[1]) if range_data[1] else size - 1
            else:
                from_bytes = request.http_range.start or 0
                until_bytes = request.http_range.stop or size - 1

            req_length = until_bytes - from_bytes

            if (until_bytes > size) or (from_bytes < 0) or (until_bytes < from_bytes):
                raise ValueError("Range not in acceptable format")
        except ValueError:
            return web.Response(
                status=416,
                text="416: Range Not Satisfiable",
                headers={
                    "Content-Range": f"bytes */{size}"
                }
            )

        if not head:
            # Use download method for streaming
            body = self.client.download(media, size, from_bytes, until_bytes)
            log.info(f"Serving file in {message.id} (chat {chat_id}) ; Range: {from_bytes} - {until_bytes}")
        else:
            body = None

        response = web.StreamResponse(
            status=206 if req.http_range.start else 200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Content-Type": mime_type,
                "Content-Range": f"bytes {from_bytes}-{until_bytes}/{size}",
                "Content-Disposition": f'attachment; filename="{file_name}"',
                "Accept-Ranges": "bytes",
            }
        )
        await response.prepare(req)

        if not head:
            await response.write(body)

        return response
