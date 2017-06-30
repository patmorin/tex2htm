#!/usr/bin/python3
# -*- coding: utf-8 -*-
""" A LaTeX to HTML conversion utility
"""
import os
import sys
import re
import subprocess
from collections import defaultdict

from catlist import catlist


# TODO: Support for importing subclasses
# TODO: More parsing cleanup
# TODO: pageref
# TODO: Handle brace blocks that are misidentified as arguments
# TODO: Plot in Figure 1.5
# TODO: Nicer skeleton

import ods

class context(object):
    def __init__(self):
        self.environment_handlers = defaultdict(lambda: process_env_default)
        self.command_handlers = defaultdict(lambda: process_cmd_default)

        # Environments that are theorem-like or that have captions should be here
        self.named_entities = {'chap': 'Chapter',
                          'sec': 'Section',
                          'thm': 'Theorem',
                          'prp': 'Property',
                          'cor': 'Corollary',
                          'lem': 'Lemma',
                          'fig': 'Figure',
                          'figure': 'Figure',
                          'eq': 'Equation',
                          'exc': 'Exercise',
                          'proof': 'Proof'}

        self.theoremlike_environments = {'thm', 'lem', 'cor', 'exc', 'prp', 'proof'}

        # Map LaTeX labels on to HTML id's
        self.label_map = dict()

        # Collections of things to warn about after processing is done
        self.undefined_labels = set()
        self.unprocessed_commands = set()
        self.unprocessed_environments = set()

        # Graphics files to generate after processing is done
        self.graphics_files = set()

        # Used for processing footnotes
        self.footnote_counter = 0
        self.footnotes = list()

        # Document title
        self.title = 'Untitled'

        # Table of contents
        self.global_toc = catlist()
        self.toc = catlist()

# Math mode
MATH = 1


# We make internal labels that look like this
crossref_format = 'CROSSREF〈{}|{}|{}〉'
crossref_rx = re.compile(r'CROSSREF〈((\w|:|-)+)\|(\w+)\|([^〉]*)〉')

#
# Utilities
#
def abort(msg, status=-1):
    sys.stderr.write(msg + '\n')
    sys.exit(status)

def warn(msg, level=0):
    sys.stderr.write("Warning: {}\n".format(msg))

def skip_space(tex, i):
    while i < len(tex) and tex[i].isspace():
        i += 1
    return i

def match_parens(tex, i, open, close):
    # TODO: Handle escape sequences
    di = defaultdict(int, {open: 1, close: -1})
    j0 = skip_space(tex, i)
    if j0 == len(tex): return i,i+1
    j = j0
    try:
        d = di[tex[j]]
        if d == 0: return i,i+1
        j = j+d
        while d > 0:
            d += di[tex[j]]
            j+=1
        return j0,j
    except IndexError:
        abort("Couldn't match parenthesis:\n... "
              + tex[max(0,i):min(len(tex),i+25)])

id_counter = 0
def gen_unique_id(prefix=''):
    global id_counter
    id_counter += 1
    if not prefix:
        prefix = 'tex2htm'
    return '{}-{}'.format(prefix, id_counter)


#
# Preprocessing functions
#
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

def split_paragraphs(tex):
    # TODO: Do this better
    lines = [line.strip() for line in tex.splitlines()]
    out=''
    for i in range(len(lines)-1):
        if lines[i] == '' and lines[i+1] != '':
            lines[i] += '<p>'
    return "\n".join(lines)

def add_toc_entry(ctx, text, label, name):
    ctx.toc.append('<li>')
    ctx.toc.append(crossref_format.format(label, name, text))
    ctx.toc.append('</li>')

