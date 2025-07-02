#!/usr/bin/env python3
"""Unit tests for dupmail.py"""

import unittest
import tempfile
import shutil
import os
import json
from unittest.mock import patch, MagicMock

# Import the module under test
import dupmail


class TestEmail(unittest.TestCase):
    """Test cases for the Email class."""
    
    def test_email_init(self):
        """Test Email initialization."""
        data = {"from": "test@example.com", "to": "recipient@example.com"}
        email_obj = dupmail.Email("/path/to/email.eml", data)
        
        self.assertEqual(email_obj.id, "/path/to/email.eml")
        self.assertEqual(email_obj.data, data)
    
    def test_email_fails_count(self):
        """Test counting failed fields."""
        # Test with all valid fields
        data = {"from": "test@example.com", "body_size": 100}
        email_obj = dupmail.Email("test.eml", data)
        self.assertEqual(email_obj.fails(), 0)
        
        # Test with empty string field
        data = {"from": "", "body_size": 100}
        email_obj = dupmail.Email("test.eml", data)
        self.assertEqual(email_obj.fails(), 1)
        
        # Test with zero integer field
        data = {"from": "test@example.com", "body_size": 0}
        email_obj = dupmail.Email("test.eml", data)
        self.assertEqual(email_obj.fails(), 1)
        
        # Test with multiple failures
        data = {"from": "", "to": "", "body_size": 0, "body_lines": 0}
        email_obj = dupmail.Email("test.eml", data)
        self.assertEqual(email_obj.fails(), 4)
    
    def test_email_repr(self):
        """Test Email string representation."""
        email_obj = dupmail.Email("/path/to/email.eml", {})
        self.assertEqual(repr(email_obj), "/path/to/email.eml")
    
    def test_email_str(self):
        """Test Email string conversion."""
        data = {"from": "test@example.com", "to": "recipient@example.com"}
        email_obj = dupmail.Email("test.eml", data)
        # Should be sorted by key
        self.assertEqual(str(email_obj), "|test@example.com|recipient@example.com|")
    
    def test_email_hash(self):
        """Test Email hash generation."""
        data = {"from": "test@example.com"}
        email_obj = dupmail.Email("test.eml", data)
        hash_val = email_obj.hash()
        
        # Should be a valid SHA256 hash (64 hex characters)
        self.assertEqual(len(hash_val), 64)
        self.assertTrue(all(c in '0123456789abcdef' for c in hash_val))
        
        # Same data should produce same hash
        email_obj2 = dupmail.Email("test2.eml", data)
        self.assertEqual(hash_val, email_obj2.hash())


class TestEmailParser(unittest.TestCase):
    """Test cases for the EmailParser class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        self.test_email_path = os.path.join(self.test_dir, "test.eml")
        
    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.test_dir)
    
    def create_test_email(self, content):
        """Helper to create a test email file."""
        with open(self.test_email_path, 'w') as f:
            f.write(content)
        return self.test_email_path
    
    def test_valid_keys(self):
        """Test that valid_keys returns expected fields."""
        keys = dupmail.EmailParser.valid_keys()
        expected_keys = ["from", "to", "subject", "date", "body_size", "body_lines", "body_hash"]
        
        for key in expected_keys:
            self.assertIn(key, keys)
    
    def test_parse_simple_email(self):
        """Test parsing a simple email."""
        email_content = """From: sender@example.com
To: recipient@example.com
Subject: Test Email
Date: Mon, 1 Jan 2024 12:00:00 +0000

This is a test email body.
With multiple lines.
"""
        self.create_test_email(email_content)
        
        keys = ["from", "to", "subject", "date"]
        email_obj = dupmail.EmailParser.parse(self.test_email_path, keys)
        
        self.assertEqual(email_obj.data["from"], "sender@example.com")
        self.assertEqual(email_obj.data["to"], "recipient@example.com")
        self.assertEqual(email_obj.data["subject"], "test email")
        self.assertEqual(email_obj.data["date"], "2024-01-01")
    
    def test_parse_body_metrics(self):
        """Test parsing body size and lines."""
        email_content = """From: sender@example.com
Subject: Test

Line 1
Line 2

Line 3
"""
        self.create_test_email(email_content)
        
        keys = ["body_size", "body_lines", "body_hash"]
        email_obj = dupmail.EmailParser.parse(self.test_email_path, keys)
        
        # Body without spaces: "Line1Line2Line3"
        self.assertEqual(email_obj.data["body_size"], 15)
        self.assertEqual(email_obj.data["body_lines"], 3)
        self.assertTrue(email_obj.data["body_hash"])  # Should have a hash
    
    def test_parse_multiple_recipients(self):
        """Test parsing emails with multiple recipients."""
        email_content = """From: sender@example.com
