#!/usr/bin/env python3
"""Redact identifiers in these journal captures without filtering their lines."""
import argparse
from pathlib import Path
import re


def sanitize(source):
    hosts = set(re.findall(r'^\[[^\n\]]+\] (\S+) ', source, re.MULTILINE))
    for host in hosts:
        source = re.sub(r'(?<![\w.-])' + re.escape(host) + r'(?![\w.-])', '<host>', source)
    patterns = (
        (r'\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b', '<uuid>'),
        (r'(?<=by-uuid/)[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}\b', '<volume-id>'),
        (r'\b[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}\b', '<mac>'),
        (r'(SerialNumber: )\S+', r'\1<serial>'),
        (r'/home/[^/\s]+', '/home/<user>'),
        (r'(Zombie\?\s*:\s*[01]\s+)[0-9a-fA-F]{16}\b', r'\1<pointer>'),
    )
    for pattern, replacement in patterns:
        source = re.sub(pattern, replacement, source)
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error('input and output must differ')
    source = args.input.read_text()
    cleaned = sanitize(source)
    assert len(source.splitlines()) == len(cleaned.splitlines())
    assert re.findall(r'^\[[^\n\]]+\]', source, re.MULTILINE) == re.findall(
        r'^\[[^\n\]]+\]', cleaned, re.MULTILINE)
    args.output.write_text(cleaned)


if __name__ == '__main__':
    main()
