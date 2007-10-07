#!/usr/bin/env python

# dirscan.py, version 1.1

import os
import re
import sys
import cPickle
import subprocess
import logging as l

from copy import deepcopy
from datetime import datetime
from getopt import getopt, GetoptError

from stat import ST_ATIME, ST_MTIME, ST_MODE, S_ISDIR
from os.path import (join, expanduser, dirname, basename,
                     exists, lexists, isfile, isdir)

rightNow = datetime.now()

class InvalidArgumentException(Exception): pass


# Use my osxtags.py module to interface with metadata tags on OS/X.

try:
    import osxtags
except:
    osxtags = None


def delfile(path):
    if lexists(path):
        os.remove(path)

def deltree(path):
    if not lexists(path): return
    for root, dirs, files in os.walk(path, topdown = False):
        for f in files:
            os.remove(join(root, f))
        for d in dirs:
            os.rmdir(join(root, d))
    os.rmdir(path)


def run(cmd, path, dryrun = False):
    path = re.sub("([$\"\\\\])", "\\\\\\1", path)

    if re.search('%s', cmd):
        cmd = re.sub('%s', '"' + path + '"', cmd)
    else:
        cmd = "%s \"%s\"" % (cmd, path)

    l.debug("Executing: %s" % cmd)

    if not dryrun:
        p = subprocess.Popen(cmd, shell = True)
        sts = os.waitpid(p.pid, 0)
        return sts[1] == 0

    return True

def safeRun(cmd, path, sudo = False, dryrun = False):
    try:
        if not run(cmd, path, dryrun):
            l.error("Command failed: '%s' with '%s'" % (cmd, path))
            raise Exception()
        else:
            return True
    except:
        if sudo:
            try:
                run('sudo ' + cmd, path, dryrun)
                return True
            except:
                l.error("Command failed: 'sudo %s' with '%s'" % (cmd, path))
        return False

def safeRemove(entry):
    entry.remove()