#
# Label and Reference Handling
# TODO: The insertion of numbers into theorem-like, sectioning commands,
#       and captions is super hacky. Consider using JavaScript to do this,
#       like here: https://github.com/rauschma/html_demos
#
def process_labels(ctx, tex, chapter):
    """ Process all the labels that occur in tex

        This works by scanning for commands and environments that alter
        numbering as well as any LaTeX labelling commands.
    """
    headings = ['chapter'] + ['sub'*i + 'section' for i in range(4)]
    reh = r'(' + '|'.join(headings) + r'){(.+?)}'
    environments = ['thm', 'lem', 'exc', 'figure', 'equation']
    ree = r'begin{(' + '|'.join(environments) + r')}'
    rel = r'(\w+)label{(.+?)}'
    rel2 = r'label{(.+?)}'
    bigone = r'\\({})|\\({})|\\({})|\\(caption)|\\({})'.format(reh, ree, rel, rel2)
    rx = re.compile(bigone)

    sec_ctr = [chapter] + [0]*(len(headings))
    env_ctr = [0]*len(environments)
    blocks = catlist()
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
            lastenv = name # save this for a caption command coming later...
            i = environments.index(name)
            env_ctr[i] += 1
            number = "{}.{}".format(sec_ctr[0], env_ctr[i])
            idd = "{}:{}".format(name, number)
            lastlabel = idd
            blocks.append("<a id='{}'></a>".format(idd))

            if name in ctx.theoremlike_environments:
                nicename = ctx.named_entities[name]
                title = '{}&nbsp;{}'.format(nicename, number)
                blocks.append(r'\begin{{{}}}[{}]'.format(name, title))

        elif m.group(6):
            # This is a labelling command (\thmlabel, \seclabel,...)
            label = "{}:{}".format(m.group(7), m.group(8))
            ctx.label_map[label] = (ctx.outputfile, lastlabel)

        elif m.group(9):
            # This is a caption command
            name = lastenv
            i = environments.index(name)
            number = "{}.{}".format(sec_ctr[0], env_ctr[i])
            idd = "{}:{}".format(name, number)
            lastlabel = idd
            nicename = ctx.named_entities[name]
            title = '<span class="title">{}&nbsp;{}</span>'.format(nicename, number)
            text = '{}&emsp;{}'.format(title, cmd.args[0])
            blocks.append(r'\caption{{{}}}'.format(text))

        elif m.group(10):
            # This is a \label command, probably the target of a pageref
            idd = gen_unique_id()
            blocks.append("<a id={}></a>".format(idd))
            ctx.label_map[m.group(11)] = (ctx.outputfile, idd)

        m = rx.search(tex, lastidx)
    blocks.append(tex[lastidx:])
    return "".join(blocks)




#
# LaTeX commands
#
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
    try:
        j,k = match_parens(tex, j, '[', ']')
    except:
        return([], [], pos, j)
    while k > j+1:
        optargs.append(tex[j+1:k-1])
        j = k
        j,k = match_parens(tex, j, '[', ']')
    args = []
    j,k = match_parens(tex, j, '{', '}')
    while k > j+1:
        args.append(tex[j+1:k-1])
        j = k
        j,k = match_parens(tex, j, '{', '}')
    return (optargs, args, pos, j)


def next_command(tex, pos):
    """Get the next command in tex that occurs at or after pos"""
    rx = re.compile(r'\\([a-zA-Z0-9]+\*?)')
    m = rx.search(tex, pos)
    if m:
        optargs, args, t, j = chomp_args(tex, m.end())
        cmd = command(m.group(1), optargs, args, m.start(), j)
        return cmd
    return None


