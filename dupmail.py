#!/usr/bin/env python3
"""dupmail - A tool for finding duplicate emails in a maildir.

This module provides functionality to scan email directories and identify
duplicate emails based on configurable metadata fields. It supports
internationalized email headers and is designed to be memory-efficient
by only storing email metadata rather than full content.
"""

import email.header
import email.iterators
import email.utils
import hashlib
import re
import sys
import os
import os.path
import glob
import argparse
import json
import logging
from typing import Dict, List, Iterator, Any


# Configure logging
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Security constants
MAX_FILE_SIZE_MB = 50  # Maximum email file size in MB
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


class Email:
    """Represents email metadata for duplicate detection.
    
    Attributes:
        id: The file path of the email
        data: Dictionary containing parsed email fields
    """
    def __init__(self, id: str, data: Dict[str, Any]) -> None:
        """Initialize an Email object.
        
        Args:
            id: The file path of the email
            data: Dictionary containing parsed email fields
        """
        self.id = id
        self.data = data
    
    def fails(self) -> int:
        """Count the number of fields that are empty or couldn't be parsed.
        
        Returns:
            Number of failed fields
        """
        count = 0
        for value in self.data.values():
            if isinstance(value,int):
                if value == 0:
                    count += 1
            else:
                if len(value) == 0:
                    count += 1
        return count
    
    def __repr__(self) -> str:
        return str(self.id)
    
    def __str__(self) -> str:
        return "|" + "|".join([str(self.data[key]) for key in sorted(self.data)]) + "|"
    
    def hash(self) -> str:
        """Generate SHA256 hash of the email metadata.
        
        Returns:
            Hexadecimal string representation of the hash
        """
        return hashlib.sha256(str(self).encode()).hexdigest()

