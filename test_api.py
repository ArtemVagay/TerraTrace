from pathlib import Path
import unittest

import httpx

from main import app
from services.log_parser import MAX_BYTES

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_home_and_assets(self):
        for url, fragment in [("/", "logForm"), ("/guide", "helloButton"), ("/static/app.js", "fetchJSON"), ("/static/styles.css", ".button-primary")]:
            with self.subTest(url=url):
                response = await self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertIn(fragment, response.text)

    async def test_demo_uses_real_analysis(self):
        response = await self.client.get("/api/logs/demo")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"]["errors"], 12)
        self.assertEqual(len(response.json()["groups"]), 4)

    async def test_upload(self):
        response = await self.client.post("/api/logs/analyze", files={"file": ("client.log", (EXAMPLES / "boss_test.log").read_bytes(), "text/plain")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["filename"], "client.log")
        self.assertEqual(response.json()["summary"]["errors"], 12)

    async def test_filename_is_a_basename(self):
        response = await self.client.post("/api/logs/analyze", files={"file": ("../../test.log", b"ERROR: MY_TEST_ERROR", "text/plain")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["filename"], "test.log")

    async def test_pasted_text(self):
        response = await self.client.post("/api/logs/text", json={"text": "ERROR: MY_TEST_ERROR"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["groups"][0]["finding"]["rule_id"], "unknown")

    async def test_invalid_files(self):
        for filename, data, status in [("test.exe", b"ERROR: bad", 415), ("empty.log", b"", 400), ("binary.log", b"\x00\x01", 400), ("big.log", b"x" * (MAX_BYTES + 1), 413)]:
            with self.subTest(filename=filename):
                response = await self.client.post("/api/logs/analyze", files={"file": (filename, data, "text/plain")})
                self.assertEqual(response.status_code, status)
                self.assertIn("detail", response.json())

    async def test_missing_file(self):
        self.assertEqual((await self.client.post("/api/logs/analyze")).status_code, 422)

    async def test_blank_text(self):
        self.assertEqual((await self.client.post("/api/logs/text", json={"text": "   "})).status_code, 400)

    async def test_multibyte_text_limit(self):
        response = await self.client.post("/api/logs/text", json={"text": "я" * (MAX_BYTES // 2 + 1)})
        self.assertEqual(response.status_code, 413)

    async def test_example_download(self):
        response = await self.client.get("/api/logs/example")
        self.assertEqual(response.status_code, 200)
        self.assertIn("boss_test.log", response.headers["content-disposition"])

    async def test_api_docs_and_health(self):
        self.assertEqual((await self.client.get("/docs")).status_code, 200)
        schema = (await self.client.get("/openapi.json")).json()
        self.assertIn("/api/logs/analyze", schema["paths"])
        self.assertEqual((await self.client.get("/api/health")).json()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
