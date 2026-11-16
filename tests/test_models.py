import hashlib
import http.server
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from gvoice import models, schema
from gvoice.errors import GvoiceError

ROOT = Path(__file__).resolve().parent.parent
GOOD = b"good model bytes " * 1000
OTHER = b"other model byte " * 1000  # same size as GOOD, other content


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Handler(http.server.BaseHTTPRequestHandler):
    routes = {}  # path -> (body, declared length or None for len(body))

    def do_GET(self):
        route = self.routes.get(self.path)
        if route is None:
            self.send_error(404)
            return
        body, declared = route
        self.send_response(200)
        self.send_header("Content-Length", str(len(body) if declared is None else declared))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
        self.close_connection = True

    def log_message(self, *args):
        pass


class ModelsBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        env = mock.patch.dict(os.environ, {"GVOICE_DATA_HOME": str(self.tmp / "data")})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("GVOICE_MODELS_HOME", None)
        self.models = self.tmp / "data" / "models"
        Handler.routes = {}
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.addCleanup(self.server.server_close)
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.base = "http://127.0.0.1:%d/" % self.server.server_address[1]

    def catalog(self, data=GOOD, sha256=None, **extra):
        model = {"id": "tiny", "file": "tiny.gguf", "url": self.base + "tiny.gguf", "bytes": len(data),
                 "sha256": sha256 or sha(data), "use": "base"}
        model.update(extra)
        return {"engine": "fake-engine", "repo": "https://example.com/e", "commit": "0" * 40, "models": [model]}

    def place(self, data, name="tiny.gguf"):
        self.models.mkdir(parents=True, exist_ok=True)
        (self.models / name).write_bytes(data)

    def code(self, call):
        with self.assertRaises(GvoiceError) as ctx:
            call()
        return ctx.exception


class CatalogTests(unittest.TestCase):
    def test_shipped_catalog_is_valid_and_pinned(self):
        catalog = models.load("qwentts")
        self.assertEqual(schema.validate(catalog, schema.load_schema("engine-catalog")), [])
        self.assertEqual(catalog["commit"], "5916bf7c79dbb4e66fc059cdc507a79a23a28bb4")
        self.assertEqual([m["id"] for m in catalog["models"]],
                         ["0.6b-base", "1.7b-base", "1.7b-voicedesign", "tokenizer-12hz"])
        self.assertEqual([m["use"] for m in catalog["models"]], ["base", "base", "design", "codec"])
        for m in catalog["models"]:
            self.assertEqual(m["url"], "https://huggingface.co/Serveurperso/Qwen3-TTS-GGUF/resolve/main/" + m["file"])

    def test_model_ids_are_the_ones_of_the_machine_profile(self):
        profile = json.loads((ROOT / "gvoice" / "machine_profiles" / "steam-deck.json").read_text())
        ids = {m["id"] for m in models.load("qwentts")["models"]}
        self.assertTrue({profile["models"]["design"], *profile["models"]["produce"]} <= ids)

    def test_missing_unreadable_and_invalid_catalogs(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "broken.json").write_text("{")
            (Path(tmp) / "empty.json").write_text("{}")
            dup = models.load("qwentts")
            dup["models"].append(dup["models"][0])
            (Path(tmp) / "dup.json").write_text(json.dumps(dup))
            err = self.assertRaises
            with err(GvoiceError) as ctx:
                models.load("nope", tmp)
            self.assertEqual(ctx.exception.code, "models.catalog_missing")
            with err(GvoiceError) as ctx:
                models.load("broken", tmp)
            self.assertEqual(ctx.exception.code, "models.catalog_unreadable")
            with err(GvoiceError) as ctx:
                models.load("empty", tmp)
            self.assertEqual(ctx.exception.code, "models.catalog_invalid")
            self.assertTrue(ctx.exception.errors)
            with err(GvoiceError) as ctx:
                models.load("dup", tmp)
            self.assertEqual(ctx.exception.code, "models.catalog_duplicate")
        with self.assertRaises(GvoiceError) as ctx:
            models.load("../models")
        self.assertEqual(ctx.exception.code, "models.catalog_missing")

    def test_schema_rejects_a_path_as_file_name_and_a_bad_hash(self):
        catalog = models.load("qwentts")
        catalog["models"][0]["file"] = "../x"
        catalog["models"][1]["sha256"] = "ABC"
        paths_ = sorted(e.path for e in schema.validate(catalog, schema.load_schema("engine-catalog")))
        self.assertEqual(paths_, ["/models/0/file", "/models/1/sha256"])


class StatusTests(ModelsBase):
    def state(self, catalog, **kw):
        return models.status(catalog, **kw)[0]

    def test_missing(self):
        item = self.state(self.catalog())
        self.assertEqual((item["state"], item["actual"]), ("missing", None))
        self.assertEqual(item["path"], str(self.models / "tiny.gguf"))

    def test_ok(self):
        self.place(GOOD)
        self.assertEqual(self.state(self.catalog())["state"], "ok")

    def test_bad_size_does_not_read_the_hash(self):
        self.place(GOOD[:-1])
        with mock.patch.object(models, "sha256_of", side_effect=AssertionError("read")):
            item = self.state(self.catalog())
        self.assertEqual((item["state"], item["actual"]), ("bad_size", len(GOOD) - 1))

    def test_bad_sha256_with_the_right_size(self):
        self.place(OTHER)
        self.assertEqual(self.state(self.catalog())["state"], "bad_sha256")

    def test_unchecked_without_the_hash(self):
        self.place(OTHER)
        self.assertEqual(self.state(self.catalog(), check_hash=False)["state"], "unchecked")

    def test_hash_is_read_by_blocks(self):
        self.place(GOOD)
        with mock.patch.object(models, "CHUNK", 1000):
            self.assertEqual(self.state(self.catalog())["state"], "ok")

    def test_unknown_id(self):
        err = self.code(lambda: models.status(self.catalog(), ["nope"]))
        self.assertEqual((err.code, err.params["id"]), ("models.unknown_id", "nope"))

    def test_models_home_overrides(self):
        other = self.tmp / "card"
        (other).mkdir()
        (other / "tiny.gguf").write_bytes(GOOD)
        with mock.patch.dict(os.environ, {"GVOICE_MODELS_HOME": str(other)}):
            self.assertEqual(self.state(self.catalog())["state"], "ok")


