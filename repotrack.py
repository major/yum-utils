#!/usr/bin/python -tt
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
# (c) 2005 seth vidal skvidal at phy.duke.edu


# specify list of repos or default in yum.conf
# specify list of pkgs - default to *
# download latest set + any deps to a specified dir
# alternatively:
# repomanage repo
# createrepo repo
# repoview repo
# email some address the list of new/updated packages.

# need to keep state of current repo to know what's 'new' and when to download things
# arch should be specified or default to system arch.

import os
import sys
from optparse import OptionParser
from urlparse import urljoin


import yum
import yum.Errors
from yum.misc import getCacheDir
from yum.constants import *
from yum.packages import parsePackages
from repomd.packageSack import ListPackageSack

class RepoTrack(yum.YumBase):
    def __init__(self, opts):
        yum.YumBase.__init__(self)
        self.opts = opts
        
    def log(self, num, msg):
        if num < 3 and not self.opts.quiet:
            print msg
    
    def findDeps(self, po):
        """Return the dependencies for a given package, as well
           possible solutions for those dependencies.
           
           Returns the deps as a dict  of:
            dict[reqs] = [list of satisfying pkgs]"""
        
   
        reqs = po.returnPrco('requires');
        reqs.sort()
        pkgresults = {}
        
        for req in reqs:
            (r,f,v) = req
            if r.startswith('rpmlib('):
                continue
            
            satisfiers = []

            for po in self.whatProvides(r, f, v):
                satisfiers.append(po)

            pkgresults[req] = satisfiers
        
        return pkgresults
    

def more_to_check(unprocessed_pkgs):
    for pkg in unprocessed_pkgs.keys():
        if unprocessed_pkgs[pkg] is not None:
            return True
    
    return False

def parseArgs():
    usage = "usage: %s [-c <config file>] [-a <arch>] [-r <repoid>] [-r <repoid2>]" % sys.argv[0]
    parser = OptionParser(usage=usage)
    parser.add_option("-c", "--config", default='/etc/yum.conf',
        help='config file to use (defaults to /etc/yum.conf)')
    parser.add_option("-a", "--arch", default=None,
        help='check as if running the specified arch (default: current arch)')
    parser.add_option("-r", "--repoid", default=[], action='append',
        help="specify repo ids to query, can be specified multiple times (default is all enabled)")
    parser.add_option("-t", "--tempcache", default=False, action="store_true", 
        help="Use a temp dir for storing/accessing yum-cache")
    parser.add_option("-p", "--download_path", dest='destdir', 
        default=os.getcwd(), help="Path to download packages to")
    parser.add_option("-u", "--urls", default=False, action="store_true", 
        help="Just list urls of what would be downloaded, don't download")
    parser.add_option("-n", "--newest", default=False, action="store_true", 
        help="Only download/list newest packages")
    parser.add_option("-q", "--quiet", default=False, action="store_true", 
        help="Output as little as possible")
        
    (opts, args) = parser.parse_args()
    return (opts, args)


def main():
# TODO/FIXME
# gpg/sha checksum them

    (opts, user_pkg_list) = parseArgs()
    
    my = RepoTrack(opts=opts)
    my.doConfigSetup(fn=opts.config)
    
    # do the happy tmpdir thing if we're not root
    if os.geteuid() != 0 or opts.tempcache:
        cachedir = getCacheDir()
        if cachedir is None:
            print "Error: Could not make cachedir, exiting"
            sys.exit(50)
            
        my.repos.setCacheDir(cachedir)

    for repo in my.repos.repos.values():
        if repo.id not in opts.repoid:
            repo.disable()
        else:
            repo.enable()
    
    my.doRepoSetup()    
    my.doSackSetup()
    
    unprocessed_pkgs = {}
    final_pkgs = {}
    user_po_list = []
    pkg_list = []
    
    avail = my.pkgSack.returnPackages()
    for item in user_pkg_list:
        exactmatch, matched, unmatched = parsePackages(avail, [item])
        pkg_list.extend(exactmatch)
        pkg_list.extend(matched)
        this_sack = ListPackageSack()
        this_sack.addList(pkg_list)
        pkg_list = this_sack.returnNewestByNameArch()
        del this_sack
        
    for po in pkg_list:
        unprocessed_pkgs[po.pkgtup] = po
    

    while more_to_check(unprocessed_pkgs):
    
        for pkgtup in unprocessed_pkgs.keys():
            if unprocessed_pkgs[pkgtup] is None:
                continue

            po = unprocessed_pkgs[pkgtup]
            final_pkgs[po.pkgtup] = po
            
            deps_dict = my.findDeps(po)
            unprocessed_pkgs[po.pkgtup] = None
            for req in deps_dict.keys():
                this_sack = ListPackageSack()
                this_sack.addList(deps_dict[req])
                pkg_list = this_sack.returnNewestByNameArch()
                del this_sack

                for res in pkg_list:
                    if res is not None:
                        if not unprocessed_pkgs.has_key(res.pkgtup):
                            unprocessed_pkgs[res.pkgtup] = res
    
    
    
    download_list = final_pkgs.values()
    if opts.newest:
        this_sack = ListPackageSack()
        this_sack.addList(download_list)
        download_list = this_sack.returnNewestByNameArch()
        
    
    for pkg in download_list:
        repo = my.repos.getRepo(pkg.repoid)
        remote = pkg.returnSimple('relativepath')
        if opts.urls:
            url = urljoin(repo.urls[0],remote)
            print '%s' % url
            continue
        local = os.path.basename(remote)
        local = os.path.join(opts.destdir, local)
        if (os.path.exists(local) and 
            str(os.path.getsize(local)) == pkg.returnSimple('packagesize')):
            if not opts.quiet:
                my.errorlog(0,"%s already exists and appears to be complete" % local)
            continue
        # Disable cache otherwise things won't download
        repo.cache = 0
        my.log(2, 'Downloading %s' % os.path.basename(remote))
        repo.get(relative=remote, local=local)


if __name__ == "__main__":
    main()
    
