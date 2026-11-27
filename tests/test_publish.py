import tempfile
import unittest
from pathlib import Path

from tools.publish import app_version, files_to_publish, keep_from_old, target_dir


class PublishTest(unittest.TestCase):
    def test_only_the_app_is_published(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in ["index.html", "data.js", "sw.js", "data/weave.json", "_smoke.html", "_pwa.html", "_shot.html"]:
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text("x")
            self.assertEqual(sorted(p.as_posix() for p in files_to_publish(root)),
                             ["data.js", "data/weave.json", "index.html", "sw.js"])

    def test_version_is_read_from_the_page(self):
        self.assertEqual(app_version("x\nconst VERSION = 'b0.3.11';  // nota\n"), "b0.3.11")
        with self.assertRaises(ValueError):
            app_version("const VERSION = '0.3.11';")  # sin v ni b no se publica

    def test_beta_goes_to_its_folder_official_to_the_root(self):
        self.assertEqual(target_dir("b0.3.11"), "b0.3.11")
        self.assertEqual(target_dir("v0.3.10"), "")

    def test_what_survives_from_the_previous_publication(self):
        old = ["index.html", "data/weave.json", "b0.3.11/index.html", "b0.3.12/sw.js"]
        # una oficial rehace la raíz y deja las betas; una beta solo cambia su carpeta
        self.assertEqual(keep_from_old(old, "v0.3.13"), ["b0.3.11/index.html", "b0.3.12/sw.js"])
        self.assertEqual(keep_from_old(old, "b0.3.11"), ["index.html", "data/weave.json", "b0.3.12/sw.js"])


if __name__ == "__main__":
    unittest.main()