class FetchTests(ModelsBase):
    def serve(self, body, declared=None):
        Handler.routes["/tiny.gguf"] = (body, declared)

    def leftovers(self):
        return sorted(p.name for p in self.models.iterdir()) if self.models.exists() else []

    def test_downloads_a_missing_model(self):
        self.serve(GOOD)
        calls = []
        result = models.fetch(self.catalog(), progress=lambda *a: calls.append(a))
        self.assertEqual(result, [{"id": "tiny", "path": str(self.models / "tiny.gguf"), "action": "downloaded"}])
        self.assertEqual((self.models / "tiny.gguf").read_bytes(), GOOD)
        self.assertEqual(self.leftovers(), ["tiny.gguf"])
        self.assertEqual(calls[0], ("tiny", 0, len(GOOD)))
        self.assertEqual(calls[-1], ("tiny", len(GOOD), len(GOOD)))
        self.assertEqual(models.status(self.catalog())[0]["state"], "ok")

    def test_does_not_download_what_is_ok(self):
        self.place(GOOD)
        result = models.fetch(self.catalog())  # no route: a request would be a 404 error
        self.assertEqual(result[0]["action"], "present")

    def test_replaces_a_wrong_file(self):
        self.place(OTHER)
        self.serve(GOOD)
        self.assertEqual(models.fetch(self.catalog())[0]["action"], "downloaded")
        self.assertEqual((self.models / "tiny.gguf").read_bytes(), GOOD)

    def test_only_the_requested_ids(self):
        catalog = self.catalog()
        second = dict(catalog["models"][0], id="second", file="second.gguf", url=self.base + "second.gguf")
        catalog["models"].append(second)
        self.serve(GOOD)
        Handler.routes["/second.gguf"] = (GOOD, None)
        models.fetch(catalog, ["second"])
        self.assertEqual(self.leftovers(), ["second.gguf"])

    def test_sha256_mismatch_leaves_nothing_and_says_why(self):
        self.serve(OTHER)
        err = self.code(lambda: models.fetch(self.catalog()))
        self.assertEqual(err.code, "models.bad_sha256")
        self.assertEqual((err.params["expected"], err.params["actual"]), (sha(GOOD), sha(OTHER)))
        self.assertIn("sha256", err.message("en"))
        self.assertEqual(self.leftovers(), [])

    def test_sha256_mismatch_keeps_the_previous_file(self):
        self.place(GOOD[:-1])
        self.serve(OTHER)
        self.assertEqual(self.code(lambda: models.fetch(self.catalog())).code, "models.bad_sha256")
        self.assertEqual(self.leftovers(), ["tiny.gguf"])
        self.assertEqual((self.models / "tiny.gguf").read_bytes(), GOOD[:-1])

    def test_short_download_honest_length(self):
        self.serve(GOOD[:-10])
        err = self.code(lambda: models.fetch(self.catalog()))
        self.assertEqual((err.code, err.params["expected"], err.params["actual"]),
                         ("models.bad_size", len(GOOD), len(GOOD) - 10))
        self.assertEqual(self.leftovers(), [])

    def test_short_download_cut_connection(self):
        self.serve(GOOD[:-10], declared=len(GOOD))
        err = self.code(lambda: models.fetch(self.catalog()))
        self.assertIn(err.code, ("models.bad_size", "models.download_failed"))
        self.assertEqual(self.leftovers(), [])

    def test_too_long_download(self):
        self.serve(GOOD + b"x")
        err = self.code(lambda: models.fetch(self.catalog()))
        self.assertEqual(err.code, "models.bad_size")
        self.assertEqual(self.leftovers(), [])

    def test_http_error(self):
        err = self.code(lambda: models.fetch(self.catalog()))
        self.assertEqual(err.code, "models.download_failed")
        self.assertIn("404", err.params["reason"])
        self.assertEqual(self.leftovers(), [])

    def test_unreachable_server(self):
        catalog = self.catalog(url="http://127.0.0.1:1/x")
        self.assertEqual(self.code(lambda: models.fetch(catalog)).code, "models.download_failed")
        self.assertEqual(self.leftovers(), [])

    def test_an_old_part_does_not_get_in_the_way(self):
        self.place(b"garbage that is longer than it should be " * 5000, "tiny.gguf.part")
        self.serve(GOOD)
        models.fetch(self.catalog())
        self.assertEqual(self.leftovers(), ["tiny.gguf"])
        self.assertEqual((self.models / "tiny.gguf").read_bytes(), GOOD)

    def test_an_old_part_is_removed_when_the_download_fails(self):
        self.place(b"old", "tiny.gguf.part")
        self.serve(OTHER)
        self.code(lambda: models.fetch(self.catalog()))
        self.assertEqual(self.leftovers(), [])


if __name__ == "__main__":
    unittest.main()
