#!/usr/bin/env python3
"""Supervise the Pocket server and an optional authenticated public tunnel.

This supervises child exits while Termux itself remains alive. It cannot stop
Android killing Termux, a battery running out, or a carrier outage.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent


def ready(port):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/status', timeout=1) as response:
            return json.loads(response.read(2000)).get('schema') == 'xi.pocket.status.v1'
    except Exception:
        return False


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', type=Path, default=Path.home() / 'xi-phone-home/pocket-data')
    p.add_argument('--port', type=int, default=7474)
    p.add_argument('--tunnel', choices=('none', 'quick'), default='none')
    a = p.parse_args(); os.umask(0o077); a.data.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (a.data / 'service.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('Pocket supervisor already running; no second instance started')
    children = []; streams = {}; running = True
    def stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    commands = {'server': [sys.executable, str(HERE / 'server.py'), '--data', str(a.data), '--port', str(a.port)]}
    if a.tunnel == 'quick':
        commands['tunnel'] = ['cloudflared', 'tunnel', '--no-autoupdate', '--url', f'http://127.0.0.1:{a.port}']
    processes = {}; backoff = {name: 1 for name in commands}; next_start = {name: 0 for name in commands}; started = {}
    try:
        while running:
            for name, command in commands.items():
                proc = processes.get(name)
                if proc and proc.poll() is None:
                    if time.monotonic() - started[name] > 60:
                        backoff[name] = 1
                    continue
                if proc:
                    streams.pop(name).close(); children.remove(proc)
                    print(name + ' exited; restarting with backoff', flush=True)
                    processes[name] = None; next_start[name] = time.monotonic() + backoff[name]
                    backoff[name] = min(60, backoff[name] * 2)
                if time.monotonic() < next_start[name] or (name == 'tunnel' and not ready(a.port)):
                    continue
                path = a.data / (name + '.log')
                if path.exists() and path.stat().st_size > 2_000_000:
                    path.replace(a.data / (name + '.previous.log'))
                output = path.open('ab'); streams[name] = output
                try:
                    processes[name] = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
                    children.append(processes[name]); started[name] = time.monotonic()
                    state = a.data / 'supervisor-state.json'
                    staged_state = a.data / 'supervisor-state.tmp'
                    staged_state.write_text(json.dumps({'supervisor_pid':os.getpid(), 'children':{key:value.pid for key,value in processes.items() if value and value.poll() is None}}))
                    staged_state.replace(state)
                except OSError:
                    streams.pop(name).close()
                    next_start[name] = time.monotonic() + backoff[name]; backoff[name] = min(60, backoff[name] * 2)
                    print(name + ' could not start; see installed dependencies', flush=True)
            time.sleep(1)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
        for stream in streams.values(): stream.close()


if __name__ == '__main__': main()