class Entry(object):
    _scanner   = None
    _prevStamp = None
    _stamp     = None
    _prevInfo  = None
    _info      = None

    def __init__(self, theScanner, path):
        self._scanner = theScanner
        self._path    = path

    @property
    def scanner(self):
        return self._scanner

    @property
    def path(self):
        return self._path

    def __str__(self):
        return self.path

    @property
    def dryrun(self):
        return self._scanner.dryrun

    @property
    def sudo(self):
        return self._scanner.sudo

    @property
    def secure(self):
        return self._scanner.secure

    @property
    def info(self):
        if not self._info:
            self._info = os.lstat(self.path)
        return self._info

    @property
    def lastAccessTime(self):
        # Clear the cached info, since it may have changed
        self._info = None
        return datetime.fromtimestamp(self.info[ST_ATIME])

    @property
    def lastModTime(self):
        # Clear the cached info, since it may have changed
        self._info = None
        return datetime.fromtimestamp(self.info[ST_MTIME])

    def contentsHaveChanged(self):
        if not self._prevInfo:
            return False
        self._info = None
        return self.info[ST_MTIME] != self._prevInfo[ST_MTIME]

    def getTimestamp(self):
        if self._scanner.atime:
            return self.lastAccessTime
        elif self._scanner.mtime:
            return self.lastModTime

        if not self._stamp:
            self._stamp = rightNow
        return self._stamp

    def setTimestamp(self, stamp):
        if not isinstance(stamp, datetime):
            msg = "`setTimestamp' requires an argument of type `datetime'"
            l.exception(msg); raise InvalidArgumentException(msg)
        self._stamp = stamp

    timestamp = property(getTimestamp, setTimestamp)

    def timestampHasChanged(self):
        if not self._prevStamp:
            return False
        return self.timestamp != self._prevStamp

    def isDirectory(self):
        return S_ISDIR(self.info[ST_MODE])

    def shouldEnterDirectory(self):
        return self.isDirectory()

    def onEntryEvent(self, eventHandler):
        if isinstance(eventHandler, str):
            if safeRun(eventHandler, self.path, self.sudo, self.dryrun):
                return True
        elif callable(eventHandler):
            try:
                if eventHandler(self):
                    return True
            except Exception, inst:
                l.exception(str(inst))

        return False

    def onEntryAdded(self):
        l.info("A %s" % self.path)

        self._stamp = rightNow

        if self._scanner.onEntryAdded:
            self.onEntryEvent(self._scanner.onEntryAdded)
        return True

    def onEntryChanged(self, contentsChanged = False):
        l.info("%s %s" % (contentsChanged and "M" or "T", self.path))

        self._stamp = rightNow

        if self._scanner.onEntryChanged:
            self.onEntryEvent(self._scanner.onEntryChanged)
        return True

    def onEntryRemoved(self):
        l.info("R %s" % self.path)

        if self._scanner.onEntryRemoved:
            self.onEntryEvent(self._scanner.onEntryRemoved)
        return True

    def onEntryPastLimit(self, age):
        l.info("O %s (%.1f days old)" % (self.path, age))

        if self._scanner.onEntryPastLimit:
            self.onEntryEvent(self._scanner.onEntryPastLimit)

    def remove(self):
        """Remove a file or directory safely.

        The main point of this routine is three-fold:

        1. If the --secure option has been chosen, shell out to the `srm'
           command to perform the deletion of files. Directories are delete in
           the normal way (using os.rmdir).

        2. If --secure is not chosen, the Python functions os.remove and
           os.rmdir are used to remove files and directories.

        3. If --sudo-ok was chosen and the Python functions -- or `srm' --
           fail, try "sudo rm", "sudo rmdir" or "sudo srm": whichever is
           appropriate to what we're trying to do.

        4. If at last the file or directory could not be removed, print a
           notice to standard error. Cron will pick this up and send it to the
           administrator account in e-mail.

        5. If the deletion succeeded, remove the entry from the state database,
           mark the database as dirty, and return True so that we know to prune
           empty directories at the end of this run."""

        fileRemoved = False

        if isfile(self.path):
            secure = self.secure
            if not secure and self._scanner.securetag and osxtags and \
               osxtags.hastag(self.path, self._scanner.securetag):
                secure = True
                l.debug("Securely deleting '%s' as it had the tag '%s' set" %
                        (self, self._scanner.securetag))
            try:
                if secure:
                    if not run('/bin/srm -f', self.path, self.dryrun):
                        l.warning("Could not securely remove '%s'" % self)
                        raise Exception()
                else:
                    l.debug("Calling: cleanup.delfile('%s')" % self.path)
                    if not self.dryrun:
                        delfile(self.path)
            except:
                if self.sudo:
                    try:
                        if secure:
                            run('sudo /bin/srm -f', self.path, self.dryrun)
                        else:
                            run('sudo /bin/rm -f', self.path, self.dryrun)
                    except:
                        l.error("Error deleting file with sudo: %s" % self)

            if self.dryrun or not lexists(self.path):
                fileRemoved = True
            else:
                l.error("Could not remove file: %s\n" % self)
        else:
            try:
                l.debug("Calling: cleanup.deltree('%s')" % self.path)
                if not self.dryrun:
                    deltree(self.path)
            except:
                if self.sudo:
                    try:
                        run('sudo /bin/rm -fr', self.path, self.dryrun)
                    except:
                        l.error("Error deleting directory with sudo: %s" % self)

            if not self.dryrun and lexists(self.path):
                l.error("Could not remove dir: %s\n" % self.path)

        return fileRemoved

    def __getstate__(self):
        x = self.timestamp; assert x
        self._prevStamp = deepcopy(x)

        if self._scanner.check:
            x = self.info; assert x
            self._prevInfo = deepcopy(x)
            self._info = None

        odict = self.__dict__.copy() # copy the dict since we change it
        del odict['_scanner']

        return odict

    def __setstate__(self, info):
        self.__dict__.update(info) # update attributes
        self._info = None


