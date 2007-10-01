#!/usr/bin/env python

# A big legal disclaimer, since this script rather aggressively
# deletes things when told to...

def showVersion():
    print """
cleanup, version 1.0

Copyright (c) 2007, by John Wiegley <johnw@newartisans.com>

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."""


import os
import re
import sys
import getopt
import cPickle
import subprocess

from stat import *
from os.path import *
from datetime import *

rightNow = datetime.now()


# Use my osxtags.py module to interface with metadata tags on OS/X.

osxtags = None
try:
    import osxtags
except: pass


class Options:
    ages            = False
    minimalScan     = False
    atime           = False
    check           = False
    data            = None
    database        = '.files.dat'
    dbMtime         = None
    days            = -1.0
    debug           = False
    depth           = -1
    dryrun          = False
    getTimestamp    = None
    ignoreFiles     = []
    keeptag         = None
    mtime           = False
    onFileAdded     = None
    onFileChanged   = None
    onFilePastLimit = None
    onFileRemoved   = None
    pruneDirs       = False
    secure          = False
    securetag       = None
    sort            = False
    status          = False
    sudo            = False


# Now for the functions that make up this module...
#
# You may, if desired, run this code from another Python script by calling
# `scanDirectory' and passing all the script's accepted long options as named
# parameters (except for `directory', which is the required first parameter).
# Example:
#
#     cleanup --directory /tmp --days 7
#
# Is equivalent to:
#
#     import cleanup
#     cleanup.cleanDirectory('/tmp', days = 7)
#
# The main difference to note is that the following options have different
# argument names in Python:
#
#     --onadded         onFileAdded
#     --onchanged       onFileChanged
#     --onpastlimit     onFilePastLimit
#     --onremoved       onFileRemoved
#     --prune-dirs      pruneDirs
#     --minimal-scan    minimalScan
#
# Also, if you are calling scanDirectory, then onFilePastLimit does
# NOT have a default behavior.  To emulate what calling this script
# from the command-line does, you will have to call scanDirectory as
# follows:
#
#     cleanup.scanDirectory(expanduser('~/.Trash'), days = 7,
#                           onFilePastLimit = cleanup.safeRemove)
#
# There is also one extra option not available from the command-line:
#
#     getTimestamp      A callable object passed (path, Options) which
#                       must return a `datetime' instance

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
    -K, --keeptag=X       If an entry is tagged with X, never delete it
                           ^ These two require OS/X and appscript

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


def delfile(path):
    if lexists(path):
        os.remove(path)

def deltree(path):
    if not lexists(path): return
    for root, dirs, files in os.walk(path, topdown = False):
        for file in files:
            os.remove(join(root, file))
        for dir in dirs:
            os.rmdir(join(root, dir))
    os.rmdir(path)


def loadDatabase(file, o):
    entries = {}

    if isfile(file):
        if o.debug:
            print "Loading entry data from '%s'" % file
        fd = open(file, 'r')
        entries = cPickle.load(fd)
        fd.close()

    return entries

def saveDatabase(file, entries, o):
    dir = dirname(file)
    if not lexists(dir):
        os.makedirs(dir)

    fd = open(file, 'w')
    if o.debug:
        print "Writing updated entry data to '%s'" % file
    cPickle.dump(entries, fd)
    fd.close()


def report(imp, prog, str, o):
    if o.dryrun:
        print "%s: %s" % (imp, str)
    else:
        print "%s: %s" % (prog, str)


def run(cmd, path, o):
    path = re.sub("([$\"\\\\])", "\\\\\\1", path)

    if re.search('%s', cmd):
        cmd = re.sub('%s', '"' + path + '"', cmd)
    else:
        cmd = "%s \"%s\"" % (cmd, path)

    if o.debug:
        report('Execute', 'Executing', cmd, o)

    if not o.dryrun:
        p = subprocess.Popen(cmd, shell = True)
        sts = os.waitpid(p.pid, 0)
        return sts[1] == 0

    return True

def safeRun(cmd, path, o):
    try:
        if not run(cmd, path, o):
            if o.debug:
                print "Command failed: '%s' with '%s'" % (cmd, path)
            raise Exception()
        else:
            return True
    except:
        if o.sudo:
            try:
                run('sudo ' + cmd, path, o)
                return True
            except: pass
        return False


