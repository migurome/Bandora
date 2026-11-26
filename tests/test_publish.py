import tempfile
import unittest
from pathlib import Path

from tools.publish import files_to_publish


class PublishTest(unittest.TestCase):
    def test_only_the_app_is_published(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in ["index.html", "data.js", "sw.js", "data/weave.json", "_smoke.html", "_pwa.html", "_shot.html"]:
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text("x")
            self.assertEqual(sorted(p.as_posix() for p in files_to_publish(root)),
                             ["data.js", "data/weave.json", "index.html", "sw.js"])


if __name__ == "__main__":
    unittest.main()