def setup_command_handlers(ctx):
    ctx.command_handlers['chapter'] =  process_chapter_cmd
    ctx.command_handlers['section'] =  process_section_cmd
    ctx.command_handlers['subsection'] =  process_subsection_cmd
    ctx.command_handlers['subsubsection'] =  process_subsubsection_cmd
    ctx.command_handlers['paragraph'] =  process_paragraph_cmd
    ctx.command_handlers['emph'] =  process_emph_cmd
    ctx.command_handlers['textbf'] =  process_textbf_cmd
    ctx.command_handlers['texttt'] =  process_texttt_cmd
    ctx.command_handlers['caption'] =  process_caption_cmd
    ctx.command_handlers['includegraphics'] =  process_graphics_cmd
    ctx.command_handlers['cite'] =  process_cite_cmd
    ctx.command_handlers['ldots'] =  process_dots_cmd
    ctx.command_handlers['footnote'] = process_footnote_cmd
    ctx.command_handlers['centering'] = process_centering_cmd
    ctx.command_handlers['href'] = process_href_cmd
    ctx.command_handlers['url'] = process_url_cmd
    ctx.command_handlers['path'] = process_path_cmd

    ctx.command_handlers['newblock'] = process_cmd_strip
    ctx.command_handlers['pageref'] = process_pageref_cmd

    worthless = ['newlength', 'setlength', 'addtolength', 'vspace', 'index',
                 'cpponly', 'cppimport', 'pcodeonly', 'pcodeimport', 'qedhere',
                 'end', 'hline', 'noindent', 'pagenumbering', 'linewidth',
                 'newcommand', 'resizebox', 'setcounter', 'multicolumn']
    for c in worthless:
        ctx.command_handlers[c] = process_cmd_worthless

    labeltypes = ['', 'fig', 'Fig', 'eq', 'thm', 'lem', 'exc', 'chap', 'sec',
                  'thm']
    for t in labeltypes:
        ctx.command_handlers[t + 'label'] = process_cmd_worthless
        ctx.command_handlers[t + 'ref'] = process_ref_cmd

    # TODO: Find an exhaustive list of these
    mathbreakers = ['mbox', 'text']
    for c in mathbreakers:
        ctx.command_handlers[c] = process_mathbreaker_cmd

def process_cmd_default(ctx, tex, cmd, mode):
    """ By default, we just pass commands through untouched """
    if not (mode & MATH):
        ctx.unprocessed_commands.add(cmd.name)
    return process_cmd_passthru(ctx, tex, cmd, mode)

def process_cmd_passthru(ctx, tex, cmd, mode):
    blocks = catlist([r'\{}'.format(cmd.name)])
    for a in cmd.optargs:
        blocks.append('[')
        blocks.extend(process_recursively(ctx, a, mode))
        blocks.append(']')
    for a in cmd.args:
        blocks.append('{')
        blocks.extend(process_recursively(ctx, a, mode))
        blocks.append('}')
    return blocks

def process_cmd_worthless(ctx, tex, cmd, mode):
    """ Worthless commands and arguments are completely removed """
    return catlist()

def process_cmd_strip(ctx, text, cmd, mode):
    """ These commands have their arguments processed """
    blocks = catlist()
    for a in cmd.args:
        blocks.extend(process_recursively(ctx, a, mode))
    return blocks

def process_mathbreaker_cmd(ctx, text, cmd, mode):
    """ These command break out of math mode """
    if mode & MATH:
        return process_cmd_passthru(ctx, text, cmd, mode & ~MATH)
    return process_cmd_strip(ctx, text, cmd, mode)

def process_path_cmd(ctx, tex, cmd, mode):
    return catlist(['<span class="path">{}</span>'.format(cmd.args[0])])

def process_dots_cmd(ctx, tex, cmd, mode):
    """ Various kinds of ellipses """
    if mode & MATH:
        return process_cmd_default(ctx, tex, cmd, mode)
    else:
        mapper = { 'ldots': '&hellip;',
                'vdots': '&#x22ee;' }
        if cmd.name in mapper:
            return catlist([mapper[cmd.name]])
    warn("Unrecognized non-math dots: {}".format(cmd.name))
    return catlist([ '?' ])

