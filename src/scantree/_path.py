from __future__ import print_function, division

import os

from pathlib import Path

import attr

from .compat import DirEntry, fspath, scandir


@attr.s(slots=True)
class RecursionPath(object):
    root = attr.ib()
    relative = attr.ib()
    real = attr.ib()
    _dir_entry = attr.ib(cmp=False)
    """Track the recursion path.

    So why not use pathlib.Path:
    - keep track of real path but only do fs check on follow link
    - use scandir/DirEntry's caching of e.g. is_dir/is_file for speedup.
    """
    @classmethod
    def from_root(cls, directory):
        if isinstance(directory, (DirEntry, DirEntryReplacement)):
            dir_entry = directory
        else:
            dir_entry = DirEntryReplacement.from_path(directory)
        return cls(
            root=dir_entry.path,
            relative='',
            real=os.path.realpath(dir_entry.path),
            dir_entry=dir_entry
        )

    def scandir(self):
        return (self._join(dir_entry) for dir_entry in scandir(self.absolute))

    def _join(self, dir_entry):
        relative = os.path.join(self.relative, dir_entry.name)
        real = os.path.join(self.real, dir_entry.name)
        if dir_entry.is_symlink():
            real = os.path.realpath(real)

        return attr.evolve(self, relative=relative, real=real, dir_entry=dir_entry)

    @property
    def absolute(self):
        return os.path.join(self.root, self.relative)

    @property
    def path(self):
        return self._dir_entry.path

    @property
    def name(self):
        return self._dir_entry.name

    def is_dir(self, follow_symlinks=True):
        return self._dir_entry.is_dir(follow_symlinks=follow_symlinks)

    def is_file(self, follow_symlinks=True):
        return self._dir_entry.is_file(follow_symlinks=follow_symlinks)

    def is_symlink(self):
        return self._dir_entry.is_symlink()

    def stat(self, follow_symlinks=True):
        return self._dir_entry.stat(follow_symlinks=follow_symlinks)

    def inode(self):
        return self._dir_entry.inode()

    def __fspath__(self):
        return self.absolute

    def as_pathlib(self):
        return Path(self.absolute)

    @staticmethod
    def _getstate(self):
        return (
            self.root,
            self.relative,
            self.real,
            DirEntryReplacement.from_dir_entry(self._dir_entry)
        )

    @staticmethod
    def _setstate(self, state):
        self.root, self.relative, self.real, self._dir_entry = state


# Attrs overrides __get/setstate__ for slotted classes, see:
# https://github.com/python-attrs/attrs/issues/512
RecursionPath.__getstate__ = RecursionPath._getstate
RecursionPath.__setstate__ = RecursionPath._setstate


@attr.s(slots=True, cmp=False)
class DirEntryReplacement(object):
    path = attr.ib(converter=fspath)
    name = attr.ib()
    _is_dir = attr.ib(init=False, default=None)
    _is_file = attr.ib(init=False, default=None)
    _is_symlink = attr.ib(init=False, default=None)
    _stat_sym = attr.ib(init=False, default=None)
    _stat_nosym = attr.ib(init=False, default=None)

    @classmethod
    def from_path(cls, path):
        path = fspath(path)
        if not os.path.exists(path):
            raise IOError('{} does not exist'.format(path))
        basename = os.path.basename(path)
        if basename in ['', '.', '..']:
            name = os.path.basename(os.path.realpath(path))
        else:
            name = basename
        return cls(path, name)

    @classmethod
    def from_dir_entry(cls, dir_entry):
        return cls(dir_entry.path, dir_entry.name)

    def is_dir(self, follow_symlinks=True):
        if self._is_dir is None:
            self._is_dir = os.path.isdir(self.path)
        if follow_symlinks:
            return self._is_dir
        else:
            return self._is_dir and not self.is_symlink()

    def is_file(self, follow_symlinks=True):
        if self._is_file is None:
            self._is_file = os.path.isfile(self.path)
        if follow_symlinks:
            return self._is_file
        else:
            return self._is_file and not self.is_symlink()

    def is_symlink(self):
        if self._is_symlink is None:
            self._is_symlink = os.path.islink(self.path)
        return self._is_symlink

    def stat(self, follow_symlinks=True):
        if follow_symlinks:
            if self._stat_sym is None:
                self._stat_sym = os.stat(self.path)
            return self._stat_sym

        if self._stat_nosym is None:
            self._stat_nosym = os.lstat(self.path)
        return self._stat_nosym

    def inode(self):
        return self.stat(follow_symlinks=False).st_ino

    def __eq__(self, other):
        if not isinstance(other, (DirEntryReplacement, DirEntry)):
            return False
        if not self.path == other.path:
            return False
        if not self.name == other.name:
            return False
        for method, kwargs in [
            ('is_dir', {'follow_symlinks': True}),
            ('is_dir', {'follow_symlinks': False}),
            ('is_file', {'follow_symlinks': True}),
            ('is_file', {'follow_symlinks': False}),
            ('is_symlink', {}),
            ('stat', {'follow_symlinks': True}),
            ('stat', {'follow_symlinks': False}),
            ('inode', {})
        ]:
            this_res = getattr(self, method)(**kwargs)
            other_res = getattr(other, method)(**kwargs)
            if not this_res == other_res:
                return False

        return True