import logging

from aiohttp import web
from telethon.tl.custom import Message

from app.util import get_file_name
from app.config import block_downloads
from .base import BaseView

log = logging.getLogger(__name__)

class Download(BaseView):
    async def download_get(self, req: web.Request) -> web.Response:
        return await self.handle_request(req)

    async def download_head(self, req: web.Request) -> web.Response:
        return await self.handle_request(req, head=True)

    async def handle_request(
        self, req: web.Request, head: bool = False
    ) -> web.Response:
        async def stream_response(media, offset, limit):
            with await media.download_media(offset=offset, limit=limit) as stream:
                async for chunk in stream:
                    yield chunk

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
        except Exception as e:
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
            range_header = req.headers.get('Range', 0)
            if range_header:
                range_data = range_header.replace('bytes=', '').split('-')
                from_bytes = int(range_data[0])
                until_bytes = (
                    int(range_data[1]) if range_data[1] else size - 1
                )
            else:
                from_bytes = req.http_range.start or 0
                until_bytes = req.http_range.stop or size - 1

            offset = from_bytes or 0
            limit = until_bytes or size

            if (limit > size) or (offset < 0) or (limit < offset):
                raise ValueError("range not in acceptable format")
        except ValueError:
            return web.Response(
                status=416,
                text="416: Range Not Satisfiable",
                headers={"Content-Range": f"bytes */{size}"}
            )

        if not head:
            return_resp = web.StreamResponse(
                status=206 if req.http_range.start else 200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Content-Type": mime_type,
                    "Content-Range": f"bytes {offset}-{limit}/{size}",
                    "Content-Disposition": f'attachment; filename="{file_name}"',
                    "Accept-Ranges": "bytes",
                }
            )
            return_resp.enable_chunked_encoding()
            try:
                await return_resp.prepare(req)
                async for chunk in stream_response(media, offset, limit):
                    await return_resp.write(chunk)
            except Exception as e:
                log.error(f"Error during streaming: {e}")
                return_resp.set_status(500)
            finally:
                await return_resp.write_eof()
       