def process_chapter_cmd(ctx, text, cmd, mode):
    global title
    title = cmd.args[0]
    blocks = catlist()
    ident = gen_unique_id()
    blocks.append('<div id="{}" class="chapter">'.format(ident))
    htmlblocks = process_recursively(ctx, cmd.args[0], mode)
    add_toc_entry(ctx, ''.join(htmlblocks), ident, 'chap')
    ctx.label_map[ident] = ctx.outputfile, ''.join(htmlblocks)
    blocks.extend(htmlblocks)
    blocks.append('</div><!-- chapter -->')
    return blocks

def process_section_cmd(ctx, text, cmd, mode):
    ident = gen_unique_id()
    blocks = catlist(['<h1 id="{}">'.format(ident)])
    htmlblocks = process_recursively(ctx, cmd.args[0], mode)
    add_toc_entry(ctx, ''.join(htmlblocks), ident, 'sec')
    ctx.label_map[ident] = ctx.outputfile, ''.join(htmlblocks)
    blocks.extend(htmlblocks)
    blocks.append("</h1>")
    return blocks

def process_subsection_cmd(ctx, text, cmd, mode):
    blocks = catlist(["<h2>"])
    blocks.extend(process_recursively(ctx, cmd.args[0], mode))
    blocks.append("</h2>")
    return blocks

def process_subsubsection_cmd(ctx, text, cmd, mode):
    blocks = catlist(["<h2>"])
    blocks.extend(process_recursively(ctx, cmd.args[0], mode))
    blocks.append("</h2>")
    return blocks

def process_paragraph_cmd(ctx, text, cmd, mode):
    blocks = catlist(['<div class="paragraph_title">'])
    blocks.extend(process_recursively(ctx, cmd.args[0], mode))
    blocks.append("</div><!-- paragraph_title -->")
    return blocks

def process_emph_cmd(ctx, text, cmd, mode):
    blocks = catlist(["<em>"])
    blocks.extend(process_recursively(ctx, cmd.args[0], mode))
    blocks.append("</em>")
    return blocks

def process_textbf_cmd(ctx, text, cmd, mode):
    blocks = catlist(["<span class='bf'>"])
    blocks.extend(process_recursively(ctx, cmd.args[0], mode))
    blocks.append("</span>")
    return blocks

def process_texttt_cmd(ctx, text, cmd, mode):
    blocks = catlist(["<span class='tt'>"])
    blocks.extend(process_recursively(ctx, cmd.args[0], mode))
    blocks.append("</span>")
    return blocks

def process_caption_cmd(ctx, text, cmd, mode):
    blocks = catlist(['<div class="caption">'])
    blocks.extend(process_recursively(ctx, cmd.args[0], mode))
    blocks.append("</div><!-- caption -->")
    return blocks

def process_graphics_cmd(ctx, text, cmd, mode):
    filename = "{}.svg".format(cmd.args[0])
    ctx.graphics_files.add(filename)
    return catlist(['<span class="imgwrap"><img class="includegraphics" src="{}"/></span>'.format(filename)])

def process_centering_cmd(ctx, text, cmd, mode):
    blocks = catlist(['<div class="centering">'])
    blocks.extend(process_recursively(ctx, cmd.args[0], mode))
    blocks.append("</div><!-- caption -->")
    return blocks

def process_footnote_cmd(ctx, tex, cmd, mode):
    blocks = catlist()
    ctx.footnote_counter += 1
    blocks.append('<a class="ptr">({})</a>'.format(ctx.footnote_counter))
    fntext = ''.join(process_recursively(ctx, cmd.args[0], mode))
    ctx.footnotes.append('<li>{}</li>'.format(fntext))
    return blocks

def process_url_cmd(ctx, tex, cmd, mode):
    return catlist(["<a href='{url}'>{url}</a>".format(url=cmd.args[0])])

def process_href_cmd(ctx, tex, cmd, mode):
    blocks = catlist(["<a href='{}'>".format(cmd.args[0])])
    blocks.extend(process_recursively(ctx, cmd.args[1], mode))
    blocks.append("</a>")
    return blocks

