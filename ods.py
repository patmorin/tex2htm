""" Open Data Structures specific extension for tex2htm """
import os
import sys
import re

from pygments import highlight
from pygments.lexers import JavaLexer
from pygments.formatters import HtmlFormatter


from catlist import catlist
#catlist = list

import tex2htm


def preprocess_hashes(tex):
    """Prevents percents inside hashes from being treated as comments"""
    blocks = catlist()
    rx = re.compile('#([^#]*)#', re.M|re.S)
    lastidx = 0
    for m in rx.finditer(tex):
        blocks.append(tex[lastidx:m.start()])
        lastidx = m.end()
        blocks.append(re.sub(r'(^|[^\\])%', r'\1\%', m.group(0)))
    blocks.append(tex[lastidx:])
    return "".join(blocks)

def convert_hashes(tex):
    return re.sub('#([^#]*)#', r'\\begin{hash}\1\end{hash}', tex, 0, re.M|re.S)

def setup_command_handlers(command_handlers):
    command_handlers['codeimport'] =  process_codeimport_cmd
    command_handlers['javaimport'] =  process_codeimport_cmd
    command_handlers['etal'] = lambda text, cmd, mode: catlist(["<em>et al</em>"])
    command_handlers['lang'] = lambda text, cmd, mode: catlist(["Java"])
    worthless = ['cpponly']
    for c in worthless:
        command_handlers[c] = tex2htm.process_cmd_worthless
    strip = ['javaonly', 'notpcode']
    for c in strip:
        command_handlers[c] = tex2htm.process_cmd_strip

def get_member(member, clz):
    basedir = os.path.dirname(sys.argv[1]) + os.path.sep \
                + '..' + os.path.sep + 'java'
    filename = basedir+os.path.sep+clz+'.java' # FIXME: hard-coded
    code = catlist()
    d = 0
    writing = False
    found = False
    for line in open(filename).read().splitlines():
        line = re.sub('(static|public|protected|private|final)\s+', '', line)
        line = re.sub('\t', '    ', line)
        if d == 1:
            m = re.match('\s*(<[^>]*>)?\s*\w+\s*(\w+)\s*\((.*)\)\s*{\s*$', line)
            if m:
                # this line is a method definition
                found = True
                name = m.group(2)
                args = [x.strip() for x in m.group(3).split(',') if x]
                argnames = [x.split()[-1] for x in args]
                sig = '{}({})'.format(name, ",".join(argnames))
                if sig == member:
                    writing = True
            m = re.match('\s*(<[^>]*>)?\s*\w+\s*(\w+)\s*;\s*$', line)
            if m:
                # this is an instance variable
                name = m.group(2)
                if name == member:
                    code.append(line)

        d += line.count('{')
        d -= line.count('}')
        if writing:
            if not re.search('IndexOutOfBoundsException', line):
                code.append(line)
            if d <= 1:
                writing = False
    if not found:
        msg = 'ERROR: {}.{} not found'.format(clz, member)
        tex2htm.warn(msg)
        code.append('// {}'.format(msg))
    return code

def process_codeimport_cmd(tex, cmd, mode):
    blocks = catlist(['<div class="codeimport">'])
    # blocks.extend(tex2htm.process_recursively(cmd.args[0], mode))
    clz, members = cmd.args[0].split('.', 1)
    members = members.split('.')
    code = catlist()
    for member in members:
        code.extend(get_member(member, clz))
    blocks.append(highlight("\n".join(code), JavaLexer(), HtmlFormatter()))
    blocks.append("</div><!-- codeimport -->")
    return blocks

def setup_environment_handlers(environment_handlers):
    environment_handlers['hash'] = process_hash_env

def process_hash_env(b, env, mode):
    inner = r'\mathtt{{{}}}'.format(re.sub(r'(^|[^\\])&', r'\1\&', env.content))
    if mode & tex2htm.MATH:
        return catlist([inner])
    else:
        return catlist([r'\(', inner, r'\)'])
