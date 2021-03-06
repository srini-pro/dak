#!/usr/bin/python3
# (c) 2008 Thomas Viehmann
# Free software licensed under the GPL version 2 or later

import os
import re
import datetime
import sys
import tempfile

ITEMS_TO_KEEP = 20
CACHE_FILE = '/srv/ftp-master.debian.org/misc/dinstall_time_cache'
GRAPH_DIR = '/srv/ftp.debian.org/web/stat'

LINE = re.compile(r'(?:|.*/)dinstall_(\d{4})\.(\d{2})\.(\d{2})-(\d{2}):(\d{2}):(\d{2})\.log(?:\.bz2)?:'
                  r'Archive maintenance timestamp \(([^\)]*)\): (\d{2}):(\d{2}):(\d{2})$')
UNSAFE = re.compile(r'[^a-zA-Z/\._:0-9\- ]')

graphs = {"dinstall1": {"keystolist": ["pg_dump1", "i18n 1", "accepted", "dominate", "generate-filelist", "apt-ftparchive",
                                    "pdiff", "release files", "w-b", "i18n 2", "apt-ftparchive cleanup"],
                        "showothers": True},
          "dinstall2": {"keystolist": ['External Updates', 'p-u-new', 'o-p-u-new', 'cruft', 'import-keyring', 'overrides', 'cleanup', 'scripts', 'mirror hardlinks', 'stats', 'compress', "pkg-file-mapping"],
                        "showothers": False},
          "totals": {"keystolist": ["apt-ftparchive", "apt-ftparchive cleanup"], "showothers": True}}

wantkeys = set()
for tmp in graphs.values():
    wantkeys |= set(tmp["keystolist"])

d = {}
kl = []
ks = set()
if os.path.exists(CACHE_FILE):
    for l in open(CACHE_FILE):
        dt, l = l.split('\t', 1)
        l = map(lambda x: (lambda y: (y[0], float(y[1])))(x.split(':', 1)), l.split('\t'))
        newk = [x[0] for x in l if x[0] not in ks]
        kl += newk
        ks |= set(newk)
        d[dt] = dict(l)

olddt = None
args = sys.argv[1:]
m = UNSAFE.search(' '.join(args))
if m:
    raise Exception("I don't like command line arguments including char '%s'" % m.group(0))

if args:
    for l in os.popen('bzgrep -H "^Archive maintenance timestamp" "' + '" "'.join(args) + '"'):
        m = LINE.match(l)
        if not m:
            raise Exception("woops '%s'" % l)
        g = [int(x) if x.isdigit() else x for x in m.groups()]
        dt = datetime.datetime(*g[:6])
        if olddt != dt:
            oldsecs = 0
            olddt = dt
        dt2 = datetime.datetime(*(g[:3] + g[-3:]))
        secs = (dt2 - dt).seconds
        assert secs >= 0 # should add 24*60*60
        k = g[6]
        d.setdefault(str(dt), {})[k] = (secs - oldsecs) / 60.0
        oldsecs = secs
        if k not in ks:
            ks.add(k)
            kl.append(k)

if (wantkeys - ks):
    print("warning, requested keys not found in any log:", *(wantkeys - ks), file=sys.stderr)

datakeys = sorted(d.keys())

with open(CACHE_FILE + ".tmp", "w") as f:
    for dk in datakeys:
        print(dk, *("%s:%s" % (k, str(d[dk][k])) for k in kl if k in d[dk]), sep='\t', file=f)
os.rename(CACHE_FILE + ".tmp", CACHE_FILE)
datakeys = datakeys[-ITEMS_TO_KEEP:]


def dump_file(outfn, keystolist, showothers):
    showothers = (showothers and 1) or 0
    # careful, outfn is NOT ESCAPED
    f = tempfile.NamedTemporaryFile("w+t")
    otherkeys = ks - set(keystolist)
    print('\t'.join(keystolist + showothers * ['other']), file=f)
    for k in datakeys:
        v = d[k]
        others = sum(v.get(x, 0) for x in otherkeys)
        print(k + '\t' + '\t'.join([str(v.get(x, 0)) for x in keystolist] + showothers * [str(others)]), file=f)
    f.flush()

    p = os.popen("R --vanilla --slave > /dev/null", "w")
    p.write("""
  d = read.table("%(datafile)s",  sep = "\t")
  #d[["ts"]] <- as.POSIXct(d[["timestamp"]])
  k = setdiff(names(d),c("ts","timestamp"))
  #palette(rainbow(max(length(k),2)))
  palette(c("midnightblue", "gold", "turquoise", "plum4", "palegreen1", "OrangeRed", "green4", "blue",
        "magenta", "darkgoldenrod3", "tomato4", "violetred2","thistle4", "steelblue2", "springgreen4", "salmon","gray"))
  #plot(d[["runtime"]],d[["compress"]],type="l",col="blue")
  #lines(d[["runtime"]],d[["logremove"]],type="l",col="red")
  #legend(as.POSIXct("2008-12-05"),9500,"logremove",col="red",lty=1)
  bitmap(file = "%(outfile)s", type="png16m",width=16.9,height=11.8)
  #plot(d[["ts"]],d[["compress"]],type="l",col="blue")
  #lines(d[["ts"]],d[["logremove"]],type="l",col="red")
  barplot(t(d[,k]), col=palette(), xlab="date",ylab="time/minutes"
          )
  par(xpd = TRUE)
  legend(xinch(-1.2),par("usr")[4]+yinch(1),legend=k,
                  ncol=3,fill=1:15) #,xjust=1,yjust=1)
  text(xinch(10),par("usr")[4]+yinch(.5),"%(title)s", cex=2)

  dev.off()
  q()
  """ % {'datafile': f.name, 'outfile': outfn,
       'title': ((not showothers) * "partial ") + "dinstall times"})
    p.flush()
    assert not p.close()


for afn, params in graphs.items():
    dump_file(os.path.join(GRAPH_DIR, afn + '.png'), **params)
