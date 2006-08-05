#!/usr/bin/python

import sys, os, re, popen2
from socket import *

serve_addr = ('localhost', 47701)

def popen(cmd):
  p = popen2.Popen4(cmd)
  p.tochild.close()
  val = p.fromchild.read()
  p.fromchild.close()
  return val.strip()

if __name__ == '__main__':
  IRC_BOLD = '\x02'
  IRC_ULINE = '\x1f'
  IRC_NORMAL = '\x0f'
  IRC_RED = '\x034'
  IRC_LIME = '\x039'
  IRC_BLUE = '\x0312'
  repos, rev = sys.argv[1:3]
  author = popen(('/usr/local/bin/svnlook', 'author', '-r', rev, repos))
  log = popen(('/usr/local/bin/svnlook', 'log', '-r', rev, repos))
  log = re.subn(r'\n *', ' ', log)[0]
  repos = os.path.basename(repos)
  data = (
      "%(IRC_LIME)s%(author)s "
      "%(IRC_RED)sr%(rev)s "
      "%(IRC_BLUE)s%(repos)s "
      "%(IRC_NORMAL)s%(log)s" % locals()
      )
  if len(data) > 400:
    data = data[:400] + "..."
  #for c in range(0, 20):
  #  data += " \x030,%s_%s_\x0f" % (c,c)
  sock = socket(AF_INET, SOCK_DGRAM)
  sock.sendto(data, serve_addr)
  sock.close()