def remove(path, o):
    """Remove a file or directory safely.

    The main point of this routine is three-fold:

    1. If the --secure option has been chosen, shell out to the `srm' command
       to perform the deletion of files. Directories are delete in the normal
       way (using os.rmdir).

    2. If --secure is not chosen, the Python functions os.remove and os.rmdir
       are used to remove files and directories.

    3. If --sudo-ok was chosen and the Python functions -- or `srm' -- fail,
       try "sudo rm", "sudo rmdir" or "sudo srm": whichever is appropriate to
       what we're trying to do.

    4. If at last the file or directory could not be removed, print a notice to
       standard error. Cron will pick this up and send it to the administrator
       account in e-mail.

    5. If the deletion succeeded, remove the entry from the state database,
       mark the database as dirty, and return True so that we know to prune
       empty directories at the end of this run."""

    fileRemoved = False

    if o.keeptag and osxtags and osxtags.hastag(path, o.keeptag):
        return False

    if isfile(path):
        secure = o.secure
        if not secure and o.securetag and osxtags and \
           osxtags.hastag(path, o.securetag):
            secure = True
            if o.debug:
                print "Securely deleting '%s' as it had the tag '%s' set" % \
                      (path, o.securetag)
        try:
            if secure:
                if not run('srm -f', path, o):
                    if o.debug:
                        print "Could not securely remove '%s'" % path
                    raise Exception()
            else:
                if o.debug:
                    report('Call', 'Calling', "cleanup.delfile('%s')" % path, o)
                if not o.dryrun:
                    delfile(path)
        except:
            if o.sudo:
                try:
                    if secure:
                        run('sudo srm -f', path, o)
                    else:
                        run('sudo rm -f', path, o)
                except: pass

        if o.dryrun or not lexists(path):
            fileRemoved = True
        else:
            sys.stderr.write("Could not remove file: %s\n" % path)
    else:
        try:
            if o.debug:
                report('Call', 'Calling', "cleanup.deltree('%s')" % path, o)
            if not o.dryrun:
                deltree(path)
        except:
            if o.sudo:
                try:
                    run('sudo rm -fr', path, o)
                except: pass

        if not o.dryrun and lexists(path):
            sys.stderr.write("Could not remove dir: %s\n" % path)

    return fileRemoved


def onEntryEvent(eventHandler, path, message, o):
    if o.debug:
        print message

    eventHandled = False

    if isinstance(eventHandler, str):
        if o.debug:
            if safeRun(eventHandler, path, o):
                eventHandled = True
        else:
            try:
                if safeRun(eventHandler, path, o):
                    eventHandled = True
            except: pass

    elif callable(eventHandler):
        if o.debug:
            if eventHandler(path, o):
                eventHandled = True
        else:
            try:
                if eventHandler(path, o):
                    eventHandled = True
            except: pass
    else:
        eventHandled = True

    if eventHandled:
        return True

    return False

def onEntryAdded(entries, path, stamp, o):
    if o.status:
        print "A", path
    if onEntryEvent(o.onFileAdded, path,
                    "Saw '%s' for the first time" % path, o):
        entries[path] = stamp
        return True
    return False

def onEntryChanged(entries, path, stamp, o):
    if o.status:
        print "M", path
    if onEntryEvent(o.onFileChanged, path,
                    "'%s' has changed since last time" % path, o):
        entries[path] = stamp
        return True
    return False

def onEntryRemoved(entries, path, o):
    if o.status:
        print "R", path
    if onEntryEvent(o.onFileRemoved, path,
                    "'%s' has disappeared from the directory" % path, o):
        del entries[path]
        return True
    return False


