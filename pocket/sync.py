#!/usr/bin/env python3
"""Copy event pages to a compatible Pocket node; verify every durable receipt."""
import argparse
import json
from pathlib import Path
import urllib.parse
import urllib.request
from server import canonical, sha, SCHEMA


def request(base, token, route, body=None):
    parsed = urllib.parse.urlsplit(base)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise ValueError('use an origin URL without credentials, path, query, or fragment')
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')):
        raise ValueError('remote sync requires HTTPS')
    req = urllib.request.Request(base.rstrip('/') + route, data=canonical(body) if body is not None else None,
          headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    # Never follow an authenticated redirect to a different origin.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_): return None
    with urllib.request.build_opener(NoRedirect).open(req, timeout=20) as response:
        return json.loads(response.read(3_000_000))


def sync(source, target, source_token, target_token):
    cursor = 0; count = 0; pages = 0
    source_node = request(source, source_token, '/api/status')['node_id']
    target_node = request(target, target_token, '/api/status')['node_id']
    if source_node == target_node:
        raise ValueError('source and target identify the same node')
    while True:
        page = request(source, source_token, '/api/sync/export?after=' + str(cursor))
        if page['schema'] != SCHEMA or page['source_node'] != source_node or page['after'] != cursor:
            raise ValueError('source changed or cursor mismatch')
        receipt = request(target, target_token, '/api/sync/import', page)
        if receipt['receiver_node'] != target_node or receipt['source_node'] != source_node or receipt['source_cursor'] != page['cursor'] or receipt['bundle_sha256'] != sha(canonical(page)) or receipt['event_ids'] != [e['event_id'] for e in page['events']]:
            raise ValueError('receipt mismatch; cursor not advanced')
        cursor = page['cursor']; count += len(page['events']); pages += 1
        if not page['has_more']:
            return {'status': 'VERIFIED', 'pages': pages, 'events_confirmed': count, 'source_node': source_node, 'target_node': target_node, 'cursor': cursor}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'target', 'source-token-file', 'target-token-file'): p.add_argument('--' + name, required=True)
    a = p.parse_args()
    try:
        print(json.dumps(sync(a.source, a.target, Path(a.source_token_file).read_text().strip(), Path(a.target_token_file).read_text().strip())))
    except Exception as error:
        # HTTP errors can contain sensitive URLs: report only the exception type.
        raise SystemExit('Sync unverified: ' + type(error).__name__)
