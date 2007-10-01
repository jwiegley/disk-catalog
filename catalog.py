#!/usr/bin/env python
#
# catalog.py, version 10
# by John Wiegley <johnw@newartisans.com>
#
# Depends on: MySQL 5 (using MyISAM), Python 2.5
#   Optional: p7zip, rar

# TODO
#
# - Write "name", "path", and "ext" basic queries
# - Exclude trashes, device files (/dev, /proc), and mount locations

# ABOUT
#
# This is a disk cataloguing program.  For those familiar with UNIX,
# it's similar to "locate": the main difference being that it's
# intended to handle very large numbers of files (millions), as well
# as allowing you to query against unmounted filesets -- such as files
# on a CD or in a disk image.
#
# Some of its salient features are:
#
# 1. It will descend into compressed and uncompressed archives.
#    a. .zip and .jar
#    b. .tar, .tar.gz, .tgz, .tar.bz2, .tbz
#    d. .rar
#    c. .7z
#
# 2. On OS/X, it will descend into disk images, provided that:
#    a. They do not ask for agreement to a software license, and
#    b. They are not encrypted (unless explicitly requested).
#
# 3. Disk images within disk images are searched, and so on
#    recursively, as long as #2 remains true.
#
# 4. Archives within disk images are searched, but not disk images
#    within archives, or archives within archives.
#
# 5. All data is kept in simple relational tables, allowing you to
#    form complex SQL queries to find exactly what you're looking for.
#    The database schema is described below.

# INSTALL
#
# To get this working on my MacBook Pro (10.4.9), using the MacPorts
# system for installing free software, I had to install the following
# packages by using "port install ...":
#
#   mysql5
#   python25
#   py25-bz2
#   py25-hashlib
#   py25-mx-base
#   py25-zlib
#   p7zip
#
# If you want to inspect .rar files, you'll need a copy of the "rar"
# command-line utility.  I use the one that comes with the application
# SimplyRAR.  You'll have to link to the "rar" utility in the
# application bundle to someplace along your PATH.

# SCHEMA
#
# It's all in the data, isn't it?  This program is mostly about
# seeding a MySQL database so you can later write queries to your
# heart's content.  But to do that, you'll need to fully understand
# how the data is stored and related: its schema.
#
# The first table is `volumes`, which tracks all of the volumes you've
# indexed.  Each volume has an `id`, which is of particular interest.
# The other elements in this table are purely informative:
#
#   `name`        VARCHAR   The unique name you gave to the volume
#   `location`    VARCHAR   Where it resides, physically or digitally
#   `kind`        VARCHAR   A description of the kind of volume it is
#   `totalCount`  INT       The total number of entries in the volume
#   `totalSize`   BIGINT    The total uncompressed size of those entries
#
# The next, and largest table in the database is `entries`, which is
# almost always what you'll be looking for, by joining the `entries`
# table with some of the other tables.  Each entry has a `volumeId`
# referring back to the volume it's stored in.  So, to query for all
# entries in your "My Book" volume, you'd use this:
#
#   SELECT e.`id`, e.`volumePath` FROM `entries` as e, `volumes` as v
#    WHERE v.`name` = "My Book" AND e.`volumeId` = v.`id`
#
# The `entries` table has the largest number of columns, not all of
# which will have values (many of them will be NULL if the entry lives
# in an archive, for example).  They are:
#
#   `id`             INT        The entry's id
#   `volumeId`       INT        The id of the volume it resides in
#   `directoryId`    INT        The id of its parent (directory) entry
#   `name`           VARCHAR    Its filename 
#   `baseName`       VARCHAR    Its basename (sans extension)
#   `extension`      TINYTEXT   Its extension
#   `kind`           INT        Its type (see below)
#   `permissions`    INT        Its UNIX file permissions, from octal
#   `owner`          INT        The owner's user id
#   `group`          INT        The owner's group id
#   `created`        DATETIME   When it was created
#   `dataModified`   DATETIME   When its data was last modified
#   `attrsModified`  DATETIME   When attributes/metadata were modified
#   `dataAccessed`   DATETIME   When its data was last accessed
#   `volumePath`     VARCHAR    Its full path within the volume
#
# There are several kinds of entries, whose `kind` will match to one
# of the following:
#
#   1    A directory
#   2    A plain old file
#   3    A symbolic link
#   4    An OS/X package, like an application directory
#   7    An archive or disk image file
#   10   A special system file (like a named pipe, socket, device, etc)
#
# Each kind of entry has one (or two) associated attribute records.
# Directories have a directory record, files have a file record, and
# archives have both (one referring to the archive itself, and a
# directory record referring to the contents within it).
#
# The `fileAttrs` table records information about actual files (things
# you could move around with the 'cp' command, let's say). It's
# columns are:
#
#   `id`           INT       The unique id of this attribute record
#   `entryId`      INT       The id of the entry it describes
#   `linkGroupId`  INT       Id of the "link group" this entry belongs to
#   `size`         BIGINT    The size of the file
#   `encoding`     TINYTEXT  The enconding of its contents (if applicable)
#
# The `dirAttrs` table records information about directories and
# archive contents:
#
#   `id`           INT       The unique id of this attribute record
#   `entryId`      INT       The id of the entry it describes
#   `thisCount`    INT       The count of its immediate children
#   `thisSize`     BIGINT    The total size of its immediate children
#   `totalCount`   INT       The count of all "descended" entries
#   `totalSize`    BIGINT    The total size of all "descendend" entries
#
# The `linkAttrs` table is just for symbolic links, and basically it
# just records which entry the link points to:
#
#   `id`           INT       Id of the link attribute
#   `entryId`      INT       Entry id for the symbolic link itself
#   `targetId`     INT       Id of the entry it points to
#
# The `metadata` table is special, and allows typed metadata to be
# stored for an entry. Both individual items, and even lists and trees
# of typed items, may be stored in this table.  It's structure is:
#
#   `id`           INT       Id of the metadata item
#   `entryId`      INT       Id of the entry it relates to
#   `metadataId`   INT       (Optional) Id of parent metadata record
#   `name`         TEXT      Name of this metadata item
#   `type`         INT       The type of the metadata (see below)
#   `textValue`    TEXT      The value of a text metadata item
#   `intValue`     INT       The value of an integer metadata item
#   `dateValue`    DATETIME  The value of a date/time metadata item
#   `blobValue`    BLOB      The value of a generic metadata item
#
# The `type` column determines which of the data columns is used, or
# even if any of them are used. The possible type values are:
#
#   1  Text
#   2  Integer
#   3  Date/time
#   4  Generic (blob data, not searchable)
#   5  List
#
# In the case of a list, none of the data fields are used. Rather, it
# means that there are other metadata entries, all with the same
# `entryId`, whose `metadataId` refers back to the parent list. If
# members of the list are also list items, the results can be a tree
# of arbitrary depth. However, every member of the tree will have the
# same `entryId` set, and the same `name`, making it possible to query
# the entry tree based on the entry or name, without regard to its
# structure.
#
# A WORD ON INDICES: Since most name-based searches are going to be
# partial (LIKE) or regular expressions (RLIKE), and since the indices
# for this kind of database can get HUGE, I haven't bothered to index
# the textual fields, such as filenames. Yes, there will be times when
# you search for an exact filename, and having an index would make
# this very fast, but it just doesn't happen often enough to justify
# the many megabytes of space such an index would require. But if you
# prefer to have indices, feel free to create them after your database
# has been initialized (the first run of the program). Just use the
# mysql command-line tool and run a command like this:
#
#   ALTER TABLE `entries` ADD INDEX(name(250))
#
# You'll find that choosing numbers above 250 (or a total index length
# above 250) will generate an error from MySQL about the maximum index
# length being around 750 or so. This is because of character
# encoding, which in some cases requires up to 3-bytes per character.
# Oh, and expect this command to take an extremely long time for a
# large database. My own database of just two external hard drives has
# over a million entries in it already.