def crossref_text(ctx, name, texlabel, default=''):
    if texlabel not in ctx.label_map:
        return default
    f, htmllabel = ctx.label_map[texlabel]
    num = htmllabel[htmllabel.find(':')+1:]
    if name == 'cite':
        return num
    if name == 'page':
        return 'X'
    if name in ctx.named_entities:
        return "{}&nbsp;{}".format(ctx.named_entities[name], num)
    warn("Using unnamed reference type: {}".format(name))
    return "{}&nbsp;{}".format(name, num)


def process_ref_cmd(ctx, tex, cmd, mode):
    name = re.sub(r'^(.*)ref', r'\1', cmd.name).lower()
    texlabel = "{}:{}".format(name, cmd.args[0])
    text = crossref_text(ctx, name, texlabel)
    html = crossref_format.format(texlabel, name, text)
    return catlist([html])

def process_pageref_cmd(ctx, tex, cmd, mode):
    name = re.sub(r'^(.*)ref', r'\1', cmd.name).lower()
    texlabel = cmd.args[0]
    text = crossref_text(ctx, name, texlabel)
    html = crossref_format.format(texlabel, name, text)
    return catlist([html])

def process_cite_cmd(ctx, tex, cmd, mode):
    blocks = catlist(['['])
    args = [s.strip() for s in cmd.args[0].split(',')]
    htmls = [crossref_format.format("cite:{}".format(a), 'cite', '') \
                for a in args]
    blocks.append(",".join(htmls))
    blocks.append(']')
    return blocks

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

def setup_environment_handlers(ctx):
    ctx.environment_handlers['dollar'] = process_inlinemath_env
    ctx.environment_handlers['tabular'] = process_tabular_env
    displaymaths = ['equation', 'equation*', 'align', 'align*', 'eqnarray*']
    for name in displaymaths:
        ctx.environment_handlers[name] = process_displaymath_env
    passthroughs = ['array', 'cases']
    for name in passthroughs:
        ctx.environment_handlers[name] = process_env_passthru
    lists = ['itemize', 'enumerate', 'list', 'description']
    for name in lists:
        ctx.environment_handlers[name] = process_list_env
    for name in ctx.theoremlike_environments:
        ctx.environment_handlers[name] = process_theoremlike_env
    ctx.environment_handlers['center'] = process_center_env
    ctx.environment_handlers['thebibliography'] = process_thebibliography_env

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
    while d > 0:
        m = rx.search(tex, pos)
        if not m:
            abort("Unmatched environment:". format(name))
        if m.group(1) == 'begin':
            d += 1
        else:
            d -= 1
        pos = m.end()
    return environment(name, optargs, args,
                       tex[pos0:m.start()], begincmd.start, m.end())

def process_env_passthru(ctx, b, env, mode):
    blocks = catlist([r'\begin{{{}}}'.format(env.name)])
    blocks.extend(process_recursively(ctx, env.content, mode))
    blocks.append(r'\end{{{}}}'.format(env.name))
    return blocks

def process_displaymath_env(ctx, b, env, mode):
    return process_env_passthru(ctx, b, env, mode | MATH)

def process_inlinemath_env(ctx, b, env, mode):
    blocks = catlist([r'\('])
    blocks.extend(process_recursively(ctx, env.content, mode | MATH))
    blocks.append(r'\)')
    return blocks

def process_thebibliography_env(ctx, b, env, mode):
    env.content = re.sub('{thebibliography}', '{enumerate}', env.content)
    blocks = catlist()
    ref = 1
    i = 0
    rx = re.compile(r'\\bibitem\s*{(\w+)}')
    for m in rx.finditer(env.content):
        blocks.append(env.content[i:m.start()])
        i = m.end()
        texlabel = "cite:{}".format(m.group(1))
        htmllabel = 'cite:{}'.format(ref)
        ref += 1
        ctx.label_map[texlabel] = (ctx.outputfile, htmllabel)
        blocks.append(r'<a id="{}"</a>'.format(htmllabel))
        blocks.append(r'\item')
    blocks.append(env.content[i:])
    env.content = "".join(blocks)
    # env.content = re.sub(r'\\bibitem\s*{(\w+)}', r'\item', env.content)
    blocks = process_list_env(ctx, b, env, mode)
    txt = "".join([b for b in blocks])
    # bibtex-generated bibliographies are full of superfluous braces
    txt = re.sub(r'{([^}]*)}', r'\1', txt)
    return catlist([txt])

