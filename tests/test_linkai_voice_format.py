"""Regression tests for the audio-format guard in the LinkAI ASR provider.

WeChat voice notes are stored as ``.silk`` (channel/weixin/weixin_message.py:154)
and handed to the ASR provider unconverted. The dashscope and zhipuai providers
normalise that container before upload, but LinkAI only matched ``.amr`` and
compared the extension case-sensitively.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from voice.linkai import linkai_voice


class _FakeResponse:
    status_code = 200

    def json(self):
        return {"text": "transcribed"}


class LinkAIVoiceFormatTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.uploaded = []   # names of the files handed to the API
        self.converted = []  # (src, dst) pairs passed to any_to_mp3
        self.voice = linkai_voice.LinkAIVoice()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _source(self, name, payload=b"audio-bytes"):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "wb") as f:
            f.write(payload)
        return path

    def _fake_post(self, url, files=None, headers=None, data=None, timeout=None):
        self.uploaded.append(os.path.basename(files["file"].name))
        return _FakeResponse()

    def _fake_any_to_mp3(self, src, dst):
        self.converted.append((src, dst))
        with open(dst, "wb") as f:
            f.write(b"mp3")

    def _run(self, voice_file, converter=None):
        converter = converter or self._fake_any_to_mp3
        with patch.object(linkai_voice, "conf", lambda: {
                "linkai_api_base": "https://api.example.com",
                "linkai_api_key": "test-key"}), \
                patch.object(linkai_voice, "apply_client_source", lambda h: h), \
                patch.object(linkai_voice, "apply_cloud_user", lambda h: h), \
                patch.object(linkai_voice.audio_convert, "any_to_mp3",
                             side_effect=converter), \
                patch.object(linkai_voice.requests, "post",
                             side_effect=self._fake_post):
            return self.voice.voiceToText(voice_file)

    def test_silk_voice_is_converted_before_upload(self):
        """SILK is the container CowAgent itself writes for WeChat voice notes."""
        reply = self._run(self._source("wx_7.silk"))
        self.assertEqual(1, len(self.converted))
        self.assertEqual(["wx_7.mp3"], self.uploaded)
        self.assertEqual("transcribed", reply.content)

    def test_extension_match_is_case_insensitive(self):
        """A uppercase '.AMR' capture must convert just like '.amr' does."""
        self._run(self._source("voice.AMR"))
        self.assertEqual(["voice.mp3"], self.uploaded)

    def test_mp3_voice_is_uploaded_unchanged(self):
        """An accepted format must not pay for a pointless re-encode."""
        self._run(self._source("ready.mp3"))
        self.assertEqual([], self.converted)
        self.assertEqual(["ready.mp3"], self.uploaded)

    def test_conversion_failure_still_sends_the_original(self):
        """A converter error degrades to the existing behaviour, it must not abort."""
        def boom(src, dst):
            raise ImportError("pydub is required for audio conversion.")

        reply = self._run(self._source("wx_8.silk"), converter=boom)
        self.assertEqual(["wx_8.silk"], self.uploaded)
        self.assertEqual("transcribed", reply.content)
