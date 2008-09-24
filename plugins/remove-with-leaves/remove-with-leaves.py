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


# Copyright 2008 Red Hat, Inc
# written by Seth Vidal <skvidal@fedoraproject.org>

#FIXME:
# When two requirements of a pkg being removed mutually require each other
# there's no way to have one know about the other and have this know to remove both
# ex: foo is being removed. it requires bar. bar requires baz. baz requires bar. 
#     nothing other than foo and baz require bar. 

"""
This plugin allows packages to clean up dependencies they pulled in which are
not in use by any other package.
"""


from yum.plugins import TYPE_CORE
from yum.constants import *

requires_api_version = '2.4'
plugin_type = (TYPE_CORE,)

_requires_cache = {}
ignore_list = ['glibc', 'bash', 'libgcc']


def _requires_this_package(rpmdb, pkg):
    if _requires_cache.has_key(pkg):
        return _requires_cache[pkg]
        
    requirers = {}
    for prov in pkg.provides:
        for req_pkg in rpmdb.getRequires(prov[0], prov[1], prov[2]):
            if req_pkg == pkg:
                continue
            requirers[req_pkg.pkgtup] = 1
    # do filelists, too :(
    for prov in pkg.filelist + pkg.dirlist + pkg.ghostlist:
        for req_pkg in rpmdb.getRequires(prov):
            if req_pkg == pkg:
                continue
            requirers[req_pkg.pkgtup] = 1

    _requires_cache[pkg] = requirers.keys()
    return requirers.keys()

def postresolve_hook(conduit):
    # get all the items in 
    tsInfo  = conduit.getTsInfo()
    rpmdb = conduit.getRpmDB()
    oldlen = 0
    while oldlen != len(tsInfo):
        oldlen = len(tsInfo)
        for txmbr in tsInfo.getMembersWithState(output_states=TS_REMOVE_STATES):
            if conduit._base.allowedMultipleInstalls(txmbr.po): 
                # these make everything dodgy, skip it
                continue
            for req in txmbr.po.requires:
                if req[0].startswith('rpmlib('):
                    continue
                for pkg in rpmdb.getProvides(req[0], req[1], req[2]):
                    if pkg.pkgtup in [ txmbr.po.pkgtup for txmbr in tsInfo.getMembersWithState(output_states=TS_REMOVE_STATES) ]:
                        continue # skip ones already marked for remove, kinda pointless
                    if pkg.name in ignore_list: # there are some pkgs which are NEVER going to be leafremovals
                        continue
                    non_removed_requires = []
                    for req_pkgtup in _requires_this_package(rpmdb,pkg):
                        pkgtups = [ txmbr.po.pkgtup for txmbr in tsInfo.getMembersWithState(output_states=TS_REMOVE_STATES) ]
                        if req_pkgtup not in pkgtups:
                            non_removed_requires.append(req_pkgtup)

                    if not non_removed_requires:
                        conduit.info(2, 'removing %s. It is not required by anything else.' % pkg)
                        conduit._base.remove(pkg)