To: user1@example.com, user2@example.com
Cc: user3@example.com
Bcc: user4@example.com
Subject: Test

Body
"""
        self.create_test_email(email_content)
        
        keys = ["to"]
        email_obj = dupmail.EmailParser.parse(self.test_email_path, keys)
        
        # Should contain all recipients sorted
        expected = "user1@example.com user2@example.com user3@example.com user4@example.com"
        self.assertEqual(email_obj.data["to"], expected)
    
    def test_parse_internationalized_header(self):
        """Test parsing internationalized headers."""
        email_content = """From: sender@example.com
Subject: =?iso-8859-1?q?p=F6stal?=
Date: Mon, 1 Jan 2024 12:00:00 +0000

Body
"""
        self.create_test_email(email_content)
        
        keys = ["subject"]
        email_obj = dupmail.EmailParser.parse(self.test_email_path, keys)
        
        # Should decode to "pöstal" and normalize to "postal" (lowercase)
        self.assertEqual(email_obj.data["subject"], "pöstal")
    
    def test_file_size_limit(self):
        """Test that large files are rejected."""
        # Create a file larger than the limit
        large_content = "X" * (dupmail.MAX_FILE_SIZE_BYTES + 1)
        self.create_test_email(large_content)
        
        with self.assertRaises(ValueError) as context:
            dupmail.EmailParser.parse(self.test_email_path, ["from"])
        
        self.assertIn("exceeds maximum size limit", str(context.exception))
    
    def test_parse_string_with_whitespace(self):
        """Test parse_string_flat normalizes whitespace."""
        parser = dupmail.EmailParser.__new__(dupmail.EmailParser)
        parser._eml = MagicMock()
        
        # Test multiple spaces
        result = parser.parse_string_flat("  multiple   spaces  ")
        self.assertEqual(result, "multiple spaces")
        
        # Test tabs and newlines
        result = parser.parse_string_flat("tabs\t\there\nand\nnewlines")
        self.assertEqual(result, "tabs here and newlines")
    
    def test_parse_date_invalid(self):
        """Test parsing invalid date returns empty string."""
        parser = dupmail.EmailParser.__new__(dupmail.EmailParser)
        parser._eml = MagicMock()
        
        result = parser.parse_date("invalid date")
        self.assertEqual(result, "")
        
        result = parser.parse_date("")
        self.assertEqual(result, "")


class TestEmailDups(unittest.TestCase):
    """Test cases for the EmailDups class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.test_dir)
    
    def create_email_file(self, subdir, filename, content):
        """Helper to create email files in test directory."""
        dir_path = os.path.join(self.test_dir, subdir)
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, filename)
        with open(file_path, 'w') as f:
            f.write(content)
        return file_path
    
    def test_init_valid_path(self):
        """Test EmailDups initialization with valid path."""
        keys = ["from", "to"]
        skip_at = 2
        
        dups = dupmail.EmailDups(self.test_dir, keys, skip_at)
        
        self.assertEqual(dups.keys, keys)
        self.assertEqual(dups.skip_at, skip_at)
        self.assertTrue(os.path.isabs(dups.path))
    
    def test_init_invalid_path(self):
        """Test EmailDups initialization with invalid paths."""
        # Non-existent path
        with self.assertRaises(ValueError) as context:
            dupmail.EmailDups("/non/existent/path", ["from"], 2)
        self.assertIn("Path does not exist", str(context.exception))
        
        # File instead of directory
        file_path = os.path.join(self.test_dir, "file.txt")
        with open(file_path, 'w') as f:
            f.write("test")
        
        with self.assertRaises(ValueError) as context:
            dupmail.EmailDups(file_path, ["from"], 2)
        self.assertIn("Path is not a directory", str(context.exception))
    
    def test_fglob(self):
        """Test file globbing."""
        # Create test structure
        self.create_email_file("inbox", "email1.eml", "test1")
        self.create_email_file("inbox", "email2.eml", "test2")
        self.create_email_file("sent", "email3.eml", "test3")
        
        dups = dupmail.EmailDups(self.test_dir, ["from"], 2)
        files = list(dups.fglob())
        
        self.assertEqual(len(files), 3)
        # All files should be within test_dir
        for f in files:
            self.assertTrue(f.startswith(dups.base_path))
    
    def test_find_duplicates(self):
        """Test finding duplicate emails."""
        # Create duplicate emails
        email_content1 = """From: sender@example.com
To: recipient@example.com
Subject: Test
Date: Mon, 1 Jan 2024 12:00:00 +0000

This is the body.
"""
        
        # Same content, different file
        email_content2 = email_content1
        
        # Different content
        email_content3 = """From: other@example.com
To: recipient@example.com
Subject: Different
Date: Mon, 2 Jan 2024 12:00:00 +0000

Different body.
"""
        
        self.create_email_file("", "dup1.eml", email_content1)
        self.create_email_file("", "dup2.eml", email_content2)
        self.create_email_file("", "unique.eml", email_content3)
        
        keys = ["from", "to", "subject", "body_hash"]
        dups = dupmail.EmailDups(self.test_dir, keys, 2)
        
        # Capture stderr to suppress progress output
        with patch('sys.stderr'):
            dups.calculate()
        
        # Should find 1 set of duplicates (dup1 and dup2)
        self.assertEqual(len(dups.dups), 1)
        
        # Should report 1 duplicate (not counting the original)
        self.assertEqual(dups.count(), 1)
    
    def test_print_result_plain(self):
        """Test plain output format."""
        dups = dupmail.EmailDups(self.test_dir, ["from"], 2)
        
        # Mock some duplicates
        email1 = dupmail.Email("/path/email1.eml", {"from": "test@example.com"})
        email2 = dupmail.Email("/path/email2.eml", {"from": "test@example.com"})
        dups.dups = {"hash1": [email1, email2]}
        
        # Capture output
        with patch('builtins.print') as mock_print:
            dups.print_result("plain")
        
        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]
        self.assertIn("/path/email1.eml", output)
        self.assertIn("/path/email2.eml", output)
    
    def test_print_result_json(self):
        """Test JSON output format."""
        dups = dupmail.EmailDups(self.test_dir, ["from"], 2)
        
        # Mock some duplicates
        email1 = dupmail.Email("/path/email1.eml", {"from": "test@example.com"})
        email2 = dupmail.Email("/path/email2.eml", {"from": "test@example.com"})
        dups.dups = {"hash1": [email1, email2]}
        
        # Capture output
        with patch('builtins.print') as mock_print:
            dups.print_result("json")
        
        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]
        
        # Should be valid JSON
        parsed = json.loads(output)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(len(parsed[0]), 2)
        self.assertIn("/path/email1.eml", parsed[0])
        self.assertIn("/path/email2.eml", parsed[0])


