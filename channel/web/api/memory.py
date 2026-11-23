"""The memory view's endpoints: /api/memory.

Lists the Agent's memory files and serves one for the viewer. Editing them
goes through the workspace write route, which knows where system assets live.
"""

import json

import web

from channel.web.core._common import (
    _get_workspace_root,
    _request_agent_id,
    _require_auth,
)
from common.log import logger


class MemoryHandler:
    def GET(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            from agent.memory.service import MemoryService
            params = web.input(
                page='1', page_size='20', category='memory', agent_id=''
            )
            workspace_root = _get_workspace_root(agent_id=_request_agent_id(params))
            service = MemoryService(workspace_root)
            result = service.list_files(
                page=int(params.page), page_size=int(params.page_size),
                category=params.category,
            )
            return json.dumps({"status": "success", **result}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[WebChannel] Memory API error: {e}")
            return json.dumps({"status": "error", "message": str(e)})


class MemoryContentHandler:
    def GET(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            from agent.memory.service import MemoryService
            params = web.input(filename='', category='memory', agent_id='')
            if not params.filename:
                return json.dumps({"status": "error", "message": "filename required"})
            workspace_root = _get_workspace_root(agent_id=_request_agent_id(params))
            service = MemoryService(workspace_root)
            result = service.get_content(params.filename, category=params.category)
            return json.dumps({"status": "success", **result}, ensure_ascii=False)
        except ValueError:
            return json.dumps({"status": "error", "message": "invalid filename"})
        except FileNotFoundError:
            return json.dumps({"status": "error", "message": "file not found"})
        except Exception as e:
            logger.error(f"[WebChannel] Memory content API error: {e}")
            return json.dumps({"status": "error", "message": str(e)})
