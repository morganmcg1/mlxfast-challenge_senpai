#!/usr/bin/env python3
"""Classify a two-revision file diff as comment/whitespace-only vs real code.

Strips C/C++/Swift line and block comments (string- and char-literal aware,
including Swift raw strings) plus blank lines, then compares.
"""
import subprocess
import sys


def strip(text: str) -> str:
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            # count preceding '#' for raw strings
            j = i - 1
            hashes = 0
            while j >= 0 and text[j] == '#':
                hashes += 1
                j -= 1
            if hashes:
                out.append(text[i])
                i += 1
                closer = '"' + '#' * hashes
                k = text.find(closer, i)
                if k < 0:
                    out.append(text[i:])
                    break
                out.append(text[i:k + len(closer)])
                i = k + len(closer)
                continue
            out.append(c)
            i += 1
            while i < n:
                if text[i] == '\\':
                    out.append(text[i:i + 2])
                    i += 2
                    continue
                out.append(text[i])
                if text[i] == '"' or text[i] == '\n':
                    i += 1
                    break
                i += 1
            continue
        if c == "'" :
            out.append(c)
            i += 1
            while i < n:
                if text[i] == '\\':
                    out.append(text[i:i + 2])
                    i += 2
                    continue
                out.append(text[i])
                if text[i] == "'" or text[i] == '\n':
                    i += 1
                    break
                i += 1
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            k = text.find('\n', i)
            i = n if k < 0 else k
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '*':
            k = text.find('*/', i + 2)
            i = n if k < 0 else k + 2
            out.append(' ')
            continue
        out.append(c)
        i += 1
    lines = [ln.rstrip() for ln in ''.join(out).split('\n')]
    return '\n'.join(ln for ln in lines if ln.strip())


def blob(rev: str, path: str) -> str:
    r = subprocess.run(['git', 'show', f'{rev}:{path}'], capture_output=True)
    if r.returncode != 0:
        return ''
    return r.stdout.decode('utf-8', 'replace')


def main() -> int:
    old, new = sys.argv[1], sys.argv[2]
    paths = sys.argv[3:]
    if not paths:
        out = subprocess.run(
            ['git', 'diff', '--name-only', old, new, '--',
             'Sources', 'Vendor', 'Package.swift', 'benchmark.json'],
            capture_output=True, text=True, check=True).stdout
        paths = [p for p in out.split('\n') if p]
    same, diff = [], []
    for p in paths:
        a, b = strip(blob(old, p)), strip(blob(new, p))
        (same if a == b else diff).append(p)
    print('== comment/whitespace-only (semantically identical) ==')
    for p in same:
        print('  SAME  ' + p)
    print('== real code difference ==')
    for p in diff:
        print('  DIFF  ' + p)
    print(f'\ntotals: same={len(same)} diff={len(diff)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
