#!/usr/bin/env python3
"""Check a Thunderstore package ZIP, and upload it with Thunderstore's multipart, background-validated protocol (stdlib).

`check` verifies the layout Thunderstore needs: a root `manifest.json` (name,
version_number X.Y.Z, website_url, description of at most 250 characters,
dependencies), a root `README.md` and a 256x256 `icon.png`. It needs no network.
Northstar mods sit under `mods/<Author>.<Mod>/` (see the Northstar packaging guide).

`upload` follows thunderstore-io/Thunderstore's builder/src/api/packageSubmit.ts:
1. Initiate a user-media upload.
2. PUT each part to its presigned URL with Content-MD5 and collect the ETags.
3. Finish the upload, submit asynchronously, then poll until validation ends.

This avoids one long synchronous request; the official CLI's synchronous
finalize returned HTTP 500 for large map packages.

The service-account token comes from $TCLI_AUTH_TOKEN (or --token-env NAME) and
only goes to the fixed API origin, never to storage URLs, logs or errors. An
interrupted multipart upload is aborted. A version that already exists fails
on Thunderstore's side; it is never overwritten.

Copyright (c) 2026 taskinoz. MIT licence. From taskinoz/apex-to-titanfall-2
thunderstore_upload.py, which published its Northstar map packages
(400-720 MB each).

  python tools/thunderstore_upload.py check PACKAGE.zip
  python tools/thunderstore_upload.py upload PACKAGE.zip --namespace TEAM --community northstar
"""
import argparse
import base64
import hashlib
import json
import os
import re
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

BASE = 'https://thunderstore.io/api/experimental/'
USER_AGENT = 'ARES-thunderstore-upload/1.0 (+https://github.com/taskinoz/ARES)'
PART_LIMIT = 128 * 1024 * 1024


def check(path):
    """Problems with a package ZIP's layout (an empty list when it is publishable)."""
    problems = []
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        for required in ('manifest.json', 'README.md', 'icon.png'):
            if required not in names:
                problems.append(f'missing root {required}')
        if any(n.startswith('/') or '..' in Path(n).parts for n in names):
            problems.append('unsafe member path')
        if 'manifest.json' in names:
            try:
                m = json.loads(z.read('manifest.json').decode('utf-8-sig'))
            except ValueError:
                problems.append('manifest.json is not JSON')
                m = {}
            if not re.fullmatch(r'[A-Za-z0-9_]+', str(m.get('name', ''))):
                problems.append('manifest name must be letters, digits and underscores')
            if not re.fullmatch(r'\d+\.\d+\.\d+', str(m.get('version_number', ''))):
                problems.append('version_number must be X.Y.Z')
            if len(str(m.get('description', ''))) > 250:
                problems.append('description exceeds 250 characters')
            for key in ('website_url', 'dependencies'):
                if key not in m:
                    problems.append(f'manifest lacks {key}')
        if 'icon.png' in names:
            head = z.read('icon.png')[:24]
            if head[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>2I', head[16:24]) != (256, 256):
                problems.append('icon.png must be a 256x256 PNG')
    return problems


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api(path, token, data=None):
    if path.startswith('/') or '..' in path or '://' in path:
        raise ValueError('API path must be relative to the fixed Thunderstore origin')
    req = urllib.request.Request(BASE + path, data=None if data is None else json.dumps(data).encode(),
                                 headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                                          'User-Agent': USER_AGENT, 'Cache-Control': 'no-cache'})
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=120) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Thunderstore API {path.split("/")[0]} returned HTTP {e.code}') from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError('Thunderstore API connection failed; no credential or upload URL logged') from None


def upload_part(path, part):
    if urllib.parse.urlsplit(part['url']).scheme != 'https':
        raise ValueError('storage upload must use HTTPS')
    with Path(path).open('rb') as f:
        f.seek(part['offset'])
        content = f.read(part['length'])
    if len(content) != part['length']:
        raise ValueError('upload part exceeds file')
    md5 = base64.b64encode(hashlib.md5(content, usedforsecurity=False).digest()).decode()
    request = urllib.request.Request(part['url'], data=content, method='PUT',
                                     headers={'Content-MD5': md5, 'Content-Type': 'application/octet-stream',
                                              'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            etag = response.headers.get('ETag')
            if not etag:
                raise RuntimeError('storage did not return an upload part ETag')
            return {'ETag': etag, 'PartNumber': part['part_number']}
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError('storage part upload failed; signed URL withheld') from None  # it is a credential


def upload(path, namespace, token, community='northstar', categories=(), nsfw=False, timeout=1800):
    path = Path(path)
    data = api('usermedia/initiate-upload/', token, {'filename': path.name, 'file_size_bytes': path.stat().st_size})
    uuid = data['user_media']['uuid']
    parts = sorted(data['upload_urls'], key=lambda p: p['offset'])
    finished = False
    try:
        end = 0
        for p in parts:
            if p['offset'] != end or not 0 < p['length'] <= PART_LIMIT:
                raise ValueError('invalid or overlapping server part ranges')
            end += p['length']
        if end != path.stat().st_size:
            raise ValueError('server upload ranges do not cover the file')
        completed = []
        for part in parts:
            completed.append(upload_part(path, part))
            print(f'Uploaded {path.name}: part {len(completed)}/{len(parts)}', flush=True)
        api(f'usermedia/{uuid}/finish-upload/', token, {'parts': completed})
        finished = True
    finally:
        if not finished:
            try:
                api(f'usermedia/{uuid}/abort-upload/', token, {})
            except RuntimeError:
                pass
    submission = api('submission/submit-async/', token, {
        'upload_uuid': uuid, 'author_name': namespace, 'communities': [community],
        'community_categories': {community: list(categories)}, 'has_nsfw_content': nsfw})
    submission_id = submission['id']
    print('Background validation submitted:', path.name, submission_id, flush=True)
    deadline = time.monotonic() + timeout
    while submission['status'] != 'FINISHED':
        if time.monotonic() > deadline:
            raise RuntimeError('submission still pending; inspect this ID before retrying: ' + submission_id)
        time.sleep(5)
        submission = api(f'submission/poll-async/{submission_id}/?ci={time.time_ns()}', token)
    if submission.get('form_errors'):
        raise RuntimeError('Thunderstore validation failed: ' + json.dumps(submission['form_errors'])[:1500])
    if submission.get('task_error') or not submission.get('result'):
        raise RuntimeError('Thunderstore background task failed; submission ID: ' + submission_id)
    print('Published:', submission['result']['package_version']['download_url'], flush=True)
    return submission


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='command', required=True)
    c = sub.add_parser('check')
    c.add_argument('package')
    u = sub.add_parser('upload')
    u.add_argument('package')
    u.add_argument('--namespace', required=True, help='Thunderstore team that owns the package')
    u.add_argument('--community', default='northstar')
    u.add_argument('--category', action='append', default=[])
    u.add_argument('--nsfw', action='store_true')
    u.add_argument('--token-env', default='TCLI_AUTH_TOKEN', help='environment variable holding the service token')
    a = p.parse_args(argv)
    problems = check(a.package)
    if a.command == 'check' or problems:
        print(json.dumps({'package': a.package, 'problems': problems}, indent=2))
        return 1 if problems else 0
    token = os.environ.get(a.token_env)
    if not token:
        p.error(f'set {a.token_env} to a Thunderstore service-account token')
    upload(a.package, a.namespace, token, a.community, a.category, a.nsfw)
    return 0


if __name__ == '__main__':
    sys.exit(main())
