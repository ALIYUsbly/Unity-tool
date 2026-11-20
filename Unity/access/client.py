import json
import re
import urllib.error
import urllib.request
import uuid

BASE_URL = "https://aliyusbly.eu.pythonanywhere.com"
RESERVE_URL = BASE_URL + "/api/credits/reserve"
SETTLE_URL = BASE_URL + "/api/credits/settle"


def tab_feature_id(tab):
    return getattr(tab, "access_id", tab.__class__.__name__.lower())


def operation_feature_id(tab, section, action):
    label = re.sub(r"[^a-z0-9]+", "-", action.label.lower()).strip("-")
    return f"{tab_feature_id(tab)}:{section.script}:{label}"


def _post(url, payload, timeout=15):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
        except Exception:
            detail = {}
        raise RuntimeError(detail.get("error") or detail.get("reason") or
                           f"Server returned HTTP {exc.code}") from exc
    except Exception as exc:
        raise RuntimeError(f"Could not contact the licence server: {exc}") from exc


class AccessClient:
    def __init__(self, key, hwid, grant=None):
        self.key = key
        self.hwid = hwid
        self.offline = False
        self.tier = "standard"
        self.balance = 0
        self.tabs = {}
        self.operations = {}
        if grant:
            self.load_from_grant(grant)

    def load_from_grant(self, grant):
        """Populate tabs/operations/credits from a signed licence grant
        (licensing.client.current_grant()) instead of a separate network
        call — the same grant that let the app start at all already
        carries the full feature policy, online or cached offline."""
        self.tier = grant.get("tier", "standard")
        self.balance = int(grant.get("credits", 0))
        self.tabs = grant.get("tabs", {})
        self.operations = grant.get("operations", {})
        self.offline = grant.get("source") == "offline_grace"
        return grant

    def tab_allowed(self, tab):
        return bool(self.tabs.get(tab_feature_id(tab), {}).get("enabled", False))

    def operation_rule(self, tab, section, action):
        fid = operation_feature_id(tab, section, action)
        rule = self.operations.get(fid, {"enabled": False, "cost": 0})
        return fid, bool(rule.get("enabled", False)), max(0, int(rule.get("cost", 0)))

    def reserve(self, tab, section, action):
        fid, enabled, _cost = self.operation_rule(tab, section, action)
        if not self.tab_allowed(tab):
            raise RuntimeError("This tab is not included in your licence.")
        if not enabled:
            raise RuntimeError("This operation is not enabled for your licence.")
        if self.offline:
            # Already running on a verified offline grant: the operation is
            # allowed per that grant, but live credit metering needs the
            # server, so nothing is reserved/charged until back online.
            return {"reservation_id": None, "credits": self.balance, "offline": True}
        try:
            result = _post(RESERVE_URL, {
                "key": self.key,
                "hwid": self.hwid,
                "tab_id": tab_feature_id(tab),
                "operation_id": fid,
                "request_id": str(uuid.uuid4()),
            })
        except RuntimeError:
            # Started online, lost the connection mid-session: fall back to
            # the grant's allowance rather than blocking a repair in
            # progress because the network dropped.
            self.offline = True
            return {"reservation_id": None, "credits": self.balance, "offline": True}
        self.balance = int(result.get("credits", self.balance))
        return result

    def settle(self, reservation_id, success):
        if not reservation_id:
            return {"credits": self.balance, "offline": True}
        try:
            result = _post(SETTLE_URL, {
                "key": self.key,
                "hwid": self.hwid,
                "reservation_id": reservation_id,
                "success": bool(success),
            })
        except RuntimeError:
            return {"credits": self.balance, "offline": True}
        self.balance = int(result.get("credits", self.balance))
        return result