def scanEntry(entries, shadow, path, o):
    "Worker function called for every file in the directory."

    dirty     = False
    oldestAge = 0
    changed   = False
    info      = None

    # If the `check' option is True, check whether the modtime of `path' is
    # more recent than the modtime of the state database.

    if o.check and o.dbMtime:
        info = os.lstat(path)

        fileMtime = datetime.fromtimestamp(info[ST_MTIME])
        if fileMtime >= o.dbMtime:
            changed = True

    # If we haven't seen this entry before, or if it has changed, or
    # if the `minimalScan' option is False, then get the interesting
    # timestamp for this file (possibly regetting it).

    stampFromFile = o.atime or o.mtime or callable(o.getTimestamp)

    if not entries.has_key(path) or changed or \
       (stampFromFile and not o.minimalScan):
        if o.atime:
            if not info: info = os.lstat(path)
            stamp = datetime.fromtimestamp(info[ST_ATIME])
        elif o.mtime and info:
            stamp = fileMtime
        elif o.mtime:
            if not info: info = os.lstat(path)
            stamp = datetime.fromtimestamp(info[ST_MTIME])
        elif callable(o.getTimestamp):
            stamp = o.getTimestamp(path)
        else:
            stamp = rightNow
    else:
        stamp = entries[path]

    # If we really haven't seen this entry before, call `onEntryAdded', which
    # ultimately results in triggering an onFileAdded event.

    if not entries.has_key(path):
        if onEntryAdded(entries, path, stamp, o):
            dirty = True

    # Otherwise, if the file changed, or `minimalScan' is False and the
    # timestamp is derived from the file itself (i.e., not just a record of
    # when we first saw it), then trigger an onFileChanged event.

    elif changed or (stampFromFile and not o.minimalScan and
                     entries[path] != stamp):
        if onEntryChanged(entries, path, stamp, o):
            dirty = True

    # Delete this path from the `shadow' dictionary, since we've now dealt with
    # it. Any entries that remain in `shadow' at the end will trigger an
    # onFileRemoved event.

    if shadow.has_key(path):
        del shadow[path]

    # If the `days' option is greater than or equal to zero, do an age check.
    # If the file is "older" than `days', trigger an onFilePastLimit event.

    if o.days >= 0:
        delta = rightNow - stamp
        age   = float(delta.days) + float(delta.seconds) / 86400.0

        # The `ages' option, if True, means that we are just to print out the
        # ages of all entries -- don't do any deleting or pruning. Updating the
        # database's state is OK, however, so that subsequent runs of `ages'
        # are correct.

        if o.ages:
            print "%8.2f %s" % (age, path)
            return (dirty, oldestAge)

        if age > oldestAge:
            oldestAge = age

        # If the age of the file is greater than `days', trigger the event
        # `onFilePastLimit'.

        if age >= o.days:
            if o.status:
                print "O", path
            if o.debug:
                report('Act on', 'Acting on', "%s (%.2fd old)" % (path, age), o)

            if isinstance(o.onFilePastLimit, str):
                safeRun(o.onFilePastLimit, path, o)

            elif callable(o.onFilePastLimit):
                o.onFilePastLimit(path, o)

    # At this point, check whether we were dealing with a directory and if it's
    # now empty. If so, and if the `pruneDirs' option is True, then delete the
    # directory.

    if o.pruneDirs and isdir(path) and not os.listdir(path):
        if o.debug:
            report('Prune', 'Pruning', path, o)
        remove(path, o)

    # Has the entry been removed from disk by any of the above actions? If so,
    # report it having been removed right now.

    if not lexists(path) and entries.has_key(path) and \
       onEntryRemoved(entries, path, o):
        dirty = True

    # Lastly, let our caller know if we changed the state of the state
    # database, and also what the oldest file we saw was.

    return (dirty, oldestAge)


def scanEntries(entries, shadow, directory, depth, o):
    "This is the worker task for scanDirectory, called for each directory."

    dirty     = False
    oldestAge = 0

    try:
        items = os.listdir(directory)
        if o.sort:
            items.sort()
    except:
        if o.debug:
            print "Could not read directory '%s'" % directory
        items = []

    for entry in items:
        if entry in o.ignoreFiles:
            continue

        path = join(directory, entry)

        # Recurse here so that we work from the bottom of the tree up, which
        # allows us to prune directories as they empty out (if `prune' is
        # True).  The pruning is done at the end of `scanEntry'.

        if isdir(path) and (o.depth < 0 or depth < o.depth):
            (dirt, old) = scanEntries(entries, shadow, path, depth + 1, o)

            if dirt: dirty = True
            if old > oldestAge: oldestAge = old

        (dirt, old) = scanEntry(entries, shadow, path, o)

        if dirt: dirty = True
        if old > oldestAge: oldestAge = old

    return (dirty, oldestAge)


