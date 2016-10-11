#!/usr/bin/python3
""" tex2htm.py - A LaTeX to HTML conversion utility
"""
import os
import sys
import re
from collections import defaultdict


# TODO: Split paragraphs
# TODO: Import code


# Some global variables
environment_handlers = defaultdict(lambda: process_env_default)
command_handlers = defaultdict(lambda: process_cmd_default)

named_entities = {'chap': 'Chapter',
                  'sec': 'Section',
                  'thm': 'Theorem',
                  'lem': 'Lemma',
                  'fig': 'Figure',
                  'figure': 'Figure',
                  'eq': 'Equation',
                  'exc': 'Exercise',
                  'proof': 'Proof'}

# Map LaTeX labels on to HTML id's
label_map = dict()

# Collections of things to warn about after processing is done
undefined_labels = set()
unprocessed_commands = set()
unprocessed_environments = set()

# Math mode
MATH = 1

#
# Utilities
#
def abort(msg, status=-1):
    sys.stderr.write(msg + '\n')
    sys.exit(status)

def warn(msg, level=0):
    sys.stderr.write("Warning: {}\n".format(msg))

def match_parens(tex, i, open, close):
    # TODO: Handle escape sequences
    di = defaultdict(int, {open: 1, close: -1})
    if i == len(tex): return i
    try:
        d = di[tex[i]]
        j = i+d
        while d > 0:
            d += di[tex[j]]
            j+=1
        return j
    except IndexError:
        abort("Couldn't match parenthesis:\n... "
              + tex[max(0,i-25):min(len(tex,i+25))])


#
# Preprocessing functions
#
def preprocess_hashes(subtex):
    """Prevents percents inside hashes from being treated as comments"""
    blocks = list()
    rx = re.compile('#([^#]*)#', re.M|re.S)
    lastidx = 0
    for m in rx.finditer(subtex):
        blocks.append(subtex[lastidx:m.start()])
        lastidx = m.end()
        blocks.append(re.sub(r'(^|[^\\])%', r'\1\%', m.group(0)))
    blocks.append(subtex[lastidx:])
    return "".join(blocks)

def strip_comments(tex):
    lines = tex.splitlines()
    nulled = set()
    for i in range(len(lines)):
        if len(lines[i]) > 0:
            lines[i] = re.sub(r'(^|[^\\])\%.*$', r'\1', lines[i])
            if len(lines[i]) == 0:
                nulled.add(i)
    lines = [lines[i] for i in range(len(lines)) if i not in nulled]
    return "\n".join(lines)


#
# Label and Refeference Handling
# TODO: Add numbers to environments and sections
def process_labels(tex):
    headings = ['chapter'] + ['sub'*i + 'section' for i in range(4)]
    reh = r'(' + '|'.join(headings) + r'){(.+?)}'
    environments = ['thm', 'lem', 'exc', 'figure', 'equation']
    ree = r'begin{(' + '|'.join(environments) + r')}'
    rel = r'(\w+)label{(.+?)}'
    bigone = r'\\({})|\\({})|\\({})|\\(caption)'.format(reh, ree, rel)
    rx = re.compile(bigone)

    sec_ctr = [0]*(len(headings)+1)
    env_ctr = [0]*len(environments)
    blocks = []
    lastlabel = None
    lastidx = 0
    m = rx.search(tex, lastidx)
    while m:
        blocks.append(tex[lastidx:m.start()])
        lastidx = m.start()
        cmd = next_command(tex, lastidx)
        lastidx = cmd.end
        if m.group(2):
            # This is a sectioning command (chapter, subsection,...)
            name = m.group(2)
            i = headings.index(name)
            if i == 0:
                env_ctr = [0]*len(env_ctr)
            sec_ctr[i:] = [sec_ctr[i]+1]+[0]*(len(headings)-i-1)
            number = ".".join([str(x) for x in sec_ctr[:i+1]])
            idd = "{}:{}".format(name, number)
            lastlabel = idd
            blocks.append("<a id='{}'></a>".format(idd))

            title = '{}&emsp;{}'.format(number, cmd.args[0])
            blocks.append(r'\{}{{{}}}'.format(name, title))

        elif m.group(5):
            # This is an environment (thm, lem, ...)
            name = m.group(5)
            i = environments.index(name)
            env_ctr[i] += 1
            number = "{}.{}".format(sec_ctr[0], env_ctr[i])
            idd = "{}:{}".format(name, number)
            lastlabel = idd
            blocks.append("<a id='{}'></a>".format(idd))

            nicename = named_entities[name]
            title = '{}&nbsp;{}'.format(nicename, number)
            blocks.append(r'\begin{{{}}}[{}]'.format(name, title))

        elif m.group(7):
            # This is a labelling command (\thmlabel, \seclabel,...)
            label = "{}:{}".format(m.group(7), m.group(8))
            label_map[label] = lastlabel

        elif m.group(9):
            # This is a caption command
            name = 'figure'
            i = environments.index(name)
            number = "{}.{}".format(sec_ctr[0], env_ctr[i])
            idd = "{}:{}".format(name, number)
            lastlabel = idd

            title = '<span class="title">Figure&nbsp;{}</span>'.format(number)
            text = '{}&emsp;{}'.format(title, cmd.args[0])
            blocks.append(r'\caption{{{}}}'.format(text))

        m = rx.search(tex, lastidx)
    blocks.append(tex[lastidx:])
    return "".join(blocks)