class EmailParser:
    """Parses email files and extracts metadata fields."""
    key_method_prefix = "process_"
    
    @staticmethod
    def parse(file: str, keys: List[str]) -> Email:
        """Parse an email file and extract specified metadata fields.
        
        Args:
            file: Path to the email file
            keys: List of fields to extract
            
        Returns:
            Email object containing parsed metadata
            
        Raises:
            ValueError: If file size exceeds MAX_FILE_SIZE_BYTES
            OSError: If file cannot be accessed
        """
        # Security check: validate file size
        file_size = os.path.getsize(file)
        if file_size > MAX_FILE_SIZE_BYTES:
            raise ValueError(f"File {file} exceeds maximum size limit of {MAX_FILE_SIZE_MB}MB")
            
        parser = EmailParser(file, keys)
        email = Email(file, parser.data())
        return email
    
    @classmethod
    def valid_keys(cls) -> List[str]:
        """Get list of valid field names that can be parsed.
        
        Returns:
            List of available field names (e.g., 'from', 'to', 'subject', 'body_size')
        """
        prefix = cls.key_method_prefix
        return [m[len(prefix):] for m in dir(cls) if m.startswith(prefix)]
    
    def __init__(self, file: str, keys: List[str]) -> None:
        """Initialize parser and extract specified fields from email.
        
        Args:
            file: Path to the email file
            keys: List of fields to extract
        """
        try:
            with open(file, 'r', encoding='utf-8', errors='replace') as fp:
                self._eml = email.message_from_file(fp)
        except Exception as e:
            logger.error(f"Failed to open email file {file}: {e}")
            raise
            
        self._data = {}
        for key in keys:
            try:
                self._data[key] = self.process(key)
            except Exception as e:
                logger.warning(f"Failed to process field '{key}' for {file}: {e}")
                self._data[key] = "" if key != "body_size" and key != "body_lines" else 0
    
    def data(self) -> Dict[str, Any]:
        """Get the parsed email data.
        
        Returns:
            Dictionary of parsed fields
        """
        return self._data
    
    def process(self, key: str) -> Any:
        """Dynamically call the appropriate process_* method for a field.
        
        Args:
            key: Field name to process
            
        Returns:
            Processed field value
        """
        func = getattr(self, EmailParser.key_method_prefix+key)
        return func()
    
    def process_from(self) -> str:
        """Extract and parse the From email address."""
        return self.parse_emails(self._eml.get_all("from", []))
    
    def process_to(self) -> str:
        """Extract and parse all recipient email addresses (To, CC, BCC)."""
        emails = self._eml.get_all("to", []) + \
                 self._eml.get_all("cc", []) + \
                 self._eml.get_all("bcc", [])
        return self.parse_emails(emails)
    
    def process_subject(self) -> str:
        """Extract and normalize the email subject."""
        return self.parse_string_flat(self._eml.get("subject", ""))
    
    def process_date(self) -> str:
        """Extract and format the email date as yyyy-mm-dd."""
        return self.parse_date(self._eml.get("date", ""))
    
    def process_body_size(self) -> int:
        """Calculate total byte size of non-empty body lines."""
        size = 0
        for line in self.body():
            size = size + len(line)
        return size
    
    def process_body_lines(self) -> int:
        """Count the number of non-empty body lines."""
        lines = 0
        for line in self.body():
            lines += 1
        return lines
    
    def process_body_hash(self) -> str:
        """Calculate SHA256 hash of non-empty body lines."""
        hashx = hashlib.sha256()
        for line in self.body():
            hashx.update(line.encode())
        return hashx.hexdigest()
    
    def parse_string(self, header: Any, encoding: str = "utf-8") -> str:
        """Convert/decode email headers into string.
        
        Handles:
        - Simple string headers
        - Encoded headers (bytes)
        - Internationalized headers (e.g., =?iso-8859-1?q?p=F6stal?=)
        
        Args:
            header: The header value to parse
            encoding: Character encoding to use
            
        Returns:
            Decoded string value
        """
        #
        # simple string headers
        #
        if type(header) is str:
            # Check if it's a MIME-encoded header
            decoded = email.header.decode_header(header)
            if len(decoded) == 1 and decoded[0][1] is None:
                # Not MIME-encoded, return as-is
                return decoded[0][0] if isinstance(decoded[0][0], str) else decoded[0][0].decode('utf-8')
            else:
                # MIME-encoded, decode it
                parts = []
                for text, charset in decoded:
                    if isinstance(text, bytes):
                        if charset:
                            parts.append(text.decode(charset))
                        else:
                            parts.append(text.decode('utf-8'))
                    else:
                        parts.append(text)
                return ''.join(parts)
        #
        # encoded headers
        #
        elif type(header) is bytes:
            # tries to parse header with the given encoding, falls back to utf-8
            try:
                return header.decode(encoding)
            except (UnicodeDecodeError, AttributeError) as e:
                logger.debug(f"Failed to decode header with {encoding}: {e}")
                if encoding != "utf-8":
                    return self.parse_string(header, "utf-8")
                else:
                    return ""
        #
        # internatialized headers
        #
        elif type(header) is email.header.Header:
            value, header_encoding = email.header.decode_header(header)[0]
            return self.parse_string(value, header_encoding)
        #
        # invalid headers
        #
        else:
            raise TypeError("invalid header: %s %s"%(header, header.__class__))
    
    def parse_string_flat(self, header: Any) -> str:
        """Parse string and normalize whitespace.
        
        Removes duplicate spaces/tabs/newlines and converts to lowercase.
        
        Args:
            header: Header value to parse
            
        Returns:
            Normalized string
        """
        value = self.parse_string(header)
        # Replace all whitespace characters with single space
        return re.sub(r"\s+", " ", value.strip().lower())
    
    def parse_emails(self, headers: List[str]) -> str:
        """Extract email addresses from headers.
        
        Removes real names, lowercases addresses, and returns them sorted.
        
        Args:
            headers: List of email header values
            
        Returns:
            Space-separated sorted email addresses
        """
        addresses = set()
        for header in headers:
            # Split by comma for multiple addresses in one header
            for addr_part in header.split(','):
                (_, addr) = email.utils.parseaddr(self.parse_string_flat(addr_part))
                if len(addr) > 0:
                    addresses.add(addr.lower())
        return " ".join(sorted(addresses))
    
    def parse_date(self, header: str) -> str:
        """Parse date header and format as yyyy-mm-dd.
        
        Args:
            header: Date header value
            
        Returns:
            Formatted date string or empty string on failure
        """
        try:
            return email.utils.parsedate_to_datetime(header).strftime("%Y-%m-%d")
        except (TypeError, ValueError, AttributeError) as e:
            logger.debug(f"Failed to parse date header: {e}")
            return ""
    
    def body(self) -> Iterator[str]:
        """Iterate over non-empty body lines with whitespace removed.
        
        Yields:
            Non-empty body lines with all whitespace removed
        """
        for line in email.iterators.body_line_iterator(self._eml):
            # Remove all whitespace characters
            l = re.sub(r"\s", "", line)
            if len(l) > 0:
                yield l

class Progress:
    """Display processing progress to stderr."""
    def __init__(self, obj: List[Any], name: str) -> None:
        """Initialize progress tracker.
        
        Args:
            obj: List of items to process
            name: Name for progress display
        """
        self.name = name
        self.i = 0
        self.show("counting %s"%(self.name))
        self.total = len(obj)
    
    def show(self, *args, **kwargs) -> None:
        """Print message to stderr."""
        print(*args, file=sys.stderr, **kwargs)
    
    def next(self) -> None:
        """Increment and display progress."""
        self.i += 1
        self.show("processing %d/%d %s"%(self.i, self.total, self.name), end="\r")
    
    def end(self) -> None:
        """Clear the progress line."""
        self.show("")