import MySQLdb
import mx.DateTime
import zipfile
import tarfile

alwaysRescan = True
try:
    import cleanup
except:
    alwaysRescan = True

import os
import re
import sys

from subprocess import Popen, PIPE
from os.path import *
from stat import *

openEncryptedImages = False

def createTables(c):
    c.execute("DROP TABLE IF EXISTS `metadata`")
    c.execute("DROP TABLE IF EXISTS `linkAttrs`")
    c.execute("DROP TABLE IF EXISTS `dirAttrs`")
    c.execute("DROP TABLE IF EXISTS `fileAttrs`")
    c.execute("DROP TABLE IF EXISTS `linkGroups`")
    c.execute("DROP TABLE IF EXISTS `entries`")
    c.execute("DROP TABLE IF EXISTS `volumes`")

    c.execute("""
    CREATE TABLE `volumes`
        (`id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
         `name` TINYTEXT,
         `location` TINYTEXT,
         `kind` TINYTEXT,
         `totalCount` INT NOT NULL,
         `totalSize` BIGINT NOT NULL)
         CHARACTER SET UTF8
         ENGINE=MyISAM""")

    c.execute("""
    CREATE TABLE `entries`
        (`id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
         `volumeId` INT NOT NULL,
         FOREIGN KEY (`volumeId`) REFERENCES `volumes`(`id`) ON DELETE CASCADE,
         `directoryId` INT NOT NULL,
         `name` VARCHAR(4096),
         `baseName` VARCHAR(4096),
         `extension` TINYTEXT,
         `kind` INT NOT NULL,
         `permissions` INT,
         `owner` INT,
         `group` INT,
         `created` DATETIME,
         `dataModified` DATETIME,
         `attrsModified` DATETIME,
         `dataAccessed` DATETIME,
         `volumePath` VARCHAR(4096))
         CHARACTER SET UTF8
         ENGINE=MyISAM""")

    c.execute("""
    CREATE TABLE `linkGroups`
        (`id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY)
         CHARACTER SET UTF8
         ENGINE=MyISAM""")

    c.execute("""
    CREATE TABLE `fileAttrs`
        (`id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
         `entryId` INT NOT NULL,
         FOREIGN KEY (`entryId`) REFERENCES `entries`(`id`) ON DELETE CASCADE,
         `linkGroupId` INT,
         FOREIGN KEY (`linkGroupId`) REFERENCES `linkGroups`(`id`) ON DELETE SET NULL,
         `size` BIGINT NOT NULL,
         `encoding` TINYTEXT)
         CHARACTER SET UTF8
         ENGINE=MyISAM""")

    c.execute("""
    CREATE TABLE `dirAttrs`
        (`id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
         `entryId` INT NOT NULL,
         FOREIGN KEY (`entryId`) REFERENCES `entries`(`id`) ON DELETE CASCADE,
         `thisCount` INT NOT NULL,
         `thisSize` BIGINT NOT NULL,
         `totalCount` INT NOT NULL,
         `totalSize` BIGINT NOT NULL)
         CHARACTER SET UTF8
         ENGINE=MyISAM""")

    c.execute("""
    CREATE TABLE `linkAttrs`
        (`id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
         `entryId` INT NOT NULL,
         FOREIGN KEY (`entryId`) REFERENCES `entries`(`id`) ON DELETE CASCADE,
         `targetId` INT NOT NULL,
         FOREIGN KEY (`targetId`) REFERENCES `entries`(`id`) ON DELETE RESTRICT)
         CHARACTER SET UTF8
         ENGINE=MyISAM""")

    c.execute("""
    CREATE TABLE `metadata`
        (`id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
         `entryId` INT NOT NULL,
         FOREIGN KEY (`entryId`) REFERENCES `entries`(`id`) ON DELETE CASCADE,
         `metadataId` INT,
         FOREIGN KEY (`metadataId`) REFERENCES `metadata`(`id`) ON DELETE CASCADE,
         `name` TEXT,
         `type` INT NOT NULL,
         `textValue` TEXT,
         `intValue` INT,
         `dateValue` DATETIME,
         `blobValue` BLOB)
         CHARACTER SET UTF8
         ENGINE=MyISAM""")