def process_list_env(ctx, b, env, mode):
    newblocks = catlist()
    mapper = dict([('itemize', 'ul'), ('enumerate', 'ol'), ('list', 'ul'),
                   ('thebibliography', 'ol'), ('description', 'ul')])
    tag = mapper[env.name]
    newblocks.append('<{} class="{}">'.format(tag, env.name))
    newblocks.extend(process_recursively(ctx, process_list_items(env.content), mode))
    newblocks.append('</li></{}>'.format(tag))
    return newblocks

def process_list_items(b):
    b = re.sub(r'\\item\s+', '\1', b, 1)
    b = re.sub(r'\\item\s+', '\2\1', b)
    b = re.sub(r'\s*' + '\1' + r'\s*', '<li>', b, 0, re.M|re.S)
    b = re.sub(r'\s*' + '\2' + r'\s*', '</li>', b, 0, re.M|re.S)
    return b

def process_tabular_env(ctx, tex, env, mode):
    # TODO: use a catlist of strings instead
    inner = "".join(process_recursively(ctx, env.content, mode))
    rows = re.split(r'\\\\', inner)
    rows = [re.split(r'\&', r) for r in rows]
    table = '<table align="center">'
    for r in rows:
        table += '<tr>'
        for c in r:
            table += '<td>' + c + '</td>'
        table += '</tr>'
    table += '</table>'
    return catlist([table])

def process_theoremlike_env(ctx, tex, env, mode):
    newblocks = catlist(['<div class="{}">'.format(env.name)])
    if env.optargs:
        title = env.optargs[0]
    elif env.name in ctx.named_entities:
        title = ctx.named_entities[env.name]
    else:
        title = ''
    newblocks.append('<span class="title">{}</span>'.format(title))

    newblocks.extend(process_recursively(ctx, env.content, mode))
    newblocks.append('</div><!-- {} -->'.format(env.name))
    return newblocks

def process_center_env(ctx, tex, env, mode):
    newblocks = catlist(['<div class="{}">'.format(env.name)])
    newblocks.extend(process_recursively(ctx, env.content, mode))
    newblocks.append('</div><!-- {} -->'.format(env.name))
    return newblocks

def process_env_default(ctx, tex, env, mode):
    if not mode & MATH:
        ctx.unprocessed_environments.add(env.name)
    newblocks = catlist(['<div class="{}">'.format(env.name)])
    newblocks.extend(process_recursively(ctx, env.content, mode))
    newblocks.append('</div><!-- {} -->'.format(env.name))
    return newblocks

#
# The main processing loop
#
def process_recursively(ctx, tex, mode):
    newblocks = catlist()
    lastidx = 0
    cmd = next_command(tex, lastidx)
    while cmd:
        newblocks.append(tex[lastidx:cmd.start])
        if cmd.name == 'begin':
            env = get_environment(tex, cmd)
            lastidx = env.end
            newblocks.extend(ctx.environment_handlers[env.name](ctx, tex, env, mode))
        else:
            lastidx = cmd.end
            newblocks.extend(ctx.command_handlers[cmd.name](ctx, tex, cmd, mode))
        cmd = next_command(tex, lastidx)
    newblocks.append(tex[lastidx:])
    return newblocks

def cleanup_oldschool(tex):
    # Cleanup some old school tex font control
    tex = re.sub(r'{\s*\\em', r'\\emph{', tex)
    tex = re.sub(r'{\s*\\bf', r'\\textbf{', tex)
    tex = re.sub(r"``", '“', tex)
    tex = re.sub(r"''", '”', tex)
    # TODO: Do something about single-quotes
    return tex