#
# LaTeX commands
# TODO: Handle footnotes correctly
class command(object):
    def __init__(self, name, optargs, args, start, end):
        self.name = name
        self.optargs = optargs
        self.args = args
        self.start = start
        self.end = end

    def __repr__(self):
        return "command({},{},{},{},{})".format(repr(self.name), repr(self.optargs),
                repr(self.args), repr(self.start), repr(self.end))


def chomp_args(tex, pos):
    optargs = []
    j = pos
    k = match_parens(tex, j, '[', ']')
    while k > j:
        optargs.append(tex[j+1:k-1])
        j = k
        k = match_parens(tex, j, '[', ']')
    args = []
    k = match_parens(tex, j, '{', '}')
    while k > j:
        args.append(tex[j+1:k-1])
        j = k
        k = match_parens(tex, j, '{', '}')
    return (optargs, args, pos, j)


def next_command(tex, pos):
    """Get the next command in tex that occurs at or after pos"""
    rx = re.compile(r'\\([a-zA-Z0-9]+)')
    m = rx.search(tex, pos)
    if m:
        optargs, args, t, j = chomp_args(tex, m.end())
        cmd = command(m.group(1), optargs, args, m.start(), j)
        return cmd
    return None


def setup_command_handlers():
    command_handlers['chapter'] =  process_chapter_cmd
    command_handlers['section'] =  process_section_cmd
    command_handlers['subsection'] =  process_subsection_cmd
    command_handlers['subsubsection'] =  process_subsubsection_cmd
    command_handlers['paragraph'] =  process_paragraph_cmd
    command_handlers['emph'] =  process_emph_cmd
    command_handlers['caption'] =  process_caption_cmd
    command_handlers['includegraphics'] =  process_graphics_cmd
    command_handlers['codeimport'] =  process_codeimport_cmd
    command_handlers['javaimport'] =  process_codeimport_cmd
    command_handlers['cite'] =  lambda t, c, m: ['[{}]'.format(c.args[0])]
    command_handlers['ldots'] =  process_dots_cmd

    worthless = ['newlength', 'setlength', 'addtolength', 'vspace', 'index',
                 'cpponly', 'cppimport', 'pcodeonly', 'pcodeimport', 'qedhere',
                 'end', 'hline', 'noindent']
    for c in worthless:
        command_handlers[c] = process_cmd_worthless

    labeltypes = ['', 'fig', 'eq', 'thm', 'lem', 'exc', 'chap', 'sec']
    for t in labeltypes:
        command_handlers[t + 'label'] = process_cmd_worthless
        command_handlers[t + 'ref'] = process_ref_cmd

    strip = ['javaonly', 'notpcode']
    for c in strip:
        command_handlers[c] = process_cmd_strip

    mathbreakers = ['mbox', 'text']
    for c in mathbreakers:
        command_handlers[c] = process_mathbreaker_cmd