class DirScanner(object):
    _dbMtime    = None
    _entries    = None
    _shadow     = None
    _dirty      = False
    _oldest     = 0
    _entryClass = Entry

    @property
    def entries(self):
        return self._entries

    def __init__(self,
                 directory        = None,
                 ages             = False, # this is a very odd option
                 atime            = False,
                 check            = False,
                 database         = '.files.dat',
                 days             = -1.0,
                 depth            = -1,
                 dryrun           = False,
                 ignoreFiles      = None,
                 minimalScan      = False,
                 mtime            = False,
                 onEntryAdded     = None,
                 onEntryChanged   = None,
                 onEntryRemoved   = None,
                 onEntryPastLimit = None,
                 pruneDirs        = False,
                 secure           = False,
                 securetag        = None,
                 sort             = False,
                 sudo             = False):

        # Check the validity of all arguments and their types (if applicable)

        if not directory:
            msg = "`directory' must be a valid directory"
            l.exception(msg); raise InvalidArgumentException(msg)

        d = expanduser(directory)
        if d != directory:
            l.info("Expanded directory '%s' to '%s'" % (directory, d))
            directory = d

        if not isdir(directory):
            msg = "Directory '%s' is not a valid directory" % directory
            l.exception(msg); raise InvalidArgumentException(msg)

        if not os.access(directory, os.R_OK | os.X_OK):
            msg = "Directory '%s' is not readable or not searchable" % directory
            l.exception(msg); raise InvalidArgumentException(msg)

        if not ignoreFiles:
            l.debug("Initializing `ignoreFiles' to []")
            ignoreFiles = []

        if not isinstance(ignoreFiles, list):
            msg = "`ignoreFiles' must be of list type"
            l.exception(msg); raise InvalidArgumentException(msg)

        if not database:
            database = '.files.dat'
            l.debug("Setting database name to '%s'" % database)

        if not isinstance(database, str):
            msg = "`database' must be of string type"
            l.exception(msg); raise InvalidArgumentException(msg)

        base = basename(database)
        if base not in ignoreFiles:
            l.debug("Adding '%s' to `ignoreFiles'" % base)
            ignoreFiles.append(base)

        if os.sep not in database:
            database = join(directory, database)
            l.debug("Expanding `database' to '%s'" % database)

        if minimalScan and depth != 0:
            l.warning("Using minimalScan when depth != 0 may cause problems")

        self.ages             = ages
        self.atime            = atime
        self.check            = check
        self.database         = database
        self.days             = days
        self.depth            = depth
        self.directory        = directory
        self.dryrun           = dryrun
        self.ignoreFiles      = ignoreFiles
        self.minimalScan      = minimalScan
        self.mtime            = mtime
        self.onEntryAdded     = onEntryAdded
        self.onEntryChanged   = onEntryChanged
        self.onEntryRemoved   = onEntryRemoved
        self.onEntryPastLimit = onEntryPastLimit
        self.pruneDirs        = pruneDirs
        self.secure           = secure
        self.securetag        = securetag
        self.sort             = sort
        self.sudo             = sudo

    def loadState(self):
        self._entries = {}
        self._dirty   = False
        self._dbMtime = None

        if not isfile(self.database):
            l.debug("State database '%s' does not exist yet" % self.database)
            return
        elif not os.access(self.database, os.R_OK):
            l.error("No read access to state data in '%s'" % self.database)
            return

        l.info("Loading state data from '%s'" % self.database)

        fd = open(self.database, 'rb')
        try:
            self._entries = cPickle.load(fd)

            # If the state database was created by the older cleanup.py, then
            # upgrade it.  Otherwise, associated each saved entry object with
            # this scanner.

            upgrade = {}
            for path, entry in self._entries.items():
                if isinstance(entry, datetime):
                    newEntry = self.createEntry(path)
                    newEntry._stamp = entry
                    upgrade[path] = newEntry
                else:
                    assert isinstance(entry, Entry)
                    entry._scanner = self

            if upgrade:
                self._entries = upgrade
        finally:
            fd.close()

        self._dbMtime = datetime.fromtimestamp(os.stat(self.database)[ST_MTIME])

    def saveState(self):
        if not self.database: return
        if not self._dirty: return
        if self.dryrun: return

        databaseDir = dirname(self.database)

        if not exists(databaseDir):
            l.info("Creating state database directory '%s'" % databaseDir)
            os.makedirs(databaseDir)

        if not isdir(databaseDir):
            l.error("Database directory '%s' does not exist" % databaseDir)
            return
        elif not os.access(databaseDir, os.W_OK):
            l.error("Could not write to database directory '%s'" % databaseDir)
            return

        l.debug("Writing updated state data to '%s'" % self.database)

        fd = open(self.database, 'wb')
        try:
            cPickle.dump(self._entries, fd)
        finally:
            fd.close()

        self._dirty   = False
        self._dbMtime = datetime.fromtimestamp(os.stat(self.database)[ST_MTIME])

    def registerEntryClass(self, entryClass):
        if not issubclass(entryClass, Entry):
            msg = "`entryClass' must be a class type derived from dirscan.Entry"
            l.exception(msg); raise InvalidArgumentException(msg)
            
        self._entryClass = entryClass

    def createEntry(self, path):
        return self._entryClass(self, path)

    def _scanEntry(self, entry):
        "Worker function called for every file in the directory."

        # If we haven't seen this entry before, call `onEntryAdded', which
        # ultimately results in triggering an onEntryAdded event.

        if not self._entries.has_key(entry.path):
            l.debug("Entry '%s' is being seen for the first time" % entry)
            if entry.onEntryAdded():
                self._entries[entry.path] = entry
                self._dirty = True

            assert not self._shadow.has_key(entry.path)

        # Otherwise, if the file changed, or `minimalScan' is False and the
        # timestamp is derived from the file itself (i.e., not just a record of
        # when we first saw it), then trigger an onEntryChanged event.

        else:
            # If the `check' option is True, check whether the modtime of
            # `path' is more recent than the modtime of the state database.

            changed = self.check and entry.contentsHaveChanged()

            if changed or entry.timestampHasChanged():
                l.debug("Entry '%s' %s seems to have changed" %
                        (entry, 'content' and changed or 'timestamp'))
                if entry.onEntryChanged(contentsChanged = changed):
                    self._dirty = True

            # Delete this path from the `shadow' dictionary, since we've now
            # dealt with it.  Any entries that remain in `shadow' at the end
            # will trigger an onEntryRemoved event.

            assert self._shadow.has_key(entry.path)
            del self._shadow[entry.path]

        # If the `days' option is greater than or equal to zero, do an age
        # check. If the file is "older" than `days', trigger an onEntryPastLimit
        # event.

        if self.days >= 0:
            delta = rightNow - entry.timestamp
            age   = float(delta.days) + float(delta.seconds) / 86400.0

            # The `ages' option, if True, means that we are just to print out
            # the ages of all entries -- don't do any deleting or pruning.
            # Updating the database's state is OK, however, so that subsequent
            # runs of `ages' are correct.

            if self.ages:
                print "%8.1f %s" % (age, entry)
                return

            if age > self._oldest:
                self._oldest = age

            # If the age of the file is greater than `days', trigger the event
            # `onEntryPastLimit'.

            if age >= self.days:
                l.debug("Entry '%s' is beyond the age limit" % entry)
                entry.onEntryPastLimit(age)

        # At this point, check whether we were dealing with a directory and if
        # it's now empty. If so, and if the `pruneDirs' option is True, then
        # delete the directory.

        if self.pruneDirs and isdir(entry.path) and not os.listdir(entry.path):
            l.info("Pruning directory '%s'" % entry)
            entry.remove()

        # Has the entry been removed from disk by any of the above actions? If
        # so, report it having been removed right now.

        if not lexists(entry.path) and entry.onEntryRemoved():
            l.debug("Entry '%s' was removed or found missing" % entry)
            if self._entries.has_key(entry.path):
                assert isinstance(self._entries[entry.path], Entry)
                assert self._entries[entry.path] is entry
                del self._entries[entry.path]
            self._dirty = True

    def _walkEntries(self, path, depth = 0):
        "This is the worker task for scanEntries, called for each directory."

        l.debug("Scanning %s ..." % path)
        try:
            items = os.listdir(path)
            if self.sort:
                items.sort()
        except:
            l.warning("Could not read directory '%s'" % path)
            return

        for name in items:
            entryPath = join(path, name)

            if name in self.ignoreFiles:
                l.debug("Ignoring file '%s'" % entryPath)
                continue

            if self._entries.has_key(entryPath):
                entry = self._entries[entryPath]
            else:
                entry = self.createEntry(entryPath)
                l.debug("Created entry '%s'" % entry)

            # Recurse here so that we work from the bottom of the tree up,
            # which allows us to prune directories as they empty out (if
            # `prune' is True). The pruning is done at the end of `scanEntry'.

            if entry.isDirectory() and \
               (self.depth < 0 or depth < self.depth) and \
               entry.shouldEnterDirectory():
                self._walkEntries(entryPath, depth + 1)

            self._scanEntry(entry)

    def scanEntries(self):
        """Scan the given directory, keeping state and acting on any changes.

        The given `directory' will be scanned, and a database kept within it
        whose name is given by `database' -- unless `database' is a relative or
        absolute pathname, in which case the database is kept there. This can
        be useful for scanning volumes which are read-only to the scanning
        process.

        Four triggers are available for acting on changes:

            onEntryAdded
            onEntryChanged
            onEntryRemoved
            onEntryPastLimit

        The first three triggers are always called, when a file or directory is
        first seen in `directory', (optionally) each time its timestamp or
        modtime is seen to change, and when it disappears. Each of these
        triggers may be of two kinds:

        string
          The string is taken to be a command, where every occurrence of %s
          within the string is replaced by the quoted filename, and the string
          is executed. If the `sudo' option is True, the same command will be
          attempted again -- with the command "sudo" prefixed to it -- if for
          any reason it fails.

        callable object
          The object called with the relevant path, and a dictionary of
          "options" which convey options specified by the caller. These are:

            data       The value of `data' passed in
            debug      If we are in debug mode
            dryrun     If this is a dry-run
            sudo       If sudo should be used to retry

            secure     If removes should be done securely
            securetag  A tag meaning: securely remove entry

        The last three of these are only passed to the handler
        `onEntryPastLimit'.

        Each handler must return True or False.  If True, the meaning is:

            onEntryAdded      The file should be added to the state database
            onEntryChanged    The file's age should be updated ...
            onEntryRemoved    The file should be removed ...
            onEntryPastLimit  The file was deleted; invoke onEntryRemoved

        If False is returned, the action is not done, and the same event may
        recur on the next run of this function (unless the handler physically
        removed the file, or prevented it from being deleted).

        The trigger `onEntryPastLimit' is special and is only called if the
        option `days' is set to a value zero or higher -- and which may be
        fractional. In this case, the handler is called when aa file entry is
        seen to be "older" than that many days.

        The concept of older depends on how the age of the file is determined:
        if `atime' is True, the file is aged according to its last access time;
        if `mtime' is used, then the file's modification time; if
        `getTimestamp' is a callable Python object, it will be called with the
        pathname of the file; otherwise, the script remembers when it first saw
        the file, and this is used to determine the age.

        If `check' is True, the modtime of all files will be checked on each
        run, and if they are newer than the last time the state database was
        changed, then `onEntryChanged' will be called.

        The other case where `onEntryChanged' might be called is if
        `minimalScan' is not used, which causes the timestamps of all files to
        be re-collected on every run. If any stamps change, `onEntryChanged' is
        called. This could be used for aging files based on their last access
        time, while ensuring that the most recent access time is always
        considered when determining the file's age.

        The `depth' option controls how deeply files are scanned. If set to 1,
        then only files and directories in `directory' are reported. If set to
        a number greater than 1, be aware than not only directories *but also
        the files within them* are passed to the event handlers.

        Directory contents may be changed by the event handlers, as each
        directory is scanned only when it is reached. If it disappears during a
        run, this will simply cause onEntryRemoved to be called.

        Lastly, the `alwaysPrune' option will cause empty directories found
        during the scanned to be pruned and `onEntryRemoved' to be called for
        them."""

        # Load the pre-existing state, if any, before scanning. If was already
        # loaded in a previous run, don't load it again.

        if not self._entries:
            self.loadState()

        assert isinstance(self._entries, dict)

        # If a state database did exist, check its last modified time. If more
        # recent than the directory itself, and if `minimalScan' is True, then
        # nothing has changed and we can exit now.

        scandir = True

        if self.minimalScan and self._dbMtime:
            assert isinstance(self._dbMtime, datetime)
            assert isdir(self.directory)
            assert os.access(self.directory, os.R_OK | os.X_OK)

            info     = os.stat(self.directory)
            dirMtime = datetime.fromtimestamp(info[ST_MTIME])

            if self._dbMtime >= dirMtime:
                scandir = False

            l.info("Database mtime %s < directory %s, %s scan" %
                   (self._dbMtime, dirMtime, scandir and "will" or "will not"))

        # If the directory has not changed, we can simply scan the entries in
        # the database without having to refer to disk. Otherwise, either the
        # directory has had files added or removed, or `minimalScan' is False.

        self._oldest = 0
        self._shadow = self._entries.copy()

        if not scandir:
            for entry in self._entries.values():
                assert isinstance(entry, Entry)
                self._scanEntry(entry)
        else:
            self._walkEntries(self.directory)

        # Anything remaining in the `shadow' dictionary are state entries which
        # no longer exist on disk, so we trigger `onEntryRemoved' for each of
        # them, and then remove them from the state database.

        for entry in self._shadow.values():
            if entry.onEntryRemoved():
                if self._entries.has_key(entry.path):
                    l.debug("Removing missing entry at '%s'" % entry)
                    del self._entries[entry.path]
                else:
                    l.warning("Missing entry '%s' not in entries list" % entry)
                self._dirty = True

        # Report what the oldest file seen was, if debugging

        if self._oldest < self.days:
            l.info("No files were beyond the age limit (oldest %.1fd < %.1fd)" %
                   (self._oldest, self.days))

        # If any changes have been made to the state database, write those
        # changes out before exiting.

        self.saveState()


