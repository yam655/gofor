#!/usr/bin/env python3

import asyncio
from pathlib import Path
import argparse
import os
import stat

Version = '0.0.5'

parser = argparse.ArgumentParser(prog='gofor', 
        description='gofor: simple gopher server')
parser.add_argument('--fqdn', '-f', default='localhost',
        help='Fully qualified domain name clients should use.')
parser.add_argument('--port', '-p', default=70, type=int,
        help='The port to listen to.')
parser.add_argument('--root', '-r', default=Path('/var/gopher'), type=Path,
        help='The document root to serve from.')
parser.add_argument('--ipv4', '-4', action='store_true',
        help='Bind to 0.0.0.0 instead of ::')
parser.add_argument('--verbose', '-v', action='store_true',
        help='Be more verbose.')
parser.add_argument('--version', action='version', version='%(prog)s ' + Version)
parser.add_argument('--chroot', action='store_true',
        help='chroot in to the document root')


class GopherProtocol(asyncio.Protocol):
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.root = self.args.root.resolve()

    def connection_made(self, transport):
        self.transport = transport

    def invalid_path(self, philly, selector):
        if not self.args.chroot:
            try:
                if philly != self.root:
                    philly.relative_to(self.root)
            except:
                if self.args.verbose:
                    print('Error: attempt to access bad region: {}'.format(selector))
                return True
        elif '..' in selector:
            if self.args.verbose:
                print('Error: attempt to access parent in chroot: {}'.format(selector))
            return True
        gmap = philly / 'gophermap'
        if not philly.exists() or philly.is_symlink() or not (stat.S_IMODE(philly.lstat().st_mode) & stat.S_IROTH):
            if self.args.verbose:
                print('Error: attempt to access nonpublic path: {}'.format(selector))
            return True
        elif philly.is_file():
            return False
        elif (philly.is_dir() and gmap.exists() and gmap.is_file() and
                stat.S_IMODE(philly.lstat().st_mode) & stat.S_IROTH):
            return False
        if self.args.verbose:
            print('Error: attempt to access something weird: {}'.format(selector))
        return True

    def data_received(self, data):
        selector = data.decode().strip()
        if '\t' in selector:
            if self.args.verbose:
                print('Possible Gopher+ selector: {}'.format(selector))
            self.transport.write('3Gopher+ selectors unsupported {}.\t\terror.host\t1'.format(selector).encode('US-ASCII', 'replace'))
            self.transport.write('\r\n.\r\n'.encode('US-ASCII', 'replace'))
            self.transport.close()

        if self.args.verbose:
            print('Request:'.format(selector))
        if selector:
            if not selector.startswith('/'):
                selector = '/' + selector
            relative = selector[1:]
        else:
            relative = ""
        if not self.args.chroot:
            philly = Path(self.root, relative).resolve()
        else:
            philly = Path(selector).resolve()

        if self.invalid_path(philly, selector):
            if self.args.verbose:
                print('Error result: {}'.format(selector))
            self.transport.write('3Error accessing {}.\t\terror.host\t1'.format(selector).encode('US-ASCII', 'replace'))
            self.transport.write('\r\n.\r\n'.encode('US-ASCII', 'replace'))
            self.transport.close()

        elif philly.is_file():
            if self.args.verbose:
                print('Success: file: {}'.format(selector))
            block_size = 64 * 1024
            with philly.open('rb') as inf:
                data = inf.read(block_size)
                while len(data) > 0:
                    self.transport.write(data)
                    data = inf.read(block_size)
        else:
            gmap = philly / 'gophermap'
            if self.args.verbose:
                print('Success: directory with gophermap: {}.'.format(selector))
            txt = str(gmap.read_text()).splitlines()
            outln = []
            for line in txt:
                if line:
                    cols = line.split('\t')
                else:
                    cols = ['i', '/', '-', '0']
                if len(cols) == 1:
                    cols = ['i'+line, '/', '-', '0']
                elif len(cols) == 2:
                    cols.append(self.args.fqdn)
                    cols.append(str(self.args.port))
                elif len(cols) == 3:
                    cols.append('70')
                elif len(cols) > 4:
                    cols = cols[:4]
                if cols[0][0] == 'h' and cols[1].startswith('URL:'):
                    cols[1] = '/' + cols[1]
                if cols[1] and cols[1][0] != '/':
                    if self.args.fqdn == cols[2]:
                        cols[1] = '{}/{}'.format(selector, cols[1])
                    else:
                        cols[1] = '/' + cols[1]
                outln.append('\t'.join(cols))
            self.transport.write('\r\n'.join(outln).encode('US-ASCII', 'xmlcharrefreplace'))
            self.transport.write('\r\n.\r\n'.encode('US-ASCII', 'replace'))

        self.transport.close()

async def main():
    args = parser.parse_args()
    loop = asyncio.get_running_loop()
    addr = '::'
    if args.chroot:
        root = args.root.resolve()
        os.chdir(root)
        os.chroot(root)
    if args.ipv4:
        addr = '0.0.0.0'
    server = await loop.create_server(
        lambda: GopherProtocol(args), addr, args.port)
    async with server:
        await server.serve_forever()

asyncio.run(main())

