"""Discovery adapters and classification helpers for Academic Resources."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src.academic.discover import (
    BrainSpotAdapter,
    LdrpAdapter,
    _parse_ldrp_index,
    classify_type,
    normalize_subject,
    resource_url_allowed,
)


class ClassificationTests(unittest.TestCase):
    def test_pdf_defaults_to_notes(self):
        self.assertEqual(classify_type("Download", "https://thebrainspot.org/storage/x.pdf"), "NOTES")

    def test_pyq_and_assignment(self):
        self.assertEqual(classify_type("OS PYQ 2023", "https://example.com/a"), "PYQ")
        self.assertEqual(classify_type("DBMS Assignment 1", "https://example.com/a"), "ASSIGNMENT")

    def test_subject_aliases(self):
        self.assertEqual(normalize_subject("Operating System", "os")[0], "Operating Systems")
        self.assertEqual(normalize_subject("Database Management Systems", "dbms")[1], "DBMS")

    def test_external_drive_allowed_as_resource_url(self):
        self.assertTrue(resource_url_allowed("https://drive.google.com/file/d/abc/view"))
        self.assertFalse(resource_url_allowed("https://evil.example/x.pdf"))


class LdrpIndexParseTests(unittest.TestCase):
    def test_parses_subject_cards(self):
        html = """
        <h3>DBMS</h3><span>Sem 3</span>
        <a href="includes/view_material.php?sem_id=8&subject_id=23">View Content</a>
        <h3>OS</h3><span>Sem 4</span>
        <a href="includes/view_material.php?sem_id=13&subject_id=30">View Content</a>
        """
        cards = _parse_ldrp_index(html, "https://ldrp.bhavsarneev.de/index.php")
        names = {c["name"]: c["semester"] for c in cards}
        self.assertEqual(names["DBMS"], 3)
        self.assertEqual(names["OS"], 4)


class BrainSpotDiscoverTests(unittest.TestCase):
    def test_discovers_pdfs_from_subject_pages(self):
        index = """
        <a href="https://thebrainspot.org/os/"><img/></a>
        <a href="https://thebrainspot.org/course/">Course</a>
        """
        subject = """
        <h1>Operating Systems</h1>
        <a href="https://thebrainspot.org/storage/2024/07/Deadlock.pdf">Download</a>
        """

        def fake_fetch(url, timeout=15):
            if "2nd-year" in url:
                return index, None
            if url.rstrip("/").endswith("/os"):
                return subject, None
            return "<html></html>", None

        with patch("src.academic.discover.fetch_html", side_effect=fake_fetch):
            with patch("src.academic.discover.time.sleep", return_value=None):
                result = BrainSpotAdapter().discover(
                    {"website_url": "https://thebrainspot.org/2nd-year/", "code": "brainspot_y2"},
                    pause=0,
                )
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["resources"]), 1)
        self.assertEqual(result["resources"][0]["original_url"], "https://thebrainspot.org/storage/2024/07/Deadlock.pdf")
        self.assertEqual(result["resources"][0]["resource_format"], "PDF")
        self.assertEqual(result["resources"][0]["year_id"], "YEAR_2")


class LdrpDiscoverTests(unittest.TestCase):
    def test_discovers_drive_links_from_chapters(self):
        index = """
        <h3>OS</h3><span>Sem 4</span>
        <a href="includes/view_material.php?sem_id=13&subject_id=30">View</a>
        """
        subject = """
        <a href="view_material.php?sem_id=13&subject_id=30&chapter_id=50">Chapter Resource Material</a>
        """
        chapter = """
        <h3>Unit 1 Notes.pdf</h3>
        <a href="https://drive.google.com/file/d/abc123/view?usp=drivesdk">Download Material</a>
        """

        def fake_fetch(url, timeout=15):
            if "index.php" in url:
                return index, None
            if "chapter_id=50" in url:
                return chapter, None
            if "subject_id=30" in url:
                return subject, None
            return "", "unexpected"

        with patch("src.academic.discover.fetch_html", side_effect=fake_fetch):
            with patch("src.academic.discover.time.sleep", return_value=None):
                result = LdrpAdapter().discover(
                    {"website_url": "https://ldrp.bhavsarneev.de/index.php", "code": "ldrp_study"},
                    pause=0,
                )
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(len(result["resources"]), 1)
        self.assertTrue(result["resources"][0]["original_url"].startswith("https://drive.google.com/"))
        self.assertEqual(result["resources"][0]["semester_id"], "SEM_4")


if __name__ == "__main__":
    unittest.main()
