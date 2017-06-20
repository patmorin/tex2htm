""" Open Data Structures specific extension for tex2htm """
import os
import re

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
    strip = ['javaonly', 'notpcode']
    for c in strip:
        command_handlers[c] = tex2htm.process_cmd_strip

def get_member(member, clz):
    basedir = '/home/morin/ods/java'
    filename = basedir+os.path.sep+clz+'.java' # FIXME: hard-coded

    for line in open(filename).read().splitlines()
        line = re.sub('public|static|void|protected', '', line)


def process_codeimport_cmd(tex, cmd, mode):
    blocks = catlist(['<div class="codeimport">'])
    blocks.extend(tex2htm.process_recursively(cmd.args[0], mode))
    blocks.append("</div><!-- codeimport -->")
    print(cmd)
    clz, members = cmd.args[0].split('.', 1)
    members = members.split('.')
    for member in members:
        get_member(member, clz)
    return blocks

def setup_environment_handlers(environment_handlers):
    environment_handlers['hash'] = process_hash_env

def process_hash_env(b, env, mode):
    inner = r'\mathtt{{{}}}'.format(re.sub(r'(^|[^\\])&', r'\1\&', env.content))
    if mode & tex2htm.MATH:
        return catlist([inner])
    else:
        return catlist([r'\(', inner, r'\)'])
