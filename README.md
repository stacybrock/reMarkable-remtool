# reMarkable-remtool

A simple CLI tool for transferring files to a reMarkable 2 or reMarkable Paper Pro tablet

## Requirements

- python 3.8+
- reMarkable 2 or reMarkable Paper Pro

**NOTE:** As of May 2025, this tool has been tested with python 3.11 and reMarkable 3.11.* through 3.19.*

**Developer Mode** and SSH must be enabled on the target device for this tool to work.

## Configuration

Copy `remtool.cfg-dist` to `remtool.cfg` and edit.

|Config Option|Purpose|
-|-
`reMarkableHostname`|IP, hostname, or SSH alias of reMarkable device

## Usage

```
remtool.py

Usage:
  remtool.py ls [PATH]
  remtool.py put [-f] [-c | --clear] FILE ... [FOLDER]
  remtool.py show PATH
  remtool.py (-h | --help)
  remtool.py --version

Options:
  -f            Force overwrite if file already exists
  -c --clear    If forcing overwrite, clear annotations on files
  -h --help     Show this screen
  --version     Show version
```
