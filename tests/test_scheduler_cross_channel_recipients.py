import json

from agent.tools.scheduler.recipient_store import RecipientStore
from agent.tools.scheduler.scheduler_tool import SchedulerTool
from bridge.context import Context, ContextType


class _TaskStore:
    def __init__(self):
        self.tasks = []

    def add_task(self, task):
        self.tasks.append(task)


def _context(channel_type, receiver):
    context = Context(ContextType.TEXT, "hello")
    context["channel_type"] = channel_type
    context["receiver"] = receiver
    context["session_id"] = receiver
    context["isgroup"] = False
    return context


def _create(tool, **overrides):
    values = {
        "name": "Reminder",
        "message": "Stand up",
        "schedule_type": "once",
        "schedule_value": "+5m",
    }
    values.update(overrides)
    return tool._create_task(**values)


def test_recipient_store_persists_only_delivery_identity(tmp_path):
    path = tmp_path / "recipients.json"
    store = RecipientStore(str(path))
    store.remember(
        "wecom_bot",
        "user-42",
        name="Ada",
        session_id="session-42",
    )

    reloaded = RecipientStore(str(path)).get("wecom_bot", "user-42")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert reloaded["name"] == "Ada"
    assert reloaded["session_id"] == "session-42"
    assert "token" not in json.dumps(payload).lower()


def test_recipient_store_avoids_rewriting_an_unchanged_recent_entry(tmp_path):
    path = tmp_path / "recipients.json"
    store = RecipientStore(str(path))
    store.remember("wecom_bot", "user-42", name="Ada")
    original_mtime = path.stat().st_mtime_ns

    store.remember("wecom_bot", "user-42", name="Ada")

    assert path.stat().st_mtime_ns == original_mtime


def test_recipient_key_uses_colon_separator(tmp_path):
    path = tmp_path / "recipients.json"
    RecipientStore(str(path)).remember("weixin", "abc@im.wechat", name="Ada")

    payload = json.loads(path.read_text(encoding="utf-8"))
    keys = list(payload["recipients"].keys())

    assert keys == ["weixin:abc@im.wechat"]
    assert "\u0000" not in path.read_text(encoding="utf-8")


def test_receiver_id_with_colon_still_round_trips(tmp_path):
    # Feishu group ids contain a colon; the key is only the joined form, the
    # structured fields are what downstream code reads, so lookup must still work.
    path = tmp_path / "recipients.json"
    store = RecipientStore(str(path))
    store.remember("feishu", "user-1:group-9", name="Room", is_group=True)

    got = store.get("feishu", "user-1:group-9")
    assert got is not None
    assert got["receiver"] == "user-1:group-9"
    assert got["is_group"] is True


def test_same_person_on_one_instance_is_a_single_entry(tmp_path):
    # Repeated sightings on the same instance collapse onto one entry; the owning
    # Agent is derived from the instance at delivery time and is not stored here.
    path = tmp_path / "recipients.json"
    store = RecipientStore(str(path))
    store.remember("weixin", "user-1", name="Ada", instance_id="weixin-aaa")
    store.remember("weixin", "user-1", name="Ada", instance_id="weixin-aaa")

    entries = store.list()
    assert len(entries) == 1
    assert "agent_ids" not in entries[0]


def test_same_receiver_on_two_instances_are_distinct_entries(tmp_path):
    # The same receiver id seen on two WeChat instances is two different people
    # (separate logins / id spaces), so they must not collapse into one entry.
    path = tmp_path / "recipients.json"
    store = RecipientStore(str(path))
    store.remember("weixin", "user-1", name="Ada", instance_id="weixin-aaa")
    store.remember("weixin", "user-1", name="Bob", instance_id="weixin-bbb")

    entries = store.list()
    assert len(entries) == 2
    assert store.get("weixin-aaa", "user-1")["name"] == "Ada"
    assert store.get("weixin-bbb", "user-1")["name"] == "Bob"


