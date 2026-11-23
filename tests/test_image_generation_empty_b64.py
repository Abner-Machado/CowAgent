import base64
import importlib.util
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).parents[1]
    / "skills"
    / "image-generation"
    / "scripts"
    / "generate.py"
)
SPEC = importlib.util.spec_from_file_location("image_generation_script", SCRIPT_PATH)
image_generation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(image_generation)

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-image-payload"
IMAGE_URL = "https://images.example.com/a.png"


def _block_load(source):  # pragma: no cover - must not be reached
    raise AssertionError(f"unexpected download of {source}")


def test_empty_b64_json_falls_back_to_url(tmp_path, monkeypatch):
    loaded = []
    monkeypatch.setattr(
        image_generation,
        "_load_image",
        lambda source: loaded.append(source) or PNG_BYTES,
    )

    paths = image_generation.OpenAIProvider._save_results(
        {"data": [{"b64_json": "", "url": IMAGE_URL}]},
        str(tmp_path),
    )

    assert loaded == [IMAGE_URL]
    assert Path(paths[0]).read_bytes() == PNG_BYTES


def test_non_empty_b64_json_is_still_preferred(tmp_path, monkeypatch):
    monkeypatch.setattr(image_generation, "_load_image", _block_load)
    b64 = base64.b64encode(PNG_BYTES).decode()

    paths = image_generation.OpenAIProvider._save_results(
        {"data": [{"b64_json": b64, "url": IMAGE_URL}]},
        str(tmp_path),
    )

    assert len(paths) == 1
    assert Path(paths[0]).read_bytes() == PNG_BYTES


def test_item_without_usable_payload_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(image_generation, "_load_image", _block_load)

    paths = image_generation.OpenAIProvider._save_results(
        {"data": [{"b64_json": "", "url": ""}]},
        str(tmp_path),
    )

    assert paths == []
    assert list(tmp_path.iterdir()) == []


def test_linkai_order_skips_empty_url():
    b64 = base64.b64encode(PNG_BYTES).decode()

    raw = image_generation._decode_image_item({"url": "", "b64_json": b64}, url_first=True)

    assert raw == PNG_BYTES