def cleanup_accented_chars(tex):
    mapper = [("'",'e','é'),
              ("'",'o','ó'),
              ("'",'c','ć'),
              ("'",r'\\i','í'),
              ('"',r'\\i','ï'),
              ('u','a','ă'),
              ('v','a','ă'),   # FIXME: Not quite
              ('c','s','ş')
             ]
    for m in mapper:
        pattern = r'\\{cmd}(\s*{arg}|\{{{arg}\}})'.format(cmd=m[0], arg=m[1])
        tex = re.sub(pattern, m[2], tex)
    for x in ['`', "'", '"']:
        pattern = r'\\{}'.format(x)
        m = re.search(pattern, tex)
        if m:
            warn("Unhandled accent: {}".format(tex[m.start():min(len(tex),
                                                                 m.start()+8)]))
    return tex

def tex2htm(ctx, tex, chapter):
    # Some preprocessing
    tex = ods.preprocess_hashes(tex) # TODO: ods specific
    tex = strip_comments(tex)
    tex = cleanup_oldschool(tex)
    tex = cleanup_accented_chars(tex)
    tex = split_paragraphs(tex)
    tex = re.sub(r'([^\\])\\\[', r'\1\\begin{equation*}', tex)
    tex = re.sub(r'([^\\])\\\]', r'\1\end{equation*}', tex)
    tex = re.sub(r'\$([^\$]*(\\\$)?)\$', r'\\begin{dollar}\1\\end{dollar}', tex,
                 0, re.M|re.S)
    tex = re.sub(r'([^\\])\~', r'\1&nbsp;', tex)
    tex = re.sub(r'\\myeqref', '\\eqref', tex)
    tex = re.sub(r'---', r'&mdash;', tex)
    tex = re.sub(r'--', r'&ndash;', tex)
    tex = ods.convert_hashes(tex) # TODO: ods specific

    tex = process_labels(ctx, tex, chapter)

    blocks = process_recursively(ctx, tex, 0)

    return "".join(blocks)

def generate_graphics_files(filenames, basedir):
    filenames = [basedir+os.path.sep+f for f in filenames]
    filenames = [f for f in filenames if not os.path.isfile(f)]
    fp = open('/dev/null', 'w')
    for f in filenames:
        f, ext = os.path.splitext(f)
        if ext != '.svg':
            warn("Unknown graphics type: {} for {}".format(ext, f+ext))
            continue
        m = re.search(r'(.*)-(\d+)$', f)
        cmd = ['iperender', '-svg']
        if m:
            ipefile = m.group(1) + ".ipe"
            view = m.group(2)
            cmd.extend(['-view', view])
        else:
            ipefile = f + ".ipe"
        svgfile = f + ext
        cmd.extend([ipefile, svgfile])
        status = subprocess.call(cmd, stdin=fp, stdout=fp, stderr=fp)
        if status:
            msg = "{} gave non-zero exit status for {}".format(cmd[0], ipefile)
            warn(msg)
    fp.close()

def finish_crossrefs(filename, label_map, html):
    blocks = catlist()
    i = 0
    for m in crossref_rx.finditer(html):
        blocks.append(html[i:m.start()])
        i = m.end()
        texlabel = m.group(1)
        name = m.group(3)
        text = m.group(4)
        if texlabel not in label_map:
            ctx.undefined_labels.add(texlabel)
            blocks.append('<span class="error">REFERR:{}</span>'.format(texlabel))
        else:
            f, ell = label_map[texlabel]
            if filename == f:
                htmllabel = "#{}".format(ell)
            else:
                htmllabel = "{}#{}".format(relative_path(filename, f), ell)
            if not text:
                text = crossref_text(ctx, name, texlabel)
            blocks.append('<a href="{}">{}</a>'.format(htmllabel, text))
    blocks.append(html[i:])
    return "".join(blocks)