def test_missing_instance_id_falls_back_to_channel_type(tmp_path):
    # Legacy single-instance: an entry saved without an instance_id is keyed and
    # retrieved under the channel type, which is its running instance id.
    path = tmp_path / "recipients.json"
    store = RecipientStore(str(path))
    store.remember("wecom_bot", "user-42", name="Ada")

    entry = store.get("wecom_bot", "user-42")
    assert entry is not None
    assert entry["instance_id"] == "wecom_bot"


def test_created_task_carries_instance_id(tmp_path):
    recipients = RecipientStore(str(tmp_path / "recipients.json"))
    recipients.remember("weixin", "user-1", name="Ada", instance_id="weixin-aaa")
    tasks = _TaskStore()
    tool = SchedulerTool({"channel_type": "web"})
    tool.current_context = _context("web", "web-session")
    tool.recipient_store = recipients
    tool.task_store = tasks

    result = _create(
        tool,
        channel_type="weixin",
        receiver="user-1",
        instance_id="weixin-aaa",
    )

    assert "Error:" not in result
    assert tasks.tasks[0]["action"]["instance_id"] == "weixin-aaa"


def test_legacy_entry_without_instance_id_is_normalized_on_read(tmp_path):
    # An entry saved before multi-instance has no instance_id; on read it defaults
    # to the channel type, which is the id a single-instance channel runs under.
    path = tmp_path / "recipients.json"
    path.write_text(
        json.dumps({
            "version": 1,
            "recipients": {
                "weixin:user-1": {
                    "channel_type": "weixin",
                    "receiver": "user-1",
                    "name": "Ada",
                    "is_group": False,
                    "session_id": "user-1",
                    "last_seen_at": "2026-09-07T03:01:28.940740+00:00",
                }
            },
        }),
        encoding="utf-8",
    )
    store = RecipientStore(str(path))

    assert store.get("weixin", "user-1")["instance_id"] == "weixin"
    assert store.list()[0]["instance_id"] == "weixin"


def test_web_can_create_message_for_trusted_cross_channel_recipient(tmp_path):
    recipients = RecipientStore(str(tmp_path / "recipients.json"))
    recipients.remember("wecom_bot", "user-42", name="Ada")
    tasks = _TaskStore()
    tool = SchedulerTool({"channel_type": "web"})
    tool.current_context = _context("web", "web-session")
    tool.recipient_store = recipients
    tool.task_store = tasks

    result = _create(tool, channel_type="wecom_bot", receiver="user-42")

    assert "Error:" not in result
    assert tasks.tasks[0]["action"]["channel_type"] == "wecom_bot"
    assert tasks.tasks[0]["action"]["receiver"] == "user-42"
    assert tasks.tasks[0]["action"]["receiver_name"] == "Ada"


def test_cross_channel_target_must_be_trusted_and_selected_from_web(tmp_path):
    recipients = RecipientStore(str(tmp_path / "recipients.json"))
    tasks = _TaskStore()
    tool = SchedulerTool({"channel_type": "web"})
    tool.recipient_store = recipients
    tool.task_store = tasks

    tool.current_context = _context("web", "web-session")
    assert "not in the trusted recipient directory" in _create(
        tool, channel_type="wecom_bot", receiver="unknown"
    )

    recipients.remember("wecom_bot", "user-42")
    tool.current_context = _context("feishu", "feishu-user")
    assert "only be selected from the Web console" in _create(
        tool, channel_type="wecom_bot", receiver="user-42"
    )
    assert tasks.tasks == []


def test_cross_channel_supports_ai_tasks(tmp_path):
    recipients = RecipientStore(str(tmp_path / "recipients.json"))
    recipients.remember("wecom_bot", "user-42", name="Ada")
    tasks = _TaskStore()
    tool = SchedulerTool({"channel_type": "web"})
    tool.current_context = _context("web", "web-session")
    tool.recipient_store = recipients
    tool.task_store = tasks

    result = _create(
        tool,
        message=None,
        ai_task="Prepare a report",
        channel_type="wecom_bot",
        receiver="user-42",
    )

    assert "Error:" not in result
    action = tasks.tasks[0]["action"]
    assert action["type"] == "agent_task"
    assert action["channel_type"] == "wecom_bot"
    assert action["receiver"] == "user-42"