class TestProgress(unittest.TestCase):
    """Test cases for the Progress class."""
    
    def test_progress_tracking(self):
        """Test progress tracking functionality."""
        items = ["item1", "item2", "item3"]
        
        with patch('sys.stderr'):
            progress = dupmail.Progress(items, "test items")
            
            self.assertEqual(progress.total, 3)
            self.assertEqual(progress.i, 0)
            
            progress.next()
            self.assertEqual(progress.i, 1)
            
            progress.next()
            self.assertEqual(progress.i, 2)
            
            progress.end()


class TestIntegration(unittest.TestCase):
    """Integration tests for the complete dupmail functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.test_dir)
    
    def test_end_to_end_duplicate_detection(self):
        """Test complete duplicate detection workflow."""
        # Create test emails
        email1 = """From: sender@example.com
To: recipient@example.com
Subject: Important Message
Date: Mon, 1 Jan 2024 12:00:00 +0000

This is an important message.
Please read carefully.
"""
        
        email2 = """From: sender@example.com
To: recipient@example.com
Subject: Important Message
Date: Mon, 1 Jan 2024 12:00:00 +0000

This is an important message.
Please read carefully.
"""
        
        email3 = """From: different@example.com
To: recipient@example.com
Subject: Different Message
Date: Mon, 2 Jan 2024 12:00:00 +0000

This is a different message.
"""
        
        # Create files
        with open(os.path.join(self.test_dir, "email1.eml"), 'w') as f:
            f.write(email1)
        with open(os.path.join(self.test_dir, "email2.eml"), 'w') as f:
            f.write(email2)
        with open(os.path.join(self.test_dir, "email3.eml"), 'w') as f:
            f.write(email3)
        
        # Run dupmail
        keys = ["from", "to", "subject", "date", "body_hash"]
        
        with patch('sys.stderr'):  # Suppress progress output
            dups = dupmail.EmailDups(self.test_dir, keys, 2)
            dups.calculate()
        
        # Should find exactly 1 duplicate
        self.assertEqual(dups.count(), 1)
        
        # The duplicate set should contain email1 and email2
        dup_sets = list(dups.dups.values())
        self.assertEqual(len(dup_sets), 1)
        self.assertEqual(len(dup_sets[0]), 2)
        
        # Get the file paths
        dup_paths = [email.id for email in dup_sets[0]]
        self.assertIn(os.path.join(self.test_dir, "email1.eml"), dup_paths)
        self.assertIn(os.path.join(self.test_dir, "email2.eml"), dup_paths)


if __name__ == '__main__':
    unittest.main()