def initDatabase(c, forceCreate):
    version = 0
    try:
        c.execute("USE `catalog`")
        c.execute("SELECT `version` FROM `version`")
        row = c.fetchone()
        version = row[0]
    except:
        c.execute("CREATE DATABASE IF NOT EXISTS `catalog` CHARACTER SET UTF8")
        c.execute("USE `catalog`")
        c.execute("DROP TABLE IF EXISTS `version`")
        c.execute("CREATE TABLE `version`(`version` INT NOT NULL)")
        c.execute("INSERT INTO `version` (`version`) VALUES (0)")

    if forceCreate:
        version = 0

    if version < 1:
        createTables(c)

        # Add indices for the tables
        #c.execute("ALTER TABLE `volumes` ADD UNIQUE(`name`(255))")
        #c.execute("ALTER TABLE `entries` ADD INDEX(`extension`(10))")
        #c.execute("ALTER TABLE `entries` ADD INDEX(`kind`(32))")

    if version < 1:
        version = 1
        c.execute("UPDATE `version` SET `version` = %d" % version)

########################################################################

class FileAttrs:
    entry     = None
    linkGroup = None
    size      = None
    encoding  = None

class DirAttrs:
    entry      = None
    thisCount  = 0
    thisSize   = 0
    totalCount = 0
    totalSize  = 0

class ArchiveAttrs(FileAttrs):
    dirAttrs = None
    def __init__(self):
        self.dirAttrs = DirAttrs()

class LinkAttrs:
    entry  = None
    target = None

(DIRECTORY, PLAIN_FILE, SYMBOLIC_LINK,
 PACKAGE, PACKAGE_DIRECTORY, PACKAGE_FILE,
 ARCHIVE, ARCHIVE_DIRECTORY, ARCHIVE_FILE,
 SPECIAL_FILE) = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)

def isArchiveName(fileName):
    #return re.search("\\.(Z|taz|sit|hqx)", fileName)
    return re.search("(\\.(zip|jar|7z|tgz|tbz|rar|dmg)|\\.tar(\\.gz|\\.bz2)?)$",
                     fileName)

lastMessage = ""

