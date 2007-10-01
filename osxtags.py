appscript = None
try:
    import appscript
    import mactypes
except:
    pass


def comment(path):
    if not appscript:
        return False

    finder = appscript.app('Finder')
    alias  = mactypes.Alias(path)

    try:
        return finder.files[alias].comment.get()
    except:
        return ""

def setcomment(path, comment):
    if not appscript:
        return False

    finder = appscript.app('Finder')
    alias  = mactypes.Alias(path)

    try:
        return finder.files[alias].comment.set(comment)
    except:
        return ""


def hastags(path, tags):
    if not appscript:
        return False

    for tag in tags:
        if tag not in comment(path):
            return False
    return True

def hastag(path, *tags):
    return hastags(path, tags)


def addtags(path, *tags):
    if not appscript:
        return False

    finder = appscript.app('Finder')
    alias  = mactypes.Alias(path)

    comment = ""
    try:
        comment = finder.files[alias].comment.get()
    except:
        return False

    for tag in tags:
        try:
            if tag not in comment:
                if comment:
                    finder.files[alias].comment.set(comment + ' ' + tag)
                else:
                    finder.files[alias].comment.set(tag)
        except:
            pass

def addtag(path, *tags):
    return addtags(path, tags)


def deltags(path, *tags):
    if not appscript:
        return False

    finder = appscript.app('Finder')
    alias  = mactypes.Alias(path)

    comment = ""
    try:
        comment = finder.files[alias].comment.get()
    except:
        pass

    for tag in tags:
        comment = re.sub("\\s*%s" % tag, "", comment)

    try:
        finder.files[alias].comment.set(comment)
    except:
        pass

def deltag(path, *tags):
    return deltags(path, tags)