def process_cmd_default(tex, cmd, mode):
    """ By default, we just pass commands through untouched """
    if not mode & MATH:
        unprocessed_commands.add(cmd.name)
    return process_cmd_passthru(tex, cmd, mode)

def process_cmd_passthru(tex, cmd, mode):
    blocks = [r'\{}'.format(cmd.name)]
    for a in cmd.optargs:
        blocks.append('[')
        blocks.extend(process_recursively(a, mode))
        blocks.append(']')
    for a in cmd.args:
        blocks.append('{')
        blocks.extend(process_recursively(a, mode))
        blocks.append('}')
    return blocks

def process_cmd_worthless(tex, cmd, mode):
    """ Worthless commands and arguments are completely completely removed """
    return ['']

def process_cmd_strip(text, cmd, mode):
    """ These commands have their arguments processed """
    return process_recursively(cmd.args[0], mode)

def process_mathbreaker_cmd(text, cmd, mode):
    """ These command break out of math mode """
    return process_cmd_passthru(text, cmd, mode & ~MATH)

def process_dots_cmd(tex, cmd, mode):
    """ Various kinds of ellipses """
    if mode & MATH:
        return process_cmd_default(tex, cmd, mode)
    else:
        mapper = { 'ldots': '&hellip;',
                'vdots': '&#x22ee;' }
        if cmd.name in mapper:
            return [ mapper[cmd.name] ]
    warn("Unrecognized non-math dots: {}".format(cmd.name))
    return [ '?' ]

def process_chapter_cmd(text, cmd, mode):
    blocks = list()
    blocks.append('<div class="chapter">')
    blocks.extend(process_recursively(cmd.args[0], mode))
    blocks.append('</div><!-- chapter -->')
    return blocks

def process_section_cmd(text, cmd, mode):
    blocks = ["<h1>"]
    blocks.extend(process_recursively(cmd.args[0], mode))
    blocks.append("</h1>")
    return blocks

def process_subsection_cmd(text, cmd, mode):
    blocks = ["<h2>"]
    blocks.extend(process_recursively(cmd.args[0], mode))
    blocks.append("</h2>")
    return blocks

def process_subsubsection_cmd(text, cmd, mode):
    blocks = ["<h2>"]
    blocks.extend(process_recursively(cmd.args[0], mode))
    blocks.append("</h2>")
    return blocks

def process_paragraph_cmd(text, cmd, mode):
    blocks = ['<div class="paragraph_title">']
    blocks.extend(process_recursively(cmd.args[0], mode))
    blocks.append("</div><!-- paragraph_title -->")
    return blocks

def process_emph_cmd(text, cmd, mode):
    blocks = ["<em>"]
    blocks.extend(process_recursively(cmd.args[0], mode))
    blocks.append("</em>")
    return blocks

def process_caption_cmd(text, cmd, mode):
    blocks = ['<div class="caption">']
    blocks.extend(process_recursively(cmd.args[0], mode))
    blocks.append("</div><!-- caption -->")
    return blocks

def process_graphics_cmd(text, cmd, mode):
    return ['<img src="{}.svg"/>'.format(cmd.args[0], mode)]

def process_codeimport_cmd(tex, cmd, mode):
    blocks = ['<div class="codeimport">']
    blocks.extend(process_recursively(cmd.args[0], mode))
    blocks.append("</div><!-- codeimport -->")
    return blocks

def process_ref_cmd(tex, cmd, mode):
    name = re.sub(r'^(.*)ref', r'\1', cmd.name).lower()
    texlabel = "{}:{}".format(name, cmd.args[0])
    if texlabel in label_map:
        htmllabel = label_map[texlabel]
        num = htmllabel[htmllabel.find(':')+1:]
    else:
        undefined_labels.add(texlabel)
        htmllabel = 'REFERR'
        num = '??'

    if name in named_entities:
        html = '<a href="#{}">{}&nbsp;{}</a>'.format(htmllabel,
                  named_entities[name], num)
    else:
        html = '<a href="#{}">{}&nbsp;{}</a>'.format(htmllabel, name, num)
    return [ html ]