class Entry:
    id            = -1
    parent        = None
    parentId      = -1
    volume        = None
    path          = None                # current absolute pathname
    volumePath    = None                # path strictly within the volume
    name          = None
    baseName      = None
    extension     = None
    kind          = PLAIN_FILE
    permissions   = None
    owner         = None
    group         = None
    created       = None
    dataModified  = None
    attrsModified = None
    dataAccessed  = None
    infoRead      = False
    attrs         = None

    def __init__(self, volume = None, parent = None, path = None,
                 volumePath = None, name = None):
        self.volume     = volume
        self.volumePath = volumePath
        self.path       = path
        self.parent     = parent
        self.name       = name

        if parent:
            self.parentId = parent.id
        else:
            self.parentId = -1

        if name is not None:
            if len(name) > 0 and name[0] == '.':
                (self.baseName, self.extension) = splitext(name[1:])
                self.baseName = '.' + self.baseName
            else:
                (self.baseName, self.extension) = splitext(name)

            if len(self.extension) > 0 and self.extension[0] == '.':
                self.extension = self.extension[1:]

    def getParent(self, c):
        if self.parent: return self.parent
        if self.parentId < 0: return None

        self.parent = Entry()
        self.parent.load(c, self.parentId)

        return self.parent

    def isPlainFile(self):
        return self.kind == PLAIN_FILE
    def isSymbolicLink(self):
        return self.kind == SYMBOLIC_LINK
    def isDirectory(self):
        return self.kind == DIRECTORY
    def isPackage(self):
        return self.kind == PACKAGE
    def isArchive(self):
        return self.kind == ARCHIVE
    def isSpecialFile(self):
        return self.kind == SPECIAL_FILE

    def readInfo(self):
        info = os.lstat(self.path)

        if S_ISDIR(info[ST_MODE]):
            self.kind = DIRECTORY
            #m = re.search("\\.(app|oo3|dtBase)")
            #if m:
            #    self.kind = PACKAGE
            self.attrs = DirAttrs()
        elif S_ISLNK(info[ST_MODE]):
            self.kind = SYMBOLIC_LINK
            self.attrs = LinkAttrs()
        elif S_ISREG(info[ST_MODE]):
            if isArchiveName(self.name):
                self.kind = ARCHIVE
                self.attrs = ArchiveAttrs()
            else:
                self.kind = PLAIN_FILE
                self.attrs = FileAttrs()
            self.attrs.size = long(info[ST_SIZE])
        else:
            self.kind = SPECIAL_FILE

        self.permissions   = info[ST_MODE]
        self.owner         = info[ST_UID]
        self.group         = info[ST_GID]
        self.dataAccessed  = mx.DateTime.gmtime(info[ST_ATIME])
        self.dataModified  = mx.DateTime.gmtime(info[ST_MTIME])
        self.attrsModified = mx.DateTime.gmtime(info[ST_CTIME])

        self.infoRead = True

    def getCount(self):
        assert self.infoRead
        if self.isDirectory() or self.isPackage():
            return self.attrs.totalCount
        elif self.isArchive():
            return self.attrs.dirAttrs.totalCount
        else:
            return 1

    def getSize(self):
        assert self.infoRead
        if self.isDirectory() or self.isPackage():
            return self.attrs.totalSize
        elif self.isArchive():
            return self.attrs.dirAttrs.totalSize
        elif not self.isSpecialFile():
            return self.attrs.size
        else:
            return 0

    def scanEntries(self, c):
        if not self.isDirectory() and not self.isPackage() and \
           not self.isArchive():
            return

        attrs = self.attrs
        if self.isArchive():
            attrs = attrs.dirAttrs

        attrs.thisCount  = 0
        attrs.thisSize   = 0
        attrs.totalCount = 0
        attrs.totalSize  = 0

        entryPath = ""

        try:
            global lastMessage

            for entryName in os.listdir(self.path):
                entryPath = join(self.path, entryName)

                if re.match("/(dev|Network|automount)/", entryPath):
                    continue

                entry = createEntry(self.volume, self, entryPath,
                                    join(self.volumePath, entryName),
                                    entryName)
                entry.readInfo()
                entry.store(c)

                if entry.isPlainFile():
                    attrs.thisCount += 1
                    attrs.thisSize  += entry.getSize()

                elif not entry.isSymbolicLink():
                    if entry.isArchive() and entry.getSize() > (5 * 1024 * 1024):
                        print "Scanning", entry.volumePath
                        lastMessage = ""
                    else:
                        parts = entry.volumePath.split("/")
                        if parts > 3:
                            parts = parts[0:3]
                        theMessage = apply(join, parts)
                        if theMessage != lastMessage:
                            print "Scanning", theMessage
                            lastMessage = theMessage

                    entry.scanEntries(c)

                    attrs.totalCount += entry.getCount()
                    attrs.totalSize  += entry.getSize()

        except Exception, msg:
            print "Failed to index %s:" % (entryPath or self.path), msg

        attrs.totalCount += attrs.thisCount
        attrs.totalSize  += attrs.thisSize

    def load(self, c, id):
        self.id = id

        result = c.execute("""
          SELECT `volumeId`, `directoryId`, `name`, `baseName`, `extension`,
                 `kind`, `permissions`, `owner`, `group`, `created`,
                 `dataModified`, `attrsModified`, `dataAccessed`,
                 `volumePath`
          FROM `entries` WHERE `id` = %s""", (self.id,))

        if result:
            (volumeId, parentId, name, baseName, extension,
             kind, permissions, owner, group, created,
             dataModified, attrsModified, dataAccessed,
             volumePath) = c.fetchone()
            
            self.volumeId      = volumeId
            self.parent        = None
            self.parentId      = parentId
            self.name          = name
            self.baseName      = baseName
            self.extension     = extension
            self.kind          = kind
            self.permissions   = permissions
            self.owner         = owner
            self.group         = group
            self.created       = created
            self.dataModified  = dataModified
            self.attrsModified = attrsModified
            self.dataAccessed  = dataAccessed
            self.volumePath    = volumePath

    def store(self, c):
        if self.id == -1:
            c.execute("""
              INSERT INTO `entries`
                (`volumeId`, `directoryId`, `name`, `baseName`, `extension`,
                 `kind`, `permissions`, `owner`, `group`, `created`,
                 `dataModified`, `attrsModified`, `dataAccessed`,
                 `volumePath`)
              VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s)""",
                (self.volume.id, self.parentId, self.name, self.baseName,
                 self.extension, self.kind, self.permissions, self.owner,
                 self.group, self.created, self.dataModified, self.attrsModified,
                 self.dataAccessed, self.volumePath))

            self.id = c.lastrowid
        else:
            c.execute("""
              UPDATE `entries` SET
                `volumeId`      = %s,
                `directoryId`   = %s,
                `name`          = %s,
                `baseName`      = %s,
                `extension`     = %s,
                `kind`          = %s,
                `permissions`   = %s,
                `owner`         = %s,
                `group`         = %s,
                `created`       = %s,
                `dataModified`  = %s,
                `attrsModified` = %s,
                `dataAccessed`  = %s,
                `volumePath`    = %s)
              WHERE `id` = %s""",
                (self.volume.id, self.parentId, self.name, self.baseName,
                 self.extension, self.kind, self.permissions, self.owner,
                 self.group, self.created, self.dataModified, self.attrsModified,
                 self.dataAccessed, self.volumePath, self.id))

            c.execute("DELETE FROM `fileAttrs` WHERE `entryId` = %s", (self.id,))
            c.execute("DELETE FROM `linkAttrs` WHERE `entryId` = %s", (self.id,))
            c.execute("DELETE FROM `dirAttrs` WHERE `entryId` = %s", (self.id,))

        if self.isPlainFile() or self.isArchive():
            c.execute("""
              INSERT INTO `fileAttrs`
                (`entryId`, `linkGroupId`, `size`, `encoding`)
              VALUES (%s, %s, %s, %s)""",
                (self.id, None, self.attrs.size, self.attrs.encoding))
        elif self.isSymbolicLink():
            # jww (2007-02-24): What if the target hasn't been stored yet?
            if False:
                c.execute("""
                  INSERT INTO `linkAttrs` (`entryId`, `targetId`)
                  VALUES (%s, %s)""", (self.id, self.attrs.target.id))

        if self.isDirectory() or self.isPackage() or self.isArchive():
            attrs = self.attrs
            if self.isArchive():
                attrs = attrs.dirAttrs
            c.execute("""
              INSERT INTO `dirAttrs`
                (`entryId`, `thisCount`, `thisSize`, `totalCount`, `totalSize`)
              VALUES (%s, %s, %s, %s, %s)""",
                (self.id, attrs.thisCount, attrs.thisSize, attrs.totalCount, attrs.totalSize))

    def drop(self, c):
        # jww (2007-08-05): What about the link group?
        c.execute("DELETE FROM `fileAttrs` WHERE `entryId` = %s", (self.id,))
        c.execute("DELETE FROM `linkAttrs` WHERE `entryId` = %s", (self.id,))
        c.execute("DELETE FROM `dirAttrs` WHERE `entryId` = %s", (self.id,))
        c.execute("DELETE FROM `entries` WHERE `id` = %s", (self.id,))
        self.id = -1