class EmailDups:
    """Find and manage duplicate emails in a directory."""
    
    def __init__(self, path: str, keys: List[str], skip_at: int) -> None:
        """Initialize duplicate finder.
        
        Args:
            path: Directory path to scan for emails
            keys: List of fields to use for duplicate detection
            skip_at: Skip emails with this many or more parsing failures
            
        Raises:
            ValueError: If path is invalid or potentially unsafe
        """
        # Security: validate path
        self.path = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(self.path):
            raise ValueError(f"Path does not exist: {self.path}")
        if not os.path.isdir(self.path):
            raise ValueError(f"Path is not a directory: {self.path}")
            
        # Ensure we don't traverse outside the specified directory
        self.base_path = os.path.realpath(self.path)
        
        self.keys = keys
        self.skip_at = skip_at
        self.dups: Dict[str, List[Email]] = {}
    
    def fglob(self) -> Iterator[str]:
        """Safely iterate over files in the directory.
        
        Yields:
            Absolute paths to files within the base directory
        """
        for f in glob.iglob(self.path+"/**", recursive=True):
            if os.path.isfile(f):
                # Security: ensure file is within base directory
                real_path = os.path.realpath(f)
                if real_path.startswith(self.base_path):
                    yield f
                else:
                    logger.warning(f"Skipping file outside base directory: {f}")
    
    def calculate(self) -> None:
        """Find duplicate emails based on configured fields."""
        dups: Dict[str, List[Email]] = {}
        p = Progress(list(self.fglob()), "emails")
        for file in self.fglob():
            p.next()
            try:
                emlhash = EmailParser.parse(file, self.keys)
                fails = emlhash.fails()
                if fails >= self.skip_at:
                    p.show("skipping %s with %d fails"%(file, fails))
                    continue
                xhash = emlhash.hash()
                if xhash not in dups:
                    dups[xhash] = []
                dups[xhash].append(emlhash)
            except ValueError as e:
                logger.warning(f"Skipping {file}: {e}")
                p.show(f"Skipping {file}: {e}")
            except Exception as e:
                logger.error(f"Error processing {file}: {e}")
                p.show(f"Error processing {file}: {e}")
        p.end()
        
        # Remove non-duplicate emails
        for key in list(dups.keys()):
            if len(dups[key]) <= 1:
                dups.pop(key, None)
        
        self.dups = dups
        
        p.show("%d dupmails found"%(self.count()))
    
    def count(self) -> int:
        """Count total number of duplicate emails.
        
        Returns:
            Number of duplicate emails (excluding the original)
        """
        count = 0
        for dup in self.dups.values():
            count = count + len(dup)-1
        return count
    
    def print_result(self, format: str) -> None:
        """Print duplicate results in specified format.
        
        Args:
            format: Output format ('plain' or 'json')
        """
        if format == "json":
            json_obj = []
            for dup in self.dups.values():
                json_obj.append([repr(item) for item in dup])
            print(json.dumps(json_obj))
        elif format == "plain":
            for dup in self.dups.values():
                print(" ".join([repr(item) for item in dup]))
        else:
            print("invalid format: %s"%(format))

def main():
    """Main entry point for the dupmail script."""
    description = ("dupmail is a modern, simple, small and lightweight tool "
                    "that finds duplicate emails")
    epilog = """
keys:

  from:       email address only taken out of From header
  to:         ordered email address list including To, CC and BCC headers
  date:       Date header formatted as yyyy-mm-dd, time is not included
  subject:    lowercase, space removed Subject header
  body_lines: the number of non empty lines in the body, including attachments
  body_size:  total byte size of non empty body lines, including attachments
  body_hash:  sha256 representation non empty body lines, including attachments
"""
    parser = argparse.ArgumentParser(description=description, epilog=epilog,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-s", "--skip-if", default=2, type=int,
                        help=("skip emails if unable to parse at least SKIP_AT fields, "
                              "default: 2"))
    parser.add_argument("-f", "--format", default="plain", choices=["plain", "json"],
                        help="print results using this format, default: plain")
    parser.add_argument("-k", "--keys", type=str, default="from,to,date,subject,body_lines,body_hash",
                        help=("comma separated list of fields to identify duplicates, "
                              "default: from,to,date,subject,body_lines,body_hash"))
    parser.add_argument("path", metavar="PATH", help="dir with emails")
    args = parser.parse_args()

    keys = args.keys.split(",")
    if not keys:
        parser.error("invalid number of KEYS")

    for key in keys:
        if key not in EmailParser.valid_keys():
            parser.error("invalid KEY: %s"%(key))

    try:
        emaildups = EmailDups(args.path, keys, args.skip_if)
        emaildups.calculate()
        emaildups.print_result(args.format)
    except ValueError as e:
        parser.error(str(e))
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