def process_file(ctx, tex, dirname, chapter):
    # Read and translate the input
    htm = tex2htm(ctx, tex, chapter)

    # Generate any necessary graphics files
    generate_graphics_files(ctx.graphics_files, dirname)
    ctx.graphics_files.clear()
    return htm

def relative_path(fn1, fn2):
    dir1 = os.path.dirname(fn1)
    dir2 = os.path.dirname(fn2)

    i = 0
    while i < min(len(dir1), len(dir2)) and dir1[i] == dir2[i]: i+=1
    dir1 = dir1[i:]
    dir2 = dir2[i:]

    if not dir1 and not dir2:
        return os.path.basename(fn2)
    if not dir1:
        return dir2 + os.path.sep + os.path.basename(fn2)
    return ('../'+os.path.sep)*(dir1.count(os.path.sep)+1) \
              + os.path.basename(dir2)

if __name__ == "__main__":
    # Setup a few things
    ctx = context()
    setup_environment_handlers(ctx)
    setup_command_handlers(ctx)
    ods.setup_environment_handlers(ctx) # TODO: ods specific
    ods.setup_command_handlers(ctx) # TODO: ods specific

    # TODO: Use a better default, or specify on command line
    outputdir = os.path.dirname(sys.argv[1])

    # Read common skeleton
    basedir = os.path.dirname(sys.argv[0])
    filename = basedir + os.path.sep + 'skeleton.htm'
    (head, tail) = re.split('CONTENT', open(filename).read())

    ctx.outputfiles = dict()

    # Process all the input files
    chapter = 0
    for filename in sys.argv[1:]:
        texfilename = filename
        dirname = os.path.dirname(texfilename)
        base, ext = os.path.splitext(texfilename)
        htmlfilename = base + '.html'
        ctx.outputfile = htmlfilename
        print("Reading from {}".format(texfilename))
        tex = open(texfilename, "r").read()
        content = process_file(ctx, tex, dirname, chapter)

        headx = re.sub('TITLE', ctx.title, head)
        headx = re.sub('TOC', ''.join(ctx.toc), headx)
        ctx.global_toc.extend(ctx.toc)
        ctx.toc.__init__()

        tailx = tail.replace('FOOTNOTES', ''.join(ctx.footnotes))
        ctx.footnotes.clear()

        ctx.outputfiles[htmlfilename] = "".join([headx, content, tailx])

        chapter += 1

    for htmlfilename in ctx.outputfiles:
        ctx.outputfiles[htmlfilename] = finish_crossrefs(htmlfilename,
                                                     ctx.label_map,
                                                     ctx.outputfiles[htmlfilename])
        print("Writing to {}".format(htmlfilename))
        of = open(htmlfilename, 'w')
        of.write(ctx.outputfiles[htmlfilename])
        of.close()

    # Create global table of contents
    title = 'Open Data Structures'
    headx = re.sub('TITLE', title, head)
    tocfile = outputdir + os.path.sep + 'toc.html'
    tochtml = finish_crossrefs(tocfile, ctx.label_map, "".join(ctx.global_toc))
    headx = re.sub('TOC', tochtml, headx)
    tailx = tail.replace('FOOTNOTES', '')
    fp = open(tocfile, 'w')
    fp.write(headx)
    fp.write(tailx)
    fp.close()

    # Print warnings
    if ctx.undefined_labels:
        labels = ", ".join(sorted(ctx.undefined_labels))
        warn("Undefined labels: {}".format(labels))
    if ctx.unprocessed_commands:
        commands = ", ".join(sorted(ctx.unprocessed_commands))
        warn("Unprocessed commands: {}".format(commands))
    if ctx.unprocessed_environments:
        environments = ", ".join(sorted(ctx.unprocessed_environments))
        warn("Defaulted environments: {}".format(environments))
