#!/usr/bin/env python3
"""remtool.py

Usage:
  remtool.py ls [PATH]
  remtool.py put FILE [FOLDER]
  remtool.py show PATH
  remtool.py (-h | --help)
  remtool.py --version

Options:
  -h --help     Show this screen.
  --version     Show version.
"""
import configparser
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections import deque
from dataclasses import dataclass
from docopt_ng import docopt
from glob import glob
from pathlib import Path, PurePath
from time import time

import pprint
pp_ = pprint.PrettyPrinter(indent=2)
pp = pp_.pprint

SCRIPTPATH = os.path.dirname(os.path.realpath(__file__))

# read config file
config = configparser.ConfigParser()
config.read(f"{SCRIPTPATH}/remtool.cfg")
CONFIG = {}
CONFIG['SSH_HOSTNAME'] = config['main']['reMarkableHostname']


class reMarkable:
    def __init__(self, hostname: str):
        self.hostname = hostname

        # get content tree and metadata from reMarkable
        self.ct = ContentTree(self._get_metadata())

    def put(self, file: str, folder: str=''):
        # assemble params into a target path
        filename = Path(file)
        folderpath = Path(folder)
        path = folderpath / filename.stem

        # check if destination folder exists
        parent = self.ct.get_node_by_path(folder)
        if parent is None:
            print(f"Folder '{folder}' does not exist.")
            return

        # check if file already exists at this target path
        target = self.ct.get_node_by_path(path)
        if target is None:
            now = str(int(time()*1000))
            new_meta = Metadata(deleted=False,
                                last_modified=now,
                                last_opened=now,
                                last_opened_page=0,
                                metadata_modified=False,
                                modified=False,
                                parent=parent.uuid,
                                pinned=False,
                                synced=False,
                                type_='DocumentType',
                                version=0,
                                visible_name=filename.stem)
            new_node = Node(uuid.uuid4(), new_meta)
            parent.add_child(new_node)

            # render node as files on disk and send them to the device
            with tempfile.TemporaryDirectory(prefix='remtool_') as tempdir:
                new_node.render_to_disk(tempdir)
                shutil.copy(filename,
                            f"{tempdir}/{new_node.uuid}{filename.suffix}")
                rendered = glob(f"{tempdir}/*")
                self._scp(rendered, '.local/share/remarkable/xochitl')
                self._ssh('systemctl restart xochitl')
            print(f"{filename} sent to reMarkable.")

    def show(self, path: str):
        target = self.ct.get_node_by_path(path)
        if target is None:
            print(f"Path '{path}' not found.")
            return

        print('path:', target.path)
        print('uuid:', target.uuid)
        print()
        print('metadata:')
        print(target.metadata)

    def ls(self, path: str=None):
        if path is None:
            path = ''

        target = self.ct.get_node_by_path(path)
        if target is None:
            print(f"Path '{path}' not found.")
            return

        if not target.is_folder():
            print(f"Path '{path}' is not a folder.")
            return

        for child in target.children:
            print(child.path)

    def _ssh(self, cmd: str, pipe_in: bool=False):
        args = ['ssh', f"root@{self.hostname}"]
        if pipe_in:
            args.insert(1, '-T')  # disable pseudo-terminal allocation
        else:
            args.append(cmd)

        if pipe_in:
            sp = subprocess.Popen(args,
                                  stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  encoding='utf-8')
            result, err = sp.communicate(cmd)
            if sp.returncode > 0:
                print(f"ERROR: {err.strip()}")
                sys.exit(1)
        else:
            try:
                out = subprocess.run(args, capture_output=True, check=True,
                                     encoding='utf-8')
                result = out.stdout
            except subprocess.CalledProcessError as e:
                print(f"ERROR: {e}")
                sys.exit(1)
        return result

    def _scp(self, source: list, dest: str):
        args = ['scp', '-r']
        args.extend(source)
        args.append(f"root@{self.hostname}:{dest}")

        try:
            subprocess.run(args, capture_output=True, check=True,
                           encoding='utf-8')
        except subprocess.CalledProcessError as e:
            print(f"ERROR: {e}")
            sys.exit(1)
        return True

    def _get_metadata(self):
        cmd = '''
shopt -s nullglob
metafiles=(.local/share/remarkable/xochitl/*.metadata)
numfiles=${#metafiles[@]}

filecount=1
echo '['
for file in ${metafiles[@]}
do
    echo '{"filename": "'$file'", "metadata": '
    cat $file
    echo '}'
    if [[ $filecount -lt $numfiles ]]; then
        echo ','
    fi
    filecount=$(($filecount + 1))
done
echo ']'
        '''.strip()
        raw_meta = self._ssh(cmd, pipe_in=True)
        json_meta = json.loads(raw_meta)
        return json_meta