def createEntry(volume, parent, path, volumePath, name):
    args = (volume, parent, path, volumePath, name)

    ext  = splitext(name[1:])[1]
    if ext == ".zip" or ext == ".jar":
        return apply(ZipFileEntry, args)
    elif ext == ".7z":
        return apply(SevenZipFileEntry, args)
    elif ext == ".rar":
        return apply(RarFileEntry, args)
    elif ext == ".dmg":
        return apply(DiskImageEntry, args)
    elif re.search("(\\.tar(\\.gz|\\.bz2)?|\\.tgz|\\.tbz)$", name):
        return apply(TarFileEntry, args)
    else:
        return apply(Entry, args)
    

def findEntryByVolumePath(c, volume, volPath):
    if c.execute("""SELECT `id` FROM `entries`
                    WHERE `volumeId` = %s AND `volumePath` = %s""",
                    (volume.id, volPath)):
        data = c.fetchone()
        if data:
            (id,) = data

            entry = Entry()
            entry.id     = id
            entry.volume = volume

            entry.load(c, entry.id)

            return entry

    return None

def processEntriesResult(c, reporter):
    entries = []

    data = c.fetchone()
    while data:
        (volId, volName, volLocation, volKind, id) = data

        vol = Volume(None, volName, volLocation, volKind)
        vol.id = volId

        entry = Entry()
        entry.id = id
        entry.volume = vol
        entries.append(entry)

        data = c.fetchone()

    for entry in entries:
        entry.load(c, entry.id)
        reporter(entry)

    return entries

