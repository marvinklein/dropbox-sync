"""

Upload the contents of a directory to Dropbox.

This is adapted from an example app for API v2.
https://github.com/dropbox/dropbox-sdk-python/blob/master/example/updown.py

"""

from __future__ import print_function

import argparse
import contextlib
import datetime
import os
import six
import sys
import time
import unicodedata

if sys.version.startswith('2'):
	input = raw_input  # noqa: E501,F821; pylint: disable=redefined-builtin,undefined-variable,useless-suppression

import dropbox
from dropbox_content_hasher import DropboxContentHasher

parser = argparse.ArgumentParser(description='Sync a directory to Dropbox')
parserGroup = parser.add_mutually_exclusive_group()
parser.add_argument('source', help='The source directory to upload')
parser.add_argument('destination', help='The destination path in your Dropbox')
parser.add_argument('--token', '-t', help='Access token (see https://www.dropbox.com/developers/apps)', required=True)
parserGroup.add_argument('--yes', '-y', action='store_true',
					help='Answer yes to all questions')
parserGroup.add_argument('--no', '-n', action='store_true',
					help='Answer no to all questions')
parserGroup.add_argument('--default', '-d', action='store_true',
					help='Take default answer on all questions')

def main():
	"""Main program.

	Parse command line, then iterate over files and directories under
	rootdir and upload all files.  Skips some temporary files and
	directories, and avoids duplicate uploads by comparing size and
	mtime with the server.
	"""
	args = parser.parse_args()
	# if sum([bool(b) for b in (args.yes, args.no, args.default)]) > 1:
		# print('At most one of --yes, --no, --default is allowed')
		# sys.exit(2)

	directory = args.directory
	rootdir = os.path.expanduser(args.rootdir)
	print('Dropbox directory name:', directory)
	print('Local directory:', rootdir)
	if not os.path.exists(rootdir):
		print(rootdir, 'does not exist on your filesystem')
		sys.exit(1)
	elif not os.path.isdir(rootdir):
		print(rootdir, 'is not a directory on your filesystem')
		sys.exit(1)

	dbx = dropbox.Dropbox(args.token)

	for dn, dirs, files in os.walk(rootdir):
		subdirectory = dn[len(rootdir):].strip(os.path.sep)
		listing = list_directory(dbx, directory, subdirectory)
		print('Descending into', subdirectory, '...')

		# First do all the files.
		for name in files:
			fullname = os.path.join(dn, name)
			if not isinstance(name, six.text_type):
				name = name.decode('utf-8')
			nname = unicodedata.normalize('NFC', name)
			if name.startswith('.'):
				print('Skipping dot file:', name)
			elif name.startswith('@') or name.endswith('~'):
				print('Skipping temporary file:', name)
			elif name.endswith('.pyc') or name.endswith('.pyo'):
				print('Skipping generated file:', name)
			elif nname in listing:
				md = listing[nname]
				mtime = os.path.getmtime(fullname)
				mtime_dt = datetime.datetime(*time.gmtime(mtime)[:6])
				size = os.path.getsize(fullname)
				if (isinstance(md, dropbox.files.FileMetadata) and
						mtime_dt == md.client_modified and size == md.size):
					print(name, 'is already synced [stats match]')
				else:
					if not isinstance(md, dropbox.files.FileMetadata):
						print('couldn’t fetch metadata')
					if mtime_dt != md.client_modified:
						print(mtime_dt, md.client_modified, 'time mismatch')
					if size != md.size:
						print(size, md.size, 'size mismatch')
					db_hash = dropbox_hash(fullname)
					if db_hash != md.content_hash:
						print(name, 'hash is different, too')
						if yesno('Refresh %s' % name, False, args):
							upload(dbx, fullname, directory, subdirectory, name, overwrite=True)
					else:
						print(db_hash, 'hash matches. skipping.')
			elif yesno('Upload %s' % name, True, args):
				upload(dbx, fullname, directory, subdirectory, name)

		# Then choose which subdirectories to traverse.
		keep = []
		for name in dirs:
			if name.startswith('.'):
				print('Skipping dot directory:', name)
			elif name.startswith('@') or name.endswith('~'):
				print('Skipping temporary directory:', name)
			elif name == '__pycache__':
				print('Skipping generated directory:', name)
			elif yesno('Descend into %s' % name, True, args):
				print('Keeping directory:', name)
				keep.append(name)
			else:
				print('OK, skipping directory:', name)
		dirs[:] = keep

