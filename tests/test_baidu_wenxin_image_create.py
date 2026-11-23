"""Regression tests for the image-create prefix on the Baidu Wenxin bot.

`BaiduWenxinBot` only inherits the bare `Bot` base class, which defines no
`create_img()`. The IMAGE_CREATE branch called `self.create_img(query, 0)`
anyway, so an image-create prefix ("画图 ...") raised AttributeError inside the
channel worker, which logs and swallows it -- the user got no reply at all.
"""

from bridge.context import Context, ContextType
from bridge.reply import Reply, ReplyType
from models.baidu.baidu_wenxin import BaiduWenxinBot


def _bot():
    # The IMAGE_CREATE branch touches nothing that __init__ builds, and __init__
    # needs the session manager plus the Baidu config keys.
    return BaiduWenxinBot.__new__(BaiduWenxinBot)


def test_image_create_replies_with_error_instead_of_raising():
    reply = _bot().reply("a cat", Context(ContextType.IMAGE_CREATE, "a cat"))

    assert isinstance(reply, Reply)
    assert reply.type == ReplyType.ERROR


def test_image_create_error_matches_the_other_bots_wording():
    # Same text every other bot without image generation returns, so the
    # message a user sees does not depend on which model is configured.
    reply = _bot().reply("a cat", Context(ContextType.IMAGE_CREATE, "a cat"))

    assert reply.content == "Bot不支持处理{}类型的消息".format(ContextType.IMAGE_CREATE)