def findEntriesByName(c, name, reporter):
    containsPercent = re.search('%', name)
    print "step 1"
    if c.execute("""
      SELECT v.`id`, v.`name`, v.`location`, v.`kind`, e.`id`
      FROM `volumes` as v, `entries` as e
      WHERE e.`name` %s %%s AND e.`volumeId` = v.`id`""" %
                 (containsPercent and "LIKE" or "="), (name,)):
        print "step 2"
        return processEntriesResult(c, reporter)
    print "step 3"

def findEntriesByPath(c, path, reporter):
    if c.execute("""
      SELECT v.`id`, v.`name`, v.`location`, v.`kind`, e.`id`
      FROM `volumes` as v, `entries` as e
      WHERE e.`volumePath` LIKE %s AND e.`volumeId` = v.`id`""", (path,)):
        return processEntriesResult(c, reporter)

class ZipFileEntry(Entry):              # a .zip archive file
    def __init__(self, volume, parent, path, volumePath, name):
        Entry.__init__(self, volume, parent, path, volumePath, name)

    def readStoredInfo(self, entry, info):
        entry.kind  = PLAIN_FILE
        entry.attrs = FileAttrs()

        entry.attrs.size    = info.file_size
        entry.dataModified  = apply(mx.DateTime.DateTime, info.date_time)

        entry.infoRead = True
        self.infoRead = True

    def scanEntries(self, c):
        assert self.isArchive()

        attrs = self.attrs
        attrs = attrs.dirAttrs

        attrs.thisCount  = 0
        attrs.thisSize   = 0
        attrs.totalCount = 0
        attrs.totalSize  = 0

        thisZipFile = None

        try:
            thisZipFile = zipfile.ZipFile(self.path)

            for info in thisZipFile.infolist():
                entry = Entry(self.volume, self, join(self.path, info.filename),
                              join(self.volumePath, info.filename),
                              info.filename)
                self.readStoredInfo(entry, info)
                entry.store(c)

                attrs.thisCount += 1
                attrs.thisSize  += info.file_size
        except Exception, msg:
            print "Failed to index %s:" % self.path, msg

        if thisZipFile:
            thisZipFile.close()

        attrs.totalCount += attrs.thisCount
        attrs.totalSize  += attrs.thisSize

class SevenZipFileEntry(Entry):              # a .7z archive file
    def readStoredInfo(self, entry, line):
        entry.kind  = PLAIN_FILE
        entry.attrs = FileAttrs()

        entry.attrs.size   = long(line[26:38])
        entry.dataModified = mx.DateTime.strptime(line[0:19], "%Y-%m-%d %H:%M:%S")

        entry.infoRead = True
        self.infoRead = True

    def scanEntries(self, c):
        assert self.isArchive()

        attrs = self.attrs
        attrs = attrs.dirAttrs

        attrs.thisCount  = 0
        attrs.thisSize   = 0
        attrs.totalCount = 0
        attrs.totalSize  = 0

        pipe = None
        
        try:
            pipe = Popen("7za l \"%s\"" % self.path, shell = True,
                         stdout = PIPE).stdout

            for line in pipe.readlines():
                if not re.match("20", line):
                    continue

                filename = line[53:-1]

                entry = Entry(self.volume, self, join(self.path, filename),
                              join(self.volumePath, filename), filename)
                self.readStoredInfo(entry, line)
                entry.store(c)

                attrs.thisCount += 1
                attrs.thisSize  += entry.attrs.size
        except Exception, msg:
            print "Failed to index %s:" % self.path, msg

        if pipe:
            pipe.close()

        attrs.totalCount += attrs.thisCount
        attrs.totalSize  += attrs.thisSize

class RarFileEntry(Entry):              # a .rar archive file
    def scanEntries(self, c):
        assert self.isArchive()

        attrs = self.attrs
        attrs = attrs.dirAttrs

        attrs.thisCount  = 0
        attrs.thisSize   = 0
        attrs.totalCount = 0
        attrs.totalSize  = 0

        pipe = None
        insideListing = False

        try:
            pipe = Popen("rar lt \"%s\"" % self.path, shell = True,
                         stdout = PIPE).stdout

            lines = pipe.readlines()
            i = 0
            while i < len(lines):
                if not insideListing:
                    if re.match("-----", lines[i]):
                        insideListing = True
                else:
                    if re.match("-----", lines[i]):
                        insideListing = False
                        i += 1
                        continue

                    items = lines[i].strip().split()
                    i += 1

                    while len(items) > 10:
                        begin = items[0] + " " + items[1]
                        items = items[1:]
                        items[0] = begin

                    filename = items[0]

                    entry = Entry(self.volume, self, join(self.path, filename),
                                  join(self.volumePath, filename), filename)

                    entry.kind  = PLAIN_FILE
                    entry.attrs = FileAttrs()

                    entry.attrs.size   = long(items[1])
                    entry.dataModified = mx.DateTime.strptime(items[4] + " " + items[5],
                                                              "%d-%m-%y %H:%M")

                    entry.infoRead = True
                    self.infoRead = True
                    entry.store(c)

                    attrs.thisCount += 1
                    attrs.thisSize  += entry.attrs.size

                i += 1
        except Exception, msg:
            print "Failed to index %s:" % self.path, msg

        if pipe:
            pipe.close()

        attrs.totalCount += attrs.thisCount
        attrs.totalSize  += attrs.thisSize