#
# LaTex environments
#
class environment(object):
    def __init__(self, name, optargs, args, content, start, end):
        self.name = name
        self.optargs = optargs
        self.args = args
        self.content = content
        self.start = start
        self.end = end

    def __repr__(self):
        return "environment({},{},{},{},{})".format(repr(self.name),
                                                    repr(self.optargs),
                                                    repr(self.args),
                                                    repr(self.content),
                                                    repr(self.start),
                                                    repr(self.end))

def setup_environment_handlers():
    environment_handlers['dollar'] = process_inlinemath_env
    environment_handlers['tabular'] = process_tabular_env
    environment_handlers['hash'] = process_hash_env
    displaymaths = ['equation', 'equation*', 'align', 'align*', 'eqnarray*']
    for name in displaymaths:
        environment_handlers[name] = process_displaymath_env
    passthroughs = ['array', 'cases']
    for name in passthroughs:
        environment_handlers[name] = process_env_passthru
    lists = ['itemize', 'enumerate', 'list']
    for name in lists:
        environment_handlers[name] = process_list_env
    thmlike = ['thm', 'lem', 'exc', 'proof']
    for name in thmlike:
        environment_handlers[name] = process_theoremlike_env

def get_environment(tex, begincmd):
    """ Get an environment that is started by begincmd.

        Keyword arguments:
        tex -- the document text
        begincmd -- the command that begins this environment

        Specifically, begincmd has the form \begin{blah}, so we will be
        buiding a blah environment for some value of blah
    """
    name = begincmd.args[0]
    pos = begincmd.end
    optargs, args, t, pos0 = chomp_args(tex, pos)
    pos = pos0
    d = 1
    regex = r'\\(begin|end){{{}}}'.format(re.escape(name))
    rx = re.compile(regex)
    while d >= 0:
        m = rx.search(tex, pos)
        if not m:
            abort("Unmatched environment:". format(name))
        if m.group(1) == 'begin':
            d += 1
        else:
            d -= 1
    return environment(name, optargs, args,
                       tex[pos0:m.start()], begincmd.start, m.end())



def process_hash_env(b, env, mode):
    inner = r'\mathtt{{{}}}'.format(re.sub(r'(^|[^\\])&', r'\1\&', env.content))
    if mode & MATH:
        return [ inner ]
    else:
        return [ r'\(', inner, r'\)' ]

def process_env_passthru(b, env, mode):
    blocks = [r'\begin{{{}}}'.format(env.name)]
    blocks.extend(process_recursively(env.content, mode))
    blocks.append(r'\end{{{}}}'.format(env.name))
    return blocks

def process_displaymath_env(b, env, mode):
    return process_env_passthru(b, env, mode | MATH)

def process_inlinemath_env(b, env, mode):
    blocks = [r'\(']
    blocks.extend(process_recursively(env.content, mode | MATH))
    blocks.append(r'\)')
    return blocks

def process_list_env(b, env, mode):
    newblocks = list()
    mapper = dict([('itemize', 'ul'), ('enumerate', 'ol'), ('list', 'ul')])
    tag = mapper[env.name]
    newblocks.append('<{} class="{}">'.format(tag, env.name))
    newblocks.extend(process_recursively(process_list_items(env.content), mode))
    newblocks.append('</li></{}>'.format(tag))
    return newblocks

def process_list_items(b):
    b = re.sub(r'\\item\s+', '\1', b, 1)
    b = re.sub(r'\\item\s+', '\2\1', b)
    b = re.sub(r'\s*' + '\1' + r'\s*', '<li>', b, 0, re.M|re.S)
    b = re.sub(r'\s*' + '\2' + r'\s*', '</li>', b, 0, re.M|re.S)
    return b

