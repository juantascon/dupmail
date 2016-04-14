#!/usr/bin/env python3

import mailbox
import email.header
import email.iterators
import email.utils
import hashlib
import re
import sys
import argparse
import json


#
# Email Metadata representation
#
class Email:
    #
    # data is a dict containing every parsed field
    #
    def __init__(self, id, data):
        self.id = id
        self.data = data
    
    #
    # Number of fields that are either empty or couldn't be parsed
    #
    def fails(self):
        count = 0
        for value in self.data.values():
            if isinstance(value,int):
                if value == 0:
                    count += 1
            else:
                if len(value) == 0:
                    count += 1
        return count
    
    def __repr__(self):
        return str(self.id)
    
    def __str__(self):
        return "|" + "|".join([str(self.data[key]) for key in sorted(self.data)]) + "|"
    
    def hash(self):
        return hashlib.sha256(str(self).encode()).hexdigest()

#
# Parses 
#
class EmailParser:
    key_method_prefix = "process_"
    
    #
    # Parses an email and returns its metadata representation
    #
    @staticmethod
    def parse(eml, keys, id):
        parser = EmailParser(eml, keys)
        email = Email(id, parser.data())
        return email
    
    #
    # A key is nothing but a parsable field, most are email headers such as:
    # to, from, etc, others however, represent body information such as size
    # or number of lines
    # This functions lists available field parsers, ej: from, to, subject,
    # body_size
    #
    @classmethod
    def valid_keys(cls):
        prefix = cls.key_method_prefix
        return [m[len(prefix):] for m in dir(cls) if m.startswith(prefix)]
    
    def __init__(self, eml, keys):
        self._eml = eml
        self._data = {}
        for key in keys:
            self._data[key] = self.process(key)
    
    def data(self):
        return self._data
    
    #
    # Dynamically calls any "process_" function
    #
    def process(self, key):
        func = getattr(self, EmailParser.key_method_prefix+key)
        return func()
    
    def process_from(self):
        return self.parse_emails(self._eml.get_all("from", []))
    
    def process_to(self):
        emails = self._eml.get_all("to", []) + \
                 self._eml.get_all("cc", []) + \
                 self._eml.get_all("bcc", [])
        return self.parse_emails(emails)
    
    def process_subject(self):
        return self.parse_string_flat(self._eml.get("subject", ""))
    
    def process_date(self):
        return self.parse_date(self._eml.get("date", ""))
    
    def process_body_size(self):
        size = 0
        for line in self.body():
            size = size + len(line)
        return size
    
    def process_body_lines(self):
        lines = 0
        for line in self.body():
            lines += 1
        return lines
    
    def process_body_hash(self):
        hashx = hashlib.sha256()
        [hashx.update(line.encode) for line in self.body()]
        return hashx.hexdigest()
    
    #
    # Converts/decodes email headers into string, it considers:
    # internatialized headers such as: =?iso-8859-1?q?p=F6stal?=
    # and utf-8/encoded headers such as: pöstal
    #
    def parse_string(self, header, encoding="utf-8"):
        #
        # simple string headers
        #
        if type(header) is str:
            return header
        #
        # encoded headers
        #
        elif type(header) is bytes:
            # tries to parse header with the given encoding, falls back to utf-8
            try:
                return header.decode(encoding)
            except:
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
            raise TypeError("invalid header: %s %s"%(header, header.__classs__))
    
    #
    # Parses a string and removes duplicate and trailing spaces/tabs/newlines
    #
    def parse_string_flat(self, header):
        value = self.parse_string(header)
        return re.sub("\s\s+", " ", value.strip().lower())
    
    #
    # Removes realnames out of email addresses headers, it then lowercases the
    # addresses and returns them sorted
    #
    def parse_emails(self, headers):
        addresses = set()
        for header in headers:
            (_, addr) = email.utils.parseaddr(self.parse_string_flat(header))
            if len(addr) > 0:
                addresses.add(addr.lower())
        return " ".join(sorted(addresses))
    
    #
    # Parses date headers fomatted as "yyyy-mm-dd"
    #
    def parse_date(self, header):
        try:
            return email.utils.parsedate_to_datetime(header).strftime("%Y-%m-%d")
        except:
            return ""
    
    #
    # Body line iterator, removes spaces/tabs/newlines and skips empty lines
    #
    def body(self):
        for line in email.iterators.body_line_iterator(self._eml):
            l = re.sub("\s", "", line)
            if len(l) > 0:
                yield l

#
# Used to print email processing progress
#
class Progress:
    def __init__(self, obj, name):
        self.name = name
        self.i = 0
        self.show("counting %s"%(self.name))
        self.total = len(obj)
    
    def show(self, *args, **kwargs):
        print(*args, file=sys.stderr, **kwargs)
    
    def next(self):
        self.i += 1
        self.show("processing %d/%d %s"%(self.i, self.total, self.name), end="\r")
    
    def end(self):
        self.show("")

class EmailDups:
    def __init__(self, path, keys, skip_at):
        self.mbox = mailbox.Maildir(path)
        self.keys = keys
        self.skip_at = skip_at
        self.dups = {}
    
    #
    # Main process
    #
    def calculate(self):
        dups = {}
        p = Progress(self.mbox, "emails")
        for id, eml in self.mbox.iteritems():
            p.next()
            emlhash = EmailParser.parse(eml, keys, id)
            fails = emlhash.fails()
            if fails >= self.skip_at:
                p.show("skipping email %s with %d fails"%(id, fails))
                continue
            xhash = emlhash.hash()
            if not xhash in dups:
                dups[xhash] = []
            dups[xhash].append(emlhash)
        p.end()
        
        #
        # removes non duplicate emails
        #
        for key in list(dups.keys()):
            if len(dups[key]) <= 1:
                dups.pop(key, None)
        
        self.dups = dups
        
        p.show("%d dupmails found"%(self.count()))
    
    def count(self):
        count = 0
        for dup in self.dups.values():
            count = count + len(dup)-1
        return count
    
    def print_result(self, format):
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

parser = argparse.ArgumentParser(description="find duplicate emails",
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("-s", "--skip-if", default=2, type=int,
                    help="skip emails if unable to parse at least SKIP_AT fields")
parser.add_argument("-f", "--format", default="plain", choices=["plain", "json"],
                    help="print results using this format")
parser.add_argument("-k", "--keys", nargs=1, default="from,to,date,subject,body_lines",
                    help="""
comma separated list of fields to identify duplicates, valid values are:

from: email address in From header
to: ordered email address list including To, CC and BCC headers
date: Date header formatted as yyyy-mm-dd, time is not included
subject: lowercase, space removed Subject header
body_lines: the number of non empty lines in the body, including attachments
body_size: same as above but total byte size
body_hash: same as above but sha256 representation
""")
parser.add_argument("path", help="maildir path")
args = parser.parse_args()

keys = args.keys.split(",")
if not keys:
    parser.error("invalid number of KEYS")

for key in keys:
    if key not in EmailParser.valid_keys():
        parser.error("invalid KEY: %s"%(key))

emaildups = EmailDups(args.path, keys, args.skip_if)
emaildups.calculate()
emaildups.print_result(args.format)