######################################################################
#
# Since this script can also be run from the command-line, employing option
# switches to select behavior using the default DirScanner and Entry classes,
# then here follows the user interaction code for that mode of use.
#

# A big legal disclaimer, since this script rather aggressively deletes things
# when told to...


def showVersion():
    print """
dirscan.py, version 1.0

Copyright (c) 2007, by John Wiegley <johnw@newartisans.com>

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."""


def usage():
    print """Usage: cleanup [options]

Where 'options' is one or more of:
    -h, --help            This help screen
    -V, --version         Display this script's version number

    -d, --dir=X           Operate on directory X instead of ~/.Trash
    -D, --depth=X         Only scan X levels; 0 = entries of dir, -1 = recurse
    -b, --database=X      Store state in X (defaults to .files.dat in `dir')
    -o, --sort            Read directories entries in sorted order
    -u, --status          Show concisely what's happening, use -n for read-only
    -w, --days=X          Wait until entries are X days old before deleting
    -s, --sudo            If an operation fails, uses `sudo' to try again
    -S, --secure          Files are securely wiped instead of deleted
    -p, --prune-dirs      Prune empty directories during a scan

    -A, --ages            Displays the ages of entries, but deletes nothing
    -n, --nothing         Don't make any changes to the directory or its state
    -v, --verbose         Show what's being done (or what would be done, if -n)

    -z, --minimal-scan    Only check directory if files have been added/removed
                           ^ This does not consider subdirectories!

    -m, --mtime           Base file ages on their last modifiied time
    -a, --atime           Base file ages on their last accessed time
    -R, --check           If a file's modtime has changed, reset its age
                           ^ This is only necessary if -m or -a are not used

        --onadded=X       Execute X when an item is first seen in directory
        --onchanged=X     Execute X when an item is changed in directory
    -F, --onpastlimit=X   Execute X when an item is beyond the age limit
        --onremoved=X     Execute K after an item is removed from directory
                           ^ These four subsitute %s for the full path; don't
                             worry about quoting.  Also, new/changed/removed
                             directories are passed as well as files.  To
                             delete only files: -F "test -f %s && rm -f %s"

    -T, --securetag=X     If an entry is tagged with X, secure delete it
                           ^ This option requires OS/X and appscript

Defaults:
    cleanup -d ~/.Trash -b .files.dat -w 7 -D 0 -p

If you have sudo and use the NOACCESS option, I recommend this on OS/X:

    sudo cleanup -d /.Trashes; cleanup -s

If you have 'appscript' installed, you can mark files for secure
deletion using a Finder comment.  If the tag were @private, then say:

    cleanup -T @private

Let's say you want to move downloaded files from ~/Library/Downloads
to /Volumes/Archive after a stay of 3 days.  Here's a command you
might run (maybe hourly) to achieve this:

    cleanup -w 3 -p -d ~/Library/Downloads -m \\
            -F 'mv %s /Volumes/Archive' -K '@pending'

Broken down piece by piece:

    -w 3    # Wait for 3 days until a file is acted upon
    -p      # Clean up empty directories and dangling links
            # NOTE: this is done automatically if -F is not used
    -d ...  # Sets the directory to scan to: ~/Library/Downloads
    -m      # Base entry ages on their modification time.  This is
            # helpful with downloads because their modtime is exactly
            # when they got stored in the downloads dir
    -F ...  # Set the command to run when a file is out-of-date.  The
            # string %s in the command is replaced with the quoted
            # filename.
    -K ...  # If any file is tagged with a Finder comment containing
            # @pending, it will not be moved from the Downloads
            # directory.  I use this for items I have yet to look at,
            # but for which I haven't time."""


