"""Tests for SEC archives helpers."""

import unittest

from edgarpack.sec.archives import identify_html_files


class TestIdentifyHtmlFiles(unittest.TestCase):
    def test_skips_index_html_and_sorts(self) -> None:
        index = {
            "directory": {
                "item": [
                    {"name": "index.html"},
                    {"name": "B.htm"},
                    {"name": "a.htm"},
                    {"name": "doc.htm"},
                    {"name": "a.htm"},
                ]
            }
        }
        files = identify_html_files(index, primary_doc="doc.htm")
        self.assertEqual(files[0], "doc.htm")
        self.assertNotIn("index.html", files)
        self.assertEqual(files, ["doc.htm", "a.htm", "B.htm"])


if __name__ == "__main__":
    unittest.main()

