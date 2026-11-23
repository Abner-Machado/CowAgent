"""The version row's endpoints: /VERSION and /api/update/*.

The running version, whether a newer one exists, and the one-click update
itself -- started in the background, then polled for progress.
"""

import json

import web

from channel.web.core._common import _require_auth
from common.log import logger


class VersionHandler:
    def GET(self):
        web.header('Content-Type', 'application/json; charset=utf-8')
        from cli.update_service import version_payload
        # Local metadata only — never contacts GitHub.
        return json.dumps(version_payload(), ensure_ascii=False)


class UpdateCheckHandler:
    def POST(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            from cli.update_service import check_for_updates, version_payload
            payload = version_payload()
            logger.info("[WebChannel] update check requested (current v%s)", payload["version"])
            result = check_for_updates(payload["version"])
            result.update({
                "install_kind": payload["install_kind"],
                "update_supported": payload["update_supported"],
                "unsupported_reason": payload["unsupported_reason"],
            })
            if result.get("up_to_date"):
                logger.info("[WebChannel] update check: already up to date (v%s)", payload["version"])
            else:
                latest = (result.get("latest") or {}).get("tag") or "?"
                logger.info("[WebChannel] update check: newer version available -> %s", latest)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            logger.error("[WebChannel] update check failed: %s", e, exc_info=True)
            return json.dumps({"status": "error", "message": str(e)})


class UpdateStartHandler:
    def POST(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            from cli.update_service import UpdateError, schedule_web_update
            logger.info("[WebChannel] one-click update requested")
            status = schedule_web_update()
            return json.dumps({"status": "success", "update": status}, ensure_ascii=False)
        except UpdateError as e:
            logger.error("[WebChannel] update could not start at step '%s': %s", e.step, e.message)
            return json.dumps({
                "status": "error",
                "step": e.step,
                "message": e.message,
                "output": e.output,
            })
        except Exception as e:
            logger.error("[WebChannel] update start failed: %s", e, exc_info=True)
            return json.dumps({"status": "error", "message": str(e)})


class UpdateStatusHandler:
    def GET(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        from cli.update_service import read_update_status
        return json.dumps(read_update_status(), ensure_ascii=False)
