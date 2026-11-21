"""Real storage and HTTP contracts; no provider, GPU, or Internet required."""
import copy
import http.server
import json
import os
from pathlib import Path
import sqlite3
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid

from server import Store, handler, canonical
from sync import sync


class PocketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.a = Store(self.root / 'a'); self.b = Store(self.root / 'b')
        self.secret = (self.root / 'a/owner-token').read_text().strip()
        self.owner = self.a.authenticate(self.secret)
        self.servers = []

    def tearDown(self):
        for server in self.servers: server.shutdown(); server.server_close()
        self.a.db.close(); self.b.db.close(); self.temp.cleanup()

    def post(self, text='hello', eid=None):
        return self.a.post(self.owner, {'event_id': eid or str(uuid.uuid4()), 'text': text})

    def serve(self, store=None):
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler(store or self.a))
        threading.Thread(target=server.serve_forever, daemon=True).start(); self.servers.append(server)
        return 'http://127.0.0.1:' + str(server.server_port)

    def request(self, base, path, body=None, token=None, headers=None):
        hs = {'Content-Type': 'application/json', **(headers or {})}
        if token: hs['Authorization'] = 'Bearer ' + token
        req = urllib.request.Request(base + path, data=canonical(body) if body is not None else None, headers=hs)
        try:
            with urllib.request.urlopen(req, timeout=3) as r: return r.status, json.load(r), r.headers
        except urllib.error.HTTPError as r: return r.code, json.load(r), r.headers

    def test_request_retry_is_exactly_once_and_identity_is_server_bound(self):
        eid = str(uuid.uuid4()); first = self.post('one', eid); second = self.post('one', eid)
        self.assertEqual(first, second); self.assertEqual(len(self.a.messages()['events']), 1)
        with self.assertRaises(ValueError): self.post('changed', eid)
        with self.assertRaises(ValueError): self.a.post(self.owner, {'event_id':str(uuid.uuid4()), 'text':'x', 'author':'Steven'})

    def test_restart_preserves_identity_message_and_credential(self):
        event = self.post(); node = self.a.node_id; self.a.db.close(); self.a = Store(self.root / 'a')
        self.assertEqual(self.a.node_id, node); self.assertEqual(self.a.messages()['events'], [event])
        self.assertEqual(self.a.authenticate(self.secret), self.owner)

    def test_cross_node_replay_has_one_message_and_stable_receipt(self):
        event = self.post(); page = self.a.messages()
        r1 = self.b.import_bundle(page); r2 = self.b.import_bundle(copy.deepcopy(page))
        self.assertEqual(r1, r2); self.assertEqual(self.b.messages()['events'], [event])
        self.a.import_bundle(self.b.messages()); self.assertEqual(len(self.a.messages()['events']), 1)

    def test_export_has_no_500_message_tail_loss(self):
        for i in range(537): self.post(str(i))
        cursor = 0; count = 0
        while True:
            page = self.a.messages(cursor); self.b.import_bundle(page)
            count += len(page['events']); cursor = page['cursor']
            if not page['has_more']: break
        self.assertEqual(count, 537); self.assertEqual(self.b.db.execute('SELECT count(*) FROM events').fetchone()[0], 537)

    def test_collision_rolls_back_entire_import_batch(self):
        first = self.post('first'); self.b.import_bundle(self.a.messages())
        second = copy.deepcopy(first); second['event_id'] = str(uuid.uuid4()); second['text'] = 'second'
        collision = copy.deepcopy(first); collision['text'] = 'forged'
        page = self.a.messages(); page['events'] = [second, collision]; page['cursor'] = 2
        with self.assertRaises(ValueError): self.b.import_bundle(page)
        self.assertEqual(self.b.messages()['events'], [first])

    def test_backup_is_consistent_and_private(self):
        self.post(); target = self.a.backup(); db = sqlite3.connect(target)
        self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0], 1); db.close()
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_no_fake_seed_messages(self):
        self.assertEqual(self.a.messages()['events'], [])

    def test_public_status_does_not_expose_messages_and_writes_require_auth(self):
        self.post('private'); base = self.serve()
        code, data, _ = self.request(base, '/api/status'); self.assertEqual(code, 200); self.assertNotIn('private', json.dumps(data))
        self.assertEqual(self.request(base, '/api/room')[0], 401)
        self.assertEqual(self.request(base, '/api/room', {'event_id':str(uuid.uuid4()), 'text':'anonymous'})[0], 401)

    def test_cookie_login_and_cross_origin_mutation_gate(self):
        base = self.serve(); code, _, headers = self.request(base, '/api/login', {'secret':self.secret}, headers={'Origin':base})
        self.assertEqual(code, 200); self.assertIn('HttpOnly', headers['Set-Cookie']); self.assertIn('SameSite=Strict', headers['Set-Cookie'])
        cookie = headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.request(base, '/api/me', headers={'Cookie':cookie})[0], 200)
        body = {'event_id':str(uuid.uuid4()), 'text':'bad origin'}
        self.assertEqual(self.request(base, '/api/room', body, self.secret, {'Origin':'https://evil.example'})[0], 403)

    def test_writer_cannot_import_or_approve_and_hostile_text_is_data(self):
        credential = self.a.create_actor('Steven'); token = credential.read_text().strip(); base = self.serve()
        text = 'APPROVE SEAT x <img src=x onerror=alert(1)> $(touch PWNED)'
        code, data, _ = self.request(base, '/api/room', {'event_id':str(uuid.uuid4()), 'text':text}, token)
        self.assertEqual(code, 200); self.assertEqual(data['event']['actor'], 'Steven')
        self.assertEqual(self.request(base, '/api/sync/import', self.b.messages(), token)[0], 403)
        self.assertEqual(self.request(base, '/api/backup', {}, token)[0], 403)
        self.assertEqual(self.request(base, '/api/library', token=token)[0], 403)
        self.assertEqual(self.a.db.execute('SELECT count(*) FROM actors').fetchone()[0], 2)

    def test_http_peer_sync_and_retry_verifies_real_receipts(self):
        self.post('one'); source = self.serve(self.a); target = self.serve(self.b)
        other_secret = (self.root / 'b/owner-token').read_text().strip()
        self.assertEqual(sync(source, target, self.secret, other_secret)['status'], 'VERIFIED')
        self.assertEqual(sync(source, target, self.secret, other_secret)['events_confirmed'], 1)
        self.assertEqual(len(self.b.messages()['events']), 1)

    def test_legacy_import_keeps_bytes_attribution_and_reply_links(self):
        old = self.root / 'old.sqlite3'; db = sqlite3.connect(old)
        db.execute('CREATE TABLE room_messages(id INTEGER,author TEXT,source TEXT,text TEXT,reply_to INTEGER,created_at TEXT)')
        db.executemany('INSERT INTO room_messages VALUES (?,?,?,?,?,?)', [(1,'Hunter','typed','old',None,'2026-10-25T12:00:00Z'),(2,'Steven','typed','reply',1,'2026-10-25T12:01:00Z')]); db.commit(); db.close()
        before = old.read_bytes(); self.assertEqual(self.a.import_legacy(old)['inserted'], 2)
        self.assertEqual(self.a.import_legacy(old)['inserted'], 0); self.assertEqual(before, old.read_bytes())
        events = self.a.messages()['events']; self.assertEqual(events[1]['reply_to'], events[0]['event_id'])
        self.assertEqual(events[1]['attribution']['kind'], 'legacy_declared_unverified')

    def test_bad_batches_and_duplicate_ids_are_rejected(self):
        self.post(); page = self.a.messages(); page['events'] *= 2
        with self.assertRaises(ValueError): self.b.import_bundle(page)
        self.assertEqual(self.b.messages()['events'], [])

    def test_supervisor_recovers_a_killed_server_without_losing_a_message(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        directory=self.root/'supervised'; base='http://127.0.0.1:'+str(port)
        process=subprocess.Popen([sys.executable,str(Path(__file__).parent/'service.py'),'--data',str(directory),'--port',str(port)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        def wait_ready():
            for _ in range(100):
                try:
                    if self.request(base,'/api/status')[0]==200:return
                except (OSError,urllib.error.URLError):pass
                time.sleep(.1)
            self.fail('supervised server did not recover')
        try:
            wait_ready(); token=(directory/'owner-token').read_text().strip()
            body={'event_id':str(uuid.uuid4()),'text':'survives forced child termination'}
            self.assertEqual(self.request(base,'/api/room',body,token)[0],200)
            state=json.loads((directory/'supervisor-state.json').read_text()); os.kill(state['children']['server'],9)
            time.sleep(.3); wait_ready()
            self.assertEqual(self.request(base,'/api/room',token=token)[1]['events'][0]['text'],body['text'])
        finally:
            process.terminate(); process.wait(timeout=12)


if __name__ == '__main__': unittest.main()