def list_directory(dbx, directory, subdirectory):
	"""List a directory.

	Return a dict mapping unicode filenames to
	FileMetadata|DirectoryMetadata entries.
	"""
	path = '/%s/%s' % (directory, subdirectory.replace(os.path.sep, '/'))
	while '//' in path:
		path = path.replace('//', '/')
	path = path.rstrip('/')
	try:
		with stopwatch('list_directory'):
			res = dbx.files_list_directory(path)
	except dropbox.exceptions.ApiError as err:
		print('Directory listing failed for', path, '-- assumed empty:', err)
		return {}
	else:
		rv = {}
		for entry in res.entries:
			rv[entry.name] = entry
		return rv

def download(dbx, directory, subdirectory, name):
	"""Download a file.

	Return the bytes of the file, or None if it doesn't exist.
	"""
	path = '/%s/%s/%s' % (directory, subdirectory.replace(os.path.sep, '/'), name)
	while '//' in path:
		path = path.replace('//', '/')
	with stopwatch('download'):
		try:
			md, res = dbx.files_download(path)
		except dropbox.exceptions.HttpError as err:
			print('*** HTTP error', err)
			return None
	data = res.content
	print(len(data), 'bytes; md:', md)
	return data

def upload(dbx, fullname, directory, subdirectory, name, overwrite=False):
	"""Upload a file.

	Return the request response, or None in case of error.
	"""
	path = '/%s/%s/%s' % (directory, subdirectory.replace(os.path.sep, '/'), name)
	while '//' in path:
		path = path.replace('//', '/')
	mode = (dropbox.files.WriteMode.overwrite
			if overwrite
			else dropbox.files.WriteMode.add)
	mtime = os.path.getmtime(fullname)
	with open(fullname, 'rb') as f:
		data = f.read()
	with stopwatch('upload %d bytes' % len(data)):
		try:
			res = dbx.files_upload(
				data, path, mode,
				client_modified=datetime.datetime(*time.gmtime(mtime)[:6]),
				mute=True)
		except dropbox.exceptions.ApiError as err:
			print('*** API error', err)
			return None
	print('uploaded as', res.name.encode('utf8'))
	return res

def yesno(message, default, args):
	"""Handy helper function to ask a yes/no question.

	Command line arguments --yes or --no force the answer;
	--default to force the default answer.

	Otherwise a blank line returns the default, and answering
	y/yes or n/no returns True or False.

	Retry on unrecognized answer.

	Special answers:
	- q or quit exits the program
	- p or pdb invokes the debugger
	"""
	if args.default:
		print(message + '? [auto]', 'Y' if default else 'N')
		return default
	if args.yes:
		print(message + '? [auto] YES')
		return True
	if args.no:
		print(message + '? [auto] NO')
		return False
	if default:
		message += '? [Y/n] '
	else:
		message += '? [N/y] '
	while True:
		answer = input(message).strip().lower()
		if not answer:
			return default
		if answer in ('y', 'yes'):
			return True
		if answer in ('n', 'no'):
			return False
		if answer in ('q', 'quit'):
			print('Exit')
			raise SystemExit(0)
		if answer in ('p', 'pdb'):
			import pdb
			pdb.set_trace()
		print('Please answer YES or NO.')

def dropbox_hash(fn):
	hasher = DropboxContentHasher()
	with open(fn, 'rb') as f:
		while True:
			chunk = f.read(1024)  # or whatever chunk size you want
			if len(chunk) == 0:
				break
			hasher.update(chunk)
	return hasher.hexdigest()

@contextlib.contextmanager
def stopwatch(message):
	"""Context manager to print how long a block of code took."""
	t0 = time.time()
	try:
		yield
	finally:
		t1 = time.time()
		print('Total elapsed time for %s: %.3f' % (message, t1 - t0))

if __name__ == '__main__':
	main()