@dataclass
class Metadata:
    deleted: bool
    last_modified: str
    last_opened: str
    last_opened_page: int
    metadata_modified: bool
    modified: bool
    parent: str
    pinned: bool
    synced: bool
    type_: str
    version: int
    visible_name: str

    def as_dict(self):
        out = {}
        for f_ in Metadata.__dataclass_fields__:
            if f_ == 'type_':
                field = 'type'
            elif f_ == 'visible_name':
                field = 'visibleName'
            elif f_ == 'metadata_modified':
                field = 'metadatamodified'
            elif f_ == 'last_modified':
                field = 'lastModified'
            elif f_ == 'last_opened':
                field = 'lastOpened'
            elif f_ == 'last_opened_page':
                field = 'lastOpenedPage'
            else:
                field = f_
            out[field] = getattr(self, f_)
        return out

    def __str__(self):
        """ Convert metadata into a human-readable string """
        width = max([len(fname) for fname in Metadata.__dataclass_fields__])+1
        out = ''
        for f_ in Metadata.__dataclass_fields__:
            if f_ == 'type_':
                field = 'type'
            else:
                field = f_
            out += f"{field.ljust(width)}: {getattr(self, f_)}\n"
        return out.strip()


class Node:
    def __init__(self, uuid: str, metadata: Metadata=None, children: list=None):
        self.uuid = uuid
        self.metadata = metadata
        self.path = ''
        if children is None:
            self.children = []

    def add_child(self, node):
        if self.metadata is None:
            if node.is_folder():
                node.path = f"{node.metadata.visible_name}/"
            else:
                node.path = f"{node.metadata.visible_name}"
        else:
            node.path = f"{self.path}{node.metadata.visible_name}"
        self.children.append(node)

    def is_folder(self):
        if self.metadata is None:
            return True
        else:
            return self.metadata.type_ == 'CollectionType'

    def render_to_disk(self, tempdir):
        filestem = f"{tempdir}/{self.uuid}"
        metafile = f"{filestem}.metadata"
        contentfile = f"{filestem}.content"

        with open(f"{metafile}", 'w') as METAFILE:
            json.dump(self.metadata.as_dict(), METAFILE, indent=4)

        with open(f"{contentfile}", 'w') as CONTENTFILE:
            json.dump({}, CONTENTFILE, indent=4)

        if not self.is_folder():
            os.makedirs(f"{filestem}")
            os.makedirs(f"{filestem}.thumbnails")

    def __repr__(self):
        if self.uuid == '':
            uuid = 'root'
        else:
            uuid = self.uuid
        out = f"Node(path={self.path} uuid={uuid}) ["
        if self.children:
            out += '\n'
        for child in self.children:
            out += f"  {child.path}\n"
        out += ']'
        return out


class ContentTree:
    def __init__(self, metadata: str):
        self.tree = Node(uuid='')
        self._build_tree(metadata)

    def get_node_by_uuid(self, uuid: str, root_node: Node=None):
        if root_node is None:
            root_node = self.tree

        if root_node.uuid == uuid:
            return root_node

        for node in root_node.children:
            result = self.get_node_by_uuid(uuid, node)
            if result is not None:
                return result

        return None

    def get_node_by_path(self, path: str, root_node: Node=None):
        if root_node is None:
            root_node = self.tree

        root_path = PurePath(root_node.path)
        ppath = PurePath(path)
        if str(root_path) == str(ppath):
            return root_node

        for node in root_node.children:
            result = self.get_node_by_path(path, node)
            if result is not None:
                return result

        return None

    def _build_tree(self, metadata):
        item_queue = deque(metadata)

        while item_queue:
            item = item_queue.popleft()

            if (item['metadata']['deleted']
                    or item['metadata']['parent'] == 'trash'):
                continue

            uuid = Path(item['filename']).stem
            if 'lastOpened' not in item['metadata']:
                item['metadata']['lastOpened'] = ''
            if 'lastOpenedPage' not in item['metadata']:
                item['metadata']['lastOpenedPage'] = 0
            meta = Metadata(item['metadata']['deleted'],
                            item['metadata']['lastModified'],
                            item['metadata']['lastOpened'],
                            item['metadata']['lastOpenedPage'],
                            item['metadata']['metadatamodified'],
                            item['metadata']['modified'],
                            item['metadata']['parent'],
                            item['metadata']['pinned'],
                            item['metadata']['synced'],
                            item['metadata']['type'],
                            item['metadata']['version'],
                            item['metadata']['visibleName'])

            if item['metadata']['parent'] == '':
                # item has no parent, i.e. it's on the root level
                self.tree.add_child(Node(uuid=uuid, metadata=meta))
            else:
                parent = self.get_node_by_uuid(item['metadata']['parent'])
                if parent is None:
                    # item _should_ have a parent, but we haven't seen it yet
                    # so, send the item back to the end of the queue
                    item_queue.append(item)
                else:
                    # item has a parent that we know about, so add it
                    parent.add_child(Node(uuid=uuid, metadata=meta))
        return


if __name__ == "__main__":
    args = docopt(__doc__, default_help=True, version='remtool 0.1')

    reM = reMarkable(CONFIG['SSH_HOSTNAME'])

    if args['put']:
        reM.put(args['FILE'], args['FOLDER'])
    elif args['ls']:
        reM.ls(args['PATH'])
    elif args['show']:
        reM.show(args['PATH'])