class TarFileEntry(Entry):              # an (un)compressed .tar archive file
    def readStoredInfo(self, entry, info):
        # jww (2007-03-26): Parse out symbolic links here
        entry.kind  = PLAIN_FILE
        entry.attrs = FileAttrs()

        entry.attrs.size   = info.size
        entry.permissions  = info.mode
        entry.owner        = info.uid
        entry.group        = info.gid
        entry.dataModified = mx.DateTime.gmtime(info.mtime)

        entry.infoRead = True
        self.infoRead = True

    def scanEntries(self, c):
        assert self.isArchive()

        attrs = self.attrs
        attrs = attrs.dirAttrs

        attrs.thisCount  = 0
        attrs.thisSize   = 0
        attrs.totalCount = 0
        attrs.totalSize  = 0

        thisTarFile = None

        try:
            thisTarFile = tarfile.open(self.path)

            for info in thisTarFile.getmembers():
                entry = Entry(self.volume, self, join(self.path, info.name),
                              join(self.volumePath, info.name), info.name)
                self.readStoredInfo(entry, info)
                entry.store(c)

                attrs.thisCount += 1
                attrs.thisSize  += info.size
        except Exception, msg:
            print "Failed to index %s:" % self.path, msg

        if thisTarFile:
            thisTarFile.close()

        attrs.totalCount += attrs.thisCount
        attrs.totalSize  += attrs.thisSize

class DiskImageEntry(Entry):              # a .dmg file
    def scanEntries(self, c):
        assert self.isArchive()

        attrs = self.attrs
        attrs = attrs.dirAttrs

        attrs.thisCount  = 0
        attrs.thisSize   = 0
        attrs.totalCount = 0
        attrs.totalSize  = 0

        pipe = None
        path = None
        skip = False
        
        try:
            pipe = Popen("hdiutil imageinfo \"%s\"" % self.path,
                         shell = True, stdout = PIPE).stdout

            for line in pipe.readlines():
                if re.search("Software License Agreement: true", line) or \
                   (not openEncryptedImages and re.search("Encrypted: true", line)):
                    skip = True
                    pipe.close()
                    return

            if not skip:
                pipe = Popen("hdiutil attach \"%s\" -readonly %s" %
                             (self.path, "-mountrandom /tmp -noverify -noautofsck"),
                             shell = True, stdout = PIPE).stdout

                for line in pipe.readlines():
                    match = re.search("(/tmp/.+)", line)
                    if match:
                        path = match.group(1)
                        break

        except Exception, msg:
            print "Failed to index %s:" % self.path, msg
            
        if pipe:
            pipe.close()

        try:
            if path:
                dirEntry = Entry(self.volume, self, path, self.volumePath, self.name)
                dirEntry.readInfo()
                dirEntry.id = self.id   # spoof id, to skip the "man in the middle"
                dirEntry.scanEntries(c)

                attrs.thisCount += dirEntry.getCount()
                attrs.thisSize  += dirEntry.getSize()

            attrs.totalCount += attrs.thisCount
            attrs.totalSize  += attrs.thisSize

        finally:
            p = Popen("hdiutil detach \"%s\"" % path, shell = True, stdout = PIPE)
            sts = os.waitpid(p.pid, 0)
            p.close()