def process_tabular_env(tex, env, mode):
    inner = "".join(process_recursively(env.content, mode))
    rows = re.split(r'\\\\', inner)
    rows = [re.split(r'\&', r) for r in rows]
    table = '<table align="center">'
    for r in rows:
        table += '<tr>'
        for c in r:
            table += '<td>' + c + '</td>'
        table += '</tr>'
    table += '</table>'
    return table

def process_theoremlike_env(tex, env, mode):
    newblocks = ['<div class="{}">'.format(env.name)]
    if env.optargs:
        title = env.optargs[0]
    elif env.name in named_entities:
        title = named_entities[env.name]
    else:
        title = ''
    newblocks.append('<span class="title">{}</span>'.format(title))

    newblocks.extend(process_recursively(env.content, mode))
    newblocks.append('</div><!-- {} -->'.format(env.name))
    return newblocks

def process_env_default(tex, env, mode):
    if not mode & MATH:
        unprocessed_environments.add(env.name)
    newblocks = ['<div class="{}">'.format(env.name)]
    newblocks.extend(process_recursively(env.content, mode))
    newblocks.append('</div><!-- {} -->'.format(env.name))
    return newblocks

#
# The main processing loop
#
def process_recursively(tex, mode):
    newblocks = list()
    lastidx = 0
    cmd = next_command(tex, lastidx)
    while cmd:
        newblocks.append(tex[lastidx:cmd.start])
        if cmd.name == 'begin':
            env = get_environment(tex, cmd)
            lastidx = env.end
            newblocks.extend(environment_handlers[env.name](tex, env, mode))
        else:
            lastidx = cmd.end
            newblocks.extend(command_handlers[cmd.name](tex, cmd, mode))
        cmd = next_command(tex, lastidx)
    newblocks.append(tex[lastidx:])
    return newblocks


def tex2htm(tex):
    # Some preprocessing
    tex = preprocess_hashes(tex)
    tex = strip_comments(tex)
    tex = re.sub(r'\\\[', r'\\begin{equation*}', tex)
    tex = re.sub(r'\\\]', r'\end{equation*}', tex)
    tex = re.sub(r'\$([^\$]*(\\\$)?)\$', r'\\begin{dollar}\1\\end{dollar}', tex,
                 0, re.M|re.S)
    tex = re.sub(r'\\myeqref', '\\eqref', tex)
    tex = re.sub(r'---', r'&mdash;', tex)
    tex = re.sub(r'--', r'&ndash;', tex)
    tex = re.sub('#([^#]*)#', r'\\begin{hash}\1\end{hash}', tex, 0, re.M|re.S)

    tex = process_labels(tex)
    for label in label_map:
        print("{}=>#{}".format(label, label_map[label]))

    blocks = process_recursively(tex, 0)

    return "".join(blocks)

if __name__ == "__main__":
    print(sys.argv[0])
    if len(sys.argv) != 2:
        sys.stderr.write("Usage: {} <texfile>\n".format(sys.argv[0]))
        sys.exit(-1)
    filename = sys.argv[1]
    base, ext = os.path.splitext(filename)
    outfile = base + ".html"
    print("Reading from {} and writing to {}".format(filename, outfile))

    # Setup a few things
    setup_environment_handlers()
    setup_command_handlers()

    # Read and translate the input
    tex = open(filename).read()
    htm = tex2htm(tex)
    # TODO: Extract title
    chapter = "None"

    # Print warnings
    if undefined_labels:
        labels = ", ".join(sorted(undefined_labels))
        warn("Undefined labels: {}".format(labels))
    if unprocessed_commands:
        commands = ", ".join(sorted(unprocessed_commands))
        warn("Unprocessed commands: {}".format(commands))
    if unprocessed_commands:
        environments = ", ".join(sorted(unprocessed_environments))
        warn("Defaulted environments: {}".format(environments))

    # Read the skeleton
    basedir = os.path.dirname(sys.argv[0])
    filename = basedir + os.path.sep + 'skeleton.htm'
    (head, tail) = re.split('CONTENT', open(filename).read())
    head = re.sub('TITLE', chapter, head)

    # Write everything
    of = open(outfile, 'w')
    of.write(head)
    of.write(htm)
    of.write(tail)
    of.close()