def scanDirectory(directory,
                  ages            = False,
                  minimalScan     = False,
                  atime           = False,
                  check           = False,
                  data            = None,
                  database        = '.files.dat',
                  days            = -1.0,
                  debug           = False,
                  depth           = -1,
                  dryrun          = False,
                  getTimestamp    = None,
                  ignoreFiles     = [],
                  keeptag         = None,
                  mtime           = False,
                  onFileAdded     = None,
                  onFileChanged   = None,
                  onFilePastLimit = None,
                  onFileRemoved   = None,
                  pruneDirs       = False,
                  secure          = False,
                  securetag       = None,
                  sort            = False,
                  status          = False,
                  sudo            = False):
    """Scan the given directory, keeping its state and acting on any changes.

The given `directory' will be scanned, and a database kept within it whose name
is given by `database' -- unless `database' is a relative or absolute pathname,
in which case the database is kept there. This can be useful for scanning
volumes which are read-only to the scanning process.

Four triggers are available for acting on changes:

    onFileAdded
    onFileChanged
    onFileRemoved
    onFilePastLimit

The first three triggers are always called, when a file or directory is first
seen in `directory', (optionally) each time its timestamp or modtime is seen to
change, and when it disappears. Each of these triggers may be of two kinds:

    string
      The string is taken to be a command, where every occurrence of %s within
      the string is replaced by the quoted filename, and the string is
      executed. If the `sudo' option is True, the same command will be
      attempted again -- with the command "sudo" prefixed to it -- if for any
      reason it fails.

    callable object
      The object called with the relevant path, and a dictionary of "options"
      which convey options specified by the caller. These are:

        data       The value of `data' passed in
        debug      If we are in debug mode
        dryrun     If this is a dry-run
        sudo       If sudo should be used to retry

        keeptag    A tag whose presence means: don't delete
        secure     If removes should be done securely
        securetag  A tag meaning: securely remove entry

      The last three of these are only passed to the handler `onFilePastLimit'.

Each handler must return True or False.  If True, the meaning is:

    onFileAdded      The file should be added to the state database
    onFileChanged    The file's age should be updated ...
    onFileRemoved    The file should be removed ...
    onFilePastLimit  The file was deleted; invoke onFileRemoved

If False is returned, the action is not done, and the same event may recur on
the next run of this function (unless the handler physically removed the file,
or prevented it from being deleted).

The trigger `onFilePastLimit' is special and is only called if the option
`days' is set to a value zero or higher -- and which may be fractional. In this
case, the handler is called when aa file entry is seen to be "older" than that
many days.

The concept of older depends on how the age of the file is determined: if
`atime' is True, the file is aged according to its last access time; if `mtime'
is used, then the file's modification time; if `getTimestamp' is a callable
Python object, it will be called with the pathname of the file; otherwise, the
script remembers when it first saw the file, and this is used to determine the
age.

If `check' is True, the modtime of all files will be checked on each run, and
if they are newer than the last time the state database was changed, then
`onFileChanged' will be called.

The other case where `onFileChanged' might be called is if `minimalScan' is not
used, which causes the timestamps of all files to be re-collected on every run.
If any stamps change, `onFileChanged' is called. This could be used for aging
files based on their last access time, while ensuring that the most recent
access time is always considered when determining the file's age.

The `depth' option controls how deeply files are scanned. If set to 1, then
only files and directories in `directory' are reported. If set to a number
greater than 1, be aware than not only directories *but also the files within
them* are passed to the event handlers.

Directory contents may be changed by the event handlers, as each directory is
scanned only when it is reached. If it disappears during a run, this will
simply cause onFileRemoved to be called.

Lastly, the `alwaysPrune' option will cause empty directories found during the
scanned to be pruned and `onFileRemoved' to be called for them."""

    # Convert the passed options to a format used throughout this code

    o = Options()

    o.ages            = ages
    o.minimalScan     = minimalScan
    o.atime           = atime
    o.check           = check
    o.data            = data
    o.database        = database
    o.days            = days
    o.debug           = debug
    o.depth           = depth
    o.dryrun          = dryrun
    o.getTimestamp    = getTimestamp
    o.ignoreFiles     = ignoreFiles
    o.keeptag         = keeptag
    o.mtime           = mtime
    o.onFileAdded     = onFileAdded
    o.onFileChanged   = onFileChanged
    o.onFilePastLimit = onFilePastLimit
    o.onFileRemoved   = onFileRemoved
    o.pruneDirs       = pruneDirs
    o.secure          = secure
    o.securetag       = securetag
    o.sort            = sort
    o.status          = status
    o.sudo            = sudo

    # Load the database reflecting the previous known state. If not present,
    # every file and directory beneath `directory' is considered new.

    if o.database:
        base = basename(o.database)
        if base not in o.ignoreFiles:
            o.ignoreFiles.append(basename(o.database))

        if os.sep not in o.database:
            dbfile = join(directory, o.database)
        else:
            dbfile = o.database

        entries = loadDatabase(dbfile, o)
    else:
        entries = {}

    # If a state database did exist, check its last modified time. If more
    # recent than the directory itself, and if `minimalScan' is True, then
    # nothing has changed and we can exit now.
            
    o.dbMtime = None
    scandir   = True

    if lexists(dbfile):
        info      = os.stat(dbfile)
        o.dbMtime = datetime.fromtimestamp(info[ST_MTIME])

    if o.minimalScan and o.dbMtime:
        info     = os.stat(directory)
        dirMtime = datetime.fromtimestamp(info[ST_MTIME])

        if o.dbMtime >= dirMtime:
            scandir = False
        elif o.debug:
            print "Database mtime %s < directory %s, will scan" % \
                  (o.dbMtime, dirMtime)

    # If the directory has not changed, we can simply scan the entries in the
    # database without having to refer to disk.

    shadow = entries.copy()

    if not scandir:
        dirty     = False
        oldestAge = 0

        for path in entries.keys():
            (dirt, old) = scanEntry(entries, shadow, path, o)
            if dirt: dirty = True
            if old > oldestAge: oldestAge = old

    # Otherwise, either the directory has had files added or removed, or
    # `minimalScan' is False.

    else:
        if o.debug:
            print "Scanning '%s' for changes..." % directory
        (dirty, oldestAge) = scanEntries(entries, shadow, directory, 0, o)

    # Report what the oldest file seen was, if debugging

    if o.debug and oldestAge < o.days:
        print "No files were beyond the age limit (oldest %.2fd [< %.2fd])" % \
              (oldestAge, o.days)

    # Anything remaining in the `shadow' dictionary are state entries which no
    # longer exist on disk, so we trigger `onFileRemoved' for each of them, and
    # then remove them from the state database.

    for path in shadow.keys():
        if onEntryRemoved(entries, path, o):
            dirty = True

    # If any changes have been made to the state database, write those changes
    # out before exiting.

    if o.database and dirty and not o.dryrun:
        try:
            saveDatabase(dbfile, entries, o)
        except:
            print "Could not save state database '%s'!" % dbfile


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
        'keeptag=',                     # -K
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
        opts, args = getopt.getopt(argv, 'AaRb:w:D:d:nF:hK:mpzST:ousvV',
                                   longOpts)
    except getopt.GetoptError:
        usage()
        sys.exit(2)

    options = {
        'directory':       expanduser('~/.Trash'),
        'minimalScan':     True,
        'depth':           0,
        'days':            7,
        'onFilePastLimit': remove
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
        elif o in ('-K', '--keeptag'):
            if not osxtags:
                sys.stderr.write(
                    "Warning: --keeptag used, but osxtags was not found\n")
            options['keeptag']         = a
        elif o in ('-m', '--mtime'):
            options['mtime']           = True
        elif o in ('--onadded'):
            options['onFileAdded']     = a
        elif o in ('--onchanged'):
            options['onFileChanged']   = a
        elif o in ('-F', '--onpastlimit'):
            options['onFilePastLimit'] = a
        elif o in ('--onremoved'):
            options['onFileRemoved']   = a
        elif o in ('-p', '--prune-dirs'):
            options['pruneDirs']       = True
        elif o in ('-z', '--minimal-scan'):
            options['minimalScan']     = True
        elif o in ('-S', '--secure'):
            options['secure']          = True
        elif o in ('-T', '--securetag'):
            if not osxtags:
                sys.stderr.write(
                    "Warning: --keeptag used, but osxtags was not found\n")
            options['securetag']       = a
        elif o in ('-o', '--sort'):
            options['sort']            = True
        elif o in ('-u', '--status'):
            options['status']          = True
        elif o in ('-s', '--sudo'):
            options['sudo']            = True
        elif o in ('-v', '--verbose'):
            options['debug']           = True

    return options


if __name__ == '__main__':
    if len(sys.argv) == 1:
        usage()
        sys.exit(1)

    options = processOptions(sys.argv[1:])

    directory = options['directory']
    del options['directory']

    scanDirectory(directory, **options)