class Volume:
    id         = -1
    topEntry   = None
    name       = "unnamed"
    location   = "unknown location"
    kind       = "unknown kind"
    totalCount = 0
    totalSize  = 0

    def __init__(self, path, name, location, kind):
        self.path     = path and normpath(path)
        self.name     = name
        self.location = location
        self.kind     = kind

    def clearEntries(self, c):
        print "Clearing any previous entries for volume %s" % self.name

        c.execute("""SELECT `id` FROM `volumes` WHERE `name` = %s""", self.name)
        data = c.fetchone()
        assert data
        volumeId = data[0]

        c.execute("""SELECT `id` FROM `entries` WHERE `volumeId` = %s""", (volumeId,))
        data = c.fetchone()
        while data:
            entryId = data[0]

            c.execute("DELETE FROM `fileAttrs` WHERE `entryId` = %s", (entryId,))
            c.execute("DELETE FROM `linkAttrs` WHERE `entryId` = %s", (entryId,))
            c.execute("DELETE FROM `dirAttrs` WHERE `entryId` = %s", (entryId,))

            data = c.fetchone()

        c.execute("DELETE FROM `entries` WHERE `volumeId` = %s", (volumeId,))
        c.execute("""DELETE FROM `volumes` WHERE `id` = %s""", (volumeId,))

    def addSizes(self, entry):
        pass

    def removeSizes(self, entry):
        pass

    def catalogEntry(self, path, options):
        print "A", path

        volPath = normpath(path)[len(self.path) + 1 :]

        parentPath = dirname(volPath)
        if parentPath:
            parent = findEntryByVolumePath(options['data'], self, parentPath)
            assert parent
        else:
            parent = None

        entry = createEntry(self, parent, path, volumePath = volPath,
                            name = basename(path))
        entry.readInfo()
        entry.store(options['data'])
        if not entry.isDirectory():
            entry.scanEntries(options['data'])

        self.addSizes(entry)           # update all parents and volume
        return True

    def updateEntry(self, path, options):
        volPath = normpath(path)[len(self.path) + 1 :]

        entry = findEntryByVolumePath(options['data'], self, volPath)
        assert entry

        self.removeSizes(entry)

        entry.readInfo()
        entry.scanEntries(options['data'])
        entry.store(options['data'])

        self.addSizes(entry)           # update all parents and volume
        return True

    def removeEntry(self, path, options):
        volPath = normpath(path)[len(self.path) + 1 :]

        entry = findEntryByVolumePath(options['data'], self, volPath)
        assert entry

        self.removeSizes(entry)

        entry.drop()
        return True

    def scanEntries(self, c):
        if alwaysRescan and self.id > 0:
            self.clearEntries(c)
            self.id = -1

        if self.id < 0:
            c.execute("""
              INSERT INTO `volumes`
                  (`name`, `location`, `kind`, `totalCount`, `totalSize`)
              VALUES (%s, %s, %s, 0, 0)""", (self.name, self.location, self.kind))
            self.id = c.lastrowid

        if alwaysRescan:
            self.topEntry = Entry(self, None, self.path, "", "")
            self.topEntry.readInfo()

            if self.topEntry.isDirectory():
                self.topEntry.scanEntries(c)
                self.topEntry.store(c)
                self.totalCount = self.topEntry.attrs.totalCount
                self.totalSize  = self.topEntry.attrs.totalSize
            elif self.topEntry.isArchive():
                self.topEntry.scanEntries(c)
                self.topEntry.store(c)
                self.totalCount = self.topEntry.attrs.dirAttrs.totalCount
                self.totalSize  = self.topEntry.attrs.dirAttrs.totalSize
            else:
                print "Volume is neither a directory nor an archive"
        else:
            supportDir = expanduser('~/Library/Application Support/DiskCataloger')

            options = {
                'directory':       self.path,
                'database':        join(supportDir, "%s.dat" % self.name),
                'mtime':           True,
                'dryrun':          True,
                'onFileAdded':     self.catalogEntry,
                'onFileChanged':   self.updateEntry,
                'onFileRemoved':   self.removeEntry,
                'onFilePastLimit': None,
                'data':            c
            }
            cleanup.scanDirectory(**options)

        c.execute("""
          UPDATE `volumes` SET `totalCount` = %s, `totalSize` = %s WHERE `id` = %s""",
            (self.totalCount, self.totalSize, self.id))
        self.id = c.lastrowid

        print "Volume", self.path, "total count is", self.totalCount
        print "Volume", self.path, "total size  is", self.totalSize

def findVolumeByName(c, name):
    result = c.execute("""
      SELECT `id`, `location`, `kind`, `totalCount`, `totalSize`
      FROM `volumes` WHERE `name`=%s""", (name,))
    if result:
        (id, location, kind, totalCount, totalSize) = c.fetchone()

        vol = Volume(None, name, location, kind)
        vol.id         = id
        vol.totalCount = totalCount
        vol.totalSize  = totalSize

        return vol

    return None

########################################################################

if len(sys.argv) < 2:
    sys.exit(1)

conn = MySQLdb.connect(host = "localhost", user = "johnw", passwd = "0M^o72WjmZ4dj7t7")

cursor = conn.cursor()
cursor.execute("SET NAMES UTF8")
cursor.execute("SET CHARACTER SET UTF8")
cursor.execute("SET character_set_connection=UTF8")
cursor.execute("SET character_set_server=UTF8")

command = sys.argv[1]

def print_result(entry):
    print entry.volume.name, "->", entry.volumePath
    sys.stdout.flush()

if command == "name":
    initDatabase(cursor, False)
    for name in sys.argv[2:]:
        findEntriesByName(cursor, name, print_result)

elif command == "path" or command == "find":
    initDatabase(cursor, False)
    for path in sys.argv[2:]:
        findEntriesByPath(cursor, path, print_result)

elif command == "index":
    wipeDatabase = False

    path = "path"
    name = "name"
    kind = "kind"
    location = "location"

    args = sys.argv[1:]
    while len(args) > 0:
        if args[0] == "--reset":
            wipeDatabase = True
        elif args[0] == "--path":
            path = args[1]
            args = args[1:]
        elif args[0] == "--name":
            name = args[1]
            args = args[1:]
        elif args[0] == "--location":
            location = args[1]
            args = args[1:]
        elif args[0] == "--kind":
            kind = args[1]
            args = args[1:]
        elif args[0] == "--include-encrypted":
            openEncryptedImages = True
        args = args[1:]

    initDatabase(cursor, wipeDatabase)

    if path == "path":
        print "The volume path has not been specified"
        sys.exit(1)

    vol = findVolumeByName(cursor, name)
    if not vol:
        vol = Volume(path, name, location, kind)
    else:
        vol.path = normpath(path)

    vol.scanEntries(cursor)

    conn.commit()
    conn.close()