def processOptions(argv):
    "Process the command-line options."
    longOpts = [
        'ages',                         # -A
        'atime',                        # -a
        'check',                        # -R
        'database=',                    # -b
        'days=',                        # -w
        'depth=',                       # -D
        'directory=',                   # -d
        'dryrun',                       # -n
        'help',                         # -h
        'mtime',                        # -m
        'onadded=',
        'onchanged=',
        'onpastlimit=',                 # -F
        'onremoved=',
        'prune-dirs',                   # -p
        'minimal-scan',                 # -z
        'secure',                       # -S
        'securetag=',                   # -T
        'sort',                         # -o
        'status',                       # -u
        'sudo',                         # -s
        'verbose',                      # -v
        'version' ]                     # -V

    try:
        opts = getopt(argv, 'AaRb:w:D:d:nhmF:pzST:ousvV', longOpts)[0]
    except GetoptError:
        usage()
        sys.exit(2)

    options = {
        'directory':        expanduser('~/.Trash'),
        'depth':            0,
        'days':             7,
        'onEntryPastLimit': safeRemove
    }

    for o, a in opts:
        if o in ('-h', '--help'):
            usage()
            sys.exit(0)
        elif o in ('-V', '--version'):
            showVersion()
            sys.exit(0)

        elif o in ('-A', '--ages'):
            options['ages']            = True
        elif o in ('-a', '--atime'):
            options['atime']           = True
        elif o in ('-R', '--check'):
            options['check']           = True
            options['minimalScan']     = False
        elif o in ('-b', '--database'):
            options['database']        = a
        elif o in ('-w', '--days'):
            options['days']            = float(a)
            options['database']        = a
        elif o in ('-D', '--depth'):
            options['depth']           = int(a)
        elif o in ('-d', '--directory'):
            options['directory']       = expanduser(a)
        elif o in ('-n', '--dryrun'):
            options['dryrun']          = True
        elif o in ('-m', '--mtime'):
            options['mtime']           = True
        elif o in ('--onadded'):
            options['onEntryAdded']     = a
        elif o in ('--onchanged'):
            options['onEntryChanged']   = a
        elif o in ('-F', '--onpastlimit'):
            options['onEntryPastLimit'] = a
        elif o in ('--onremoved'):
            options['onEntryRemoved']   = a
        elif o in ('-p', '--prune-dirs'):
            options['pruneDirs']       = True
        elif o in ('-z', '--minimal-scan'):
            options['minimalScan']     = True
        elif o in ('-S', '--secure'):
            options['secure']          = True
        elif o in ('-T', '--securetag'):
            if not osxtags:
                sys.stderr.write(
                    "Warning: --securetag used, but osxtags was not found\n")
            options['securetag']       = a
        elif o in ('-o', '--sort'):
            options['sort']            = True
        elif o in ('-u', '--status'):
            l.basicConfig(level = l.INFO, format = '%(message)s')
        elif o in ('-s', '--sudo'):
            options['sudo']            = True
        elif o in ('-v', '--verbose'):
            l.basicConfig(level = l.DEBUG,
                          format = '[%(levelname)s] %(message)s')

    return options


if __name__ == '__main__':
    if len(sys.argv) == 1:
        usage()
        sys.exit(2)

    assert len(sys.argv) > 1
    userOptions = processOptions(sys.argv[1:])

    if not isdir(userOptions['directory']):
        sys.stderr.write("The directory '%s' does not exist" %
                         userOptions['directory'])
        sys.exit(1)

    scanner = DirScanner(**userOptions)
    scanner.scanEntries()

# dirscan.py ends